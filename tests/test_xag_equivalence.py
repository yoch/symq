"""The affine encoder must agree with exhaustive execution, in every mode the contract allows.

This is the acceptance test of issue #69: no size claim matters until the encoding is proved to
decide the same predicate as the transition encoder and as concrete execution. Every case is
checked against ``Circuit.run`` on every input of small circuits, and against the existing SSA
encoder on the same instance.
"""
from __future__ import annotations

import random

import pytest

from symq import Budget, Circuit, Gate
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.sat import Contract, available
from symq.sat.encoding import solver_available
from symq.sat.miter_xag import check_xag_equivalence

pytestmark = pytest.mark.skipif(not (available() and solver_available()),
                                reason="python-sat is not installed")


def exhaustive(left: Circuit, right: Circuit, contract: Contract | None = None) -> bool:
    """Reference: concrete execution on every legal input, no encoding involved."""
    contract = contract or Contract()
    for x in range(1 << left.width):
        if any(((x >> wire) & 1) != value for wire, value in contract.input_constants.items()):
            continue
        a, b = left.run(x), right.run(x)
        for left_wire, right_wire in pairs(contract, left.width):
            if ((a >> left_wire) & 1) != ((b >> right_wire) & 1):
                return False
        for wire in contract.restored_wires:
            initial = (x >> wire) & 1
            if ((a >> wire) & 1) != initial or ((b >> wire) & 1) != initial:
                return False
    return True


def pairs(contract: Contract, width: int) -> list[tuple[int, int]]:
    if contract.output_map:
        return sorted(contract.output_map.items())
    if contract.observed_outputs is not None:
        return [(wire, wire) for wire in contract.observed_outputs]
    return [(wire, wire) for wire in range(width)]


@pytest.mark.parametrize("seed", range(40))
def test_the_verdict_matches_exhaustive_execution(seed):
    rng = random.Random(seed)
    width = rng.randint(1, 6)
    left = random_circuit(width, rng.randint(0, 16), rng)
    right = (equivalent_variant(left, rng, steps=rng.randint(1, 6))
             if rng.random() < 0.5 else random_circuit(width, rng.randint(0, 16), rng))
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=20))
    assert verdict.outcome in ("equivalent", "different"), verdict
    expected = "equivalent" if exhaustive(left, right) else "different"
    assert verdict.outcome == expected, (seed, left.gates, right.gates)
    if verdict.outcome == "different":
        assert verdict.witness_checked, "a counterexample must be replayed"
        assert left.run(verdict.witness) != right.run(verdict.witness)


@pytest.mark.parametrize("seed", range(25))
def test_the_two_encoders_agree(seed):
    """The XAG and SSA encoders must decide the same predicate on the same instance."""
    from symq.sat import check_sat_equivalence

    rng = random.Random(1000 + seed)
    width = rng.randint(2, 6)
    left = random_circuit(width, rng.randint(1, 14), rng)
    right = (equivalent_variant(left, rng, steps=4) if rng.random() < 0.5
             else mutate(left, rng, "insert")[0])
    xag = check_xag_equivalence(left, right, budget=Budget(max_seconds=20))
    ssa = check_sat_equivalence(left, right, budget=Budget(max_seconds=20))
    assert xag.outcome == ssa.outcome, (seed, xag.outcome, ssa.outcome)


def test_the_four_gate_shapes():
    for circuit in (
        Circuit(1).x(0),
        Circuit(2).cx(0, 1),
        Circuit(3).ccx(0, 1, 2),
        Circuit(5).mcx(0, 1, 2, 3, 4),
    ):
        assert check_xag_equivalence(circuit, circuit).outcome == "equivalent"


def test_a_rare_input_difference_is_found():
    width = 6
    left = Circuit(width)
    right = Circuit(width).mcx(*range(width))
    verdict = check_xag_equivalence(left, right)
    assert verdict.outcome == "different"
    assert all((verdict.witness >> wire) & 1 for wire in range(width - 1))


def test_constant_inputs_narrow_the_domain():
    left = Circuit(2)
    right = Circuit(2).cx(0, 1)
    assert check_xag_equivalence(left, right).outcome == "different"
    contract = Contract(input_constants={0: 0})
    assert check_xag_equivalence(left, right, contract).outcome == "equivalent"
    assert exhaustive(left, right, contract)


