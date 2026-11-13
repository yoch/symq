"""A verification record hashes the exact detached objects used by its engine and replay."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from symq import Budget, Circuit, verification
from symq.phase import PhaseProgram
from symq.sat import Contract
from symq.sat.assumptions import And, Const, Eq, Not, Var, Xor


@contextmanager
def mutate_before_engine(monkeypatch, entry, mutate, restore=None):
    """Schedule a real caller thread while leaving the real engine and replay intact."""
    ready = threading.Event()
    real = getattr(verification, entry)

    def worker():
        assert ready.wait(5), "verification never reached its engine"
        mutate()

    with ThreadPoolExecutor(max_workers=1) as executor:
        mutation = executor.submit(worker)

        def synchronized(*args, **kwargs):
            ready.set()
            mutation.result(timeout=5)
            try:
                return real(*args, **kwargs)
            finally:
                if restore is not None:
                    executor.submit(restore).result(timeout=5)

        monkeypatch.setattr(verification, entry, synchronized)
        try:
            yield
        finally:
            ready.set()
            mutation.result(timeout=5)


@pytest.mark.parametrize("engine,entry", [
    ("reference", "check_equivalence"),
    ("sparse", "check_equivalence"),
    ("zdd", "check_equivalence"),
    pytest.param("sat", "check_sat_equivalence", marks=pytest.mark.sat),
])
def test_classical_hash_verdict_and_witness_share_one_snapshot(monkeypatch, engine, entry):
    left, right = Circuit(1), Circuit(1).x(0)
    original = right.snapshot()
    expected_hash = verification._program_hash(original)
    with mutate_before_engine(monkeypatch, entry, right.gates.clear):
        record = verification.verify_explicit(left, right, theorem="classical_full", engine=engine)
    assert not right.gates  # the caller really changed its program before execution
    assert record.right_sha256 == expected_hash
    assert record.outcome == "different" and record.witness_kind == "input"
    assert left.run(record.witness) != original.run(record.witness)


def test_phase_hash_verdict_and_oracle_replay_share_one_snapshot(monkeypatch):
    left, right = PhaseProgram(1), PhaseProgram(1).z(0)
    expected_hash = verification._program_hash(right)
    with mutate_before_engine(monkeypatch, "check_phase_equivalence", right.ops.clear):
        record = verification.verify_explicit(left, right, theorem="sign_phase_exact",
                                             engine="phase-reference")
    assert not right.ops
    assert record.right_sha256 == expected_hash
    assert record.outcome == "different" and record.witness == 1


def test_restoring_the_caller_input_before_return_does_not_rebind_the_result(monkeypatch):
    left, right = Circuit(1), Circuit(1).x(0)
    original_gates = list(right.gates)
    expected_hash = verification._program_hash(right)
    with mutate_before_engine(monkeypatch, "check_equivalence", right.gates.clear,
                              lambda: right.gates.extend(original_gates)):
        record = verification.verify_explicit(left, right, theorem="classical_full", engine="zdd")
    # An initial/final hash comparison alone would miss this change-and-restore race.
    assert verification._program_hash(right) == record.right_sha256 == expected_hash
    assert record.outcome == "different"
    assert left.run(record.witness) != right.run(record.witness)


def test_snapshot_rebuilds_gate_internals_instead_of_sharing_frozen_objects(monkeypatch):
    left, right = Circuit(2).x(0), Circuit(2).x(0)
    expected_hash = verification._program_hash(right)

    def mutate():
        object.__setattr__(right.gates[0], "qubits", (1,))

    with mutate_before_engine(monkeypatch, "check_equivalence", mutate):
        record = verification.verify_explicit(left, right, theorem="classical_full", engine="zdd")
    assert record.outcome == "equivalent"
    assert record.right_sha256 == expected_hash != verification._program_hash(right)


@pytest.mark.sat
@pytest.mark.parametrize("field", ["input_constants", "observed_outputs", "restored_wires",
                                   "output_map", "assumption"])
def test_contract_digest_and_sat_replay_use_detached_fields(monkeypatch, field):
    left, right = Circuit(2), Circuit(2).x(1)
    if field == "input_constants":
        right = Circuit(2).cx(0, 1)
        contract = Contract(input_constants={0: 1}, observed_outputs=(1,))
        mutate = lambda: contract.input_constants.update({0: 0})
    elif field == "observed_outputs":
        # Lists are accepted by Contract.validate; they must also be detached.
        contract = Contract(observed_outputs=[0, 1])
        mutate = contract.observed_outputs.pop
    elif field == "restored_wires":
        contract = Contract(observed_outputs=(0,), restored_wires=[1])
        mutate = contract.restored_wires.clear
    elif field == "output_map":
        contract = Contract(output_map={1: 1})

        def mutate():
            contract.output_map.clear()
            contract.output_map[0] = 0
    else:
        variable = Var("x.0")
        contract = Contract(observed_outputs=(1,), assumption=And(
            Eq(variable, Const(True)), Not(Xor(Var("x.1"), Const(False)))))
        # Change a descendant, not just the root: a shallow copy is insufficient.
        mutate = lambda: object.__setattr__(variable, "name", "x.1")
    expected_hash = verification._contract_hash(contract, left.width)
    with mutate_before_engine(monkeypatch, "check_sat_equivalence", mutate):
        record = verification.verify_explicit(left, right, theorem="classical_contract",
                                             engine="sat", contract=contract)
    assert record.contract_sha256 == expected_hash
    assert record.outcome == "different" and record.witness_kind == "input"
    assert record.contract_sha256 != verification._contract_hash(contract, left.width)
    # The mutation weakens every case enough to make the *current* inputs equivalent.
    current = verification.verify_explicit(left, right, theorem="classical_contract",
                                          engine="sat", contract=contract)
    assert current.outcome == "equivalent"


@pytest.mark.parametrize("program_type,theorem,engine", [
    (Circuit, "classical_full", "sparse"),
    (PhaseProgram, "sign_phase_exact", "phase-reference"),
])
def test_expiration_during_snapshot_is_inconclusive_without_claimed_hashes(
        monkeypatch, program_type, theorem, engine):
    now = [0.0]
    polls = []
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    real = program_type.snapshot

    def slow_snapshot(self, *, check=None):
        def checkpoint():
            polls.append(None)
            now[0] += 1
            check()
        return real(self, check=checkpoint)

    monkeypatch.setattr(program_type, "snapshot", slow_snapshot)
    program = program_type(1).x(0).x(0).x(0)
    record = verification.verify_explicit(program, program, theorem=theorem, engine=engine,
                                         budget=Budget(max_seconds=2))
    assert record.outcome == "inconclusive" and record.witness is None
    assert record.left_sha256 == record.right_sha256 == ""
    assert len(polls) == 2  # capture stopped at the deadline, not after copying all gates


def test_expiration_during_contract_copy_stops_before_hashing(monkeypatch):
    now = [0.0]
    copied = []
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])

    class TimedConstants(dict):
        def items(self):
            for item in super().items():
                now[0] += 1
                copied.append(item)
                yield item

    contract = Contract(input_constants=TimedConstants({i: 0 for i in range(20)}))
    record = verification.verify_explicit(Circuit(20), Circuit(20), theorem="classical_contract",
                                         engine="sat", contract=contract,
                                         budget=Budget(max_seconds=2))
    assert record.outcome == "inconclusive" and record.contract_sha256 is None
    assert record.left_sha256 == record.right_sha256 == ""
    assert len(copied) == 2


def test_engine_inherits_the_deadline_started_before_capture(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    real_hash = verification._program_hash
    real_check = verification.check_equivalence
    deadlines = []

    def slow_hash(value):
        now[0] += 2
        return real_hash(value)

    def check(*args, **kwargs):
        deadlines.append(kwargs["budget"].absolute_deadline)
        return real_check(*args, **kwargs)

    monkeypatch.setattr(verification, "_program_hash", slow_hash)
    monkeypatch.setattr(verification, "check_equivalence", check)
    record = verification.verify_explicit(Circuit(1), Circuit(1), theorem="classical_full",
                                         engine="sparse", budget=Budget(max_seconds=10))
    assert record.outcome == "equivalent"
    assert deadlines == [110.0]