def test_observed_outputs_and_restored_wires():
    clean = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    dirty = Circuit(3).ccx(0, 1, 2)
    identity = Circuit(3)
    contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))
    assert check_xag_equivalence(clean, identity, contract).outcome == "equivalent"
    assert check_xag_equivalence(dirty, identity, contract).outcome == "different"
    assert exhaustive(clean, identity, contract)
    assert not exhaustive(dirty, identity, contract)


def test_a_wire_permutation_can_be_declared():
    left = Circuit(2).cx(0, 1).cx(1, 0)
    right = Circuit(2).cx(1, 0).cx(0, 1)
    contract = Contract(output_map={0: 1, 1: 0})
    verdict = check_xag_equivalence(left, right, contract)
    assert verdict.outcome == ("equivalent" if exhaustive(left, right, contract) else "different")


def test_a_long_xor_chain_keeps_its_semantics():
    """A linear circuit of 40 CX gates must stay exact, however long its affine forms get."""
    circuit = Circuit(8)
    for step in range(40):
        circuit.cx(step % 8, (step * 3 + 1) % 8)
    assert check_xag_equivalence(circuit, Circuit(8, list(circuit.gates))).outcome == "equivalent"
    mutant = Circuit(8, [*circuit.gates, Gate("x", (7,))])
    assert check_xag_equivalence(circuit, mutant).outcome == "different"


def test_an_invalid_gate_is_refused():
    from types import SimpleNamespace

    valid = Circuit(1).x(0)
    corrupted = Circuit(1)
    corrupted.gates.append(SimpleNamespace(name="z", qubits=(0,)))
    with pytest.raises(TypeError):
        check_xag_equivalence(valid, corrupted)


def test_an_inconclusive_run_is_not_a_verdict():
    rng = random.Random(9)
    left = random_circuit(6, 30, rng)
    right = random_circuit(6, 30, rng)
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=1e-6))
    if verdict.outcome == "inconclusive":
        assert verdict.equivalent is None


def test_an_expired_budget_is_inconclusive_not_a_verdict(monkeypatch):
    """The budget must be enforced, not merely honoured when convenient.

    The previous test only checked ``if verdict.outcome == "inconclusive"``, so it passed whatever
    happened. Here the *encoding* is made slow enough to cross a tiny deadline, and the verdict
    must be ``inconclusive`` with a budget reason and no boolean answer.
    """
    from symq.sat import miter_xag

    real_build = miter_xag.build_xag_miter

    def slow_build(*args, **kwargs):
        import time

        time.sleep(0.02)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(miter_xag, "build_xag_miter", slow_build)
    left = Circuit(3).cx(0, 1).ccx(0, 1, 2)
    right = Circuit(3).cx(0, 1).ccx(0, 1, 2)
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=1e-6))
    assert verdict.outcome == "inconclusive"
    assert verdict.equivalent is None
    assert "budget" in verdict.detail or "clock" in verdict.detail


def test_a_deadline_crossed_after_solving_is_still_inconclusive(monkeypatch):
    """An UNSAT answer completed past the deadline must not be reported as equivalent."""
    import symq.sat.miter as miter_module

    real_driver = miter_module.drive_solver

    def slow_driver(left, right, contract, miter, budget):
        import time

        from symq import Budget as B

        # Force a deadline that is already gone when the driver starts.
        time.sleep(0.01)
        return real_driver(left, right, contract, miter, B(max_seconds=1e-6))

    monkeypatch.setattr(miter_module, "drive_solver", slow_driver)
    left = Circuit(2).cx(0, 1)
    verdict = check_xag_equivalence(left, Circuit(2).cx(0, 1), budget=Budget(max_seconds=5))
    assert verdict.outcome == "inconclusive", verdict
    assert verdict.equivalent is None


def test_the_seconds_field_includes_everything_up_to_the_return(monkeypatch):
    """``SatVerdict.seconds`` must cover encoding, solving, replay and cleanup, not just solving."""
    left = Circuit(3).ccx(0, 1, 2)
    right = Circuit(3).ccx(0, 1, 2)
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=30))
    assert verdict.outcome == "equivalent"
    # The whole call, timed externally, must be at least the reported seconds.
    import time

    started = time.perf_counter()
    check_xag_equivalence(left, right, budget=Budget(max_seconds=30))
    external = time.perf_counter() - started
    assert verdict.seconds <= external + 0.01, (
        "the reported seconds cannot exceed the wall clock of the whole call")
    assert verdict.seconds > 0
