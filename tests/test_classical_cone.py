"""Independent finite-state qualification of the research classical cone path.

All circuits below are original, synthetic development fixtures (repository MIT
license). These tests establish bounded functional behavior, not throughput or
an untouched public holdout result.
"""
from __future__ import annotations

import copy
import json
import random
from dataclasses import replace

import pytest

from symq import Circuit
from symq.circuit import Gate
from symq.labs import classical_cone as cones
from symq.labs.classical_transcript import Program, digest
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.resources import Budget, ResourceLimitExceeded
from symq.sat.assumptions import And, Eq, Not, Var


def _pin(source):
    return digest(Program.freeze(source))


def _scalar(width, gates, value):
    """Straight bit-list oracle: no Circuit.run, cone logic, SAT, or ANF."""
    bits = [(value >> q) & 1 for q in range(width)]
    for gate in gates:
        wires = gate.qubits
        if gate.name == "x":
            bits[wires[0]] = 1 - bits[wires[0]]
        elif gate.name == "cx":
            bits[wires[1]] ^= bits[wires[0]]
        elif gate.name == "ccx":
            bits[wires[2]] ^= bits[wires[0]] * bits[wires[1]]
        elif gate.name == "mcx":
            enabled = 1
            for control in wires[:-1]:
                enabled *= bits[control]
            bits[wires[-1]] ^= enabled
        else:
            raise AssertionError("unknown oracle gate")
    return bits


def _extract(source, at=None, wires=(0,), **kwargs):
    return cones.extract_classical_cone(
        source, at=len(source.gates) if at is None else at, observed_wires=wires,
        expected_source_sha256=_pin(source), **kwargs,
    )


def _product():
    # The irrelevant wire's changes are intentionally interleaved with the cone.
    source = Circuit(5).x(4).ccx(0, 1, 2).x(4).cx(2, 3)
    predicate = Eq(Var("u.2"), And(Var("u.0"), Var("u.1")))
    return source, predicate


def _prove(source, predicate, *, at=None, **kwargs):
    return cones.prove_cone_predicate(
        source, at=len(source.gates) if at is None else at, predicate=predicate,
        expected_source_sha256=_pin(source), **kwargs,
    )


def test_temporal_slice_keeps_only_writes_needed_at_the_time_of_read():
    source = Circuit(6).cx(0, 2).x(0).cx(4, 5).ccx(2, 3, 1).x(2)
    answer = _extract(source, at=4, wires=(1,))
    assert answer.outcome == "extracted"
    cone = answer.cone
    assert cone.gate_indices == (0, 3)
    assert cone.wires == (0, 1, 2, 3)
    assert cone.span == (0, 4)
    for value in range(1 << source.width):
        local = sum(((value >> wire) & 1) << q for q, wire in enumerate(cone.wires))
        reference = _scalar(source.width, source.gates[:4], value)
        sliced = _scalar(cone.program.width, cone.program.gates, local)
        assert reference[1] == sliced[cone.wires.index(1)]
    # The slice guarantees only requested outputs, not every mapped wire.
    assert _scalar(6, source.gates[:4], 0)[0] != _scalar(4, cone.program.gates, 0)[0]


def test_seeded_cones_agree_on_all_boundary_inputs_with_independent_oracle():
    rng = random.Random(62143)
    for case in range(35):
        width = 2 + case % 5
        source = Circuit(width)
        for _ in range(30):
            arity = rng.randint(1, min(width, 5))
            name = {1: "x", 2: "cx", 3: "ccx"}.get(arity, "mcx")
            source.append(name, *rng.sample(range(width), arity))
        start = rng.randrange(15)
        at = rng.randrange(15, 31)
        observed = tuple(rng.sample(range(width), rng.randint(1, width)))
        cone = _extract(source, at=at, wires=observed, start_op=start).cone
        for value in range(1 << width):
            local = sum(((value >> wire) & 1) << q for q, wire in enumerate(cone.wires))
            reference = _scalar(width, source.gates[start:at], value)
            sliced = _scalar(cone.program.width, cone.program.gates, local)
            assert all(reference[q] == sliced[cone.wires.index(q)] for q in observed)


def test_replay_reconstructs_closure_source_position_and_mapping():
    source = Circuit(5).cx(0, 2).ccx(2, 3, 1).x(4)
    answer = _extract(source, at=2, wires=(1,))
    receipt = json.loads(json.dumps(answer.to_dict()))

    def replay(record, current=source, pin=None):
        return cones.verify_classical_cone(
            current, record, at=2, observed_wires=(1,),
            expected_source_sha256=_pin(source) if pin is None else pin,
        )

    assert replay(receipt).outcome == "extracted"
    mutants = []
    for key, value in (
        ("gate_indices", [1]), ("wires", [0, 2, 1, 3]), ("span", [1, 2]),
        ("observed_wires", [2]), ("source_width", 6), ("boundary_inputs", "zero"),
        ("source_gate_count", True), ("source_sha256", "0" * 64),
    ):
        mutant = copy.deepcopy(receipt)
        mutant["cone"][key] = value
        mutants.append(mutant)
    mutant = copy.deepcopy(receipt)
    mutant["cone"]["program"]["gates"][0][1] = [0, 1]
    mutants.append(mutant)
    mutant = copy.deepcopy(receipt)
    mutant["schema_version"] = True
    mutants.append(mutant)
    for mutant in mutants:
        with pytest.raises(ValueError, match="receipt"):
            replay(mutant)

    changed = source.snapshot().x(4)  # identical selected outputs, stale *source* identity
    with pytest.raises(ValueError, match="SHA-256"):
        replay(receipt, changed)
    with pytest.raises(ValueError, match="receipt"):
        replay(receipt, changed, _pin(changed))


def test_snapshot_is_detached_and_unknown_gate_is_never_encoded_as_x():
    source = Circuit(2).cx(0, 1)
    extracted = _extract(source, wires=(1,))
    object.__setattr__(source.gates[0], "qubits", (1, 0))
    assert extracted.cone.program.gates == (Gate("cx", (0, 1)),)
    source = Circuit(2).cx(0, 1)
    pin = _pin(source)
    object.__setattr__(source.gates[0], "name", "hmr")
    result = cones.extract_classical_cone(
        source, at=1, observed_wires=(1,), expected_source_sha256=pin,
    )
    assert result.outcome == "unsupported" and result.cone is None


@pytest.mark.parametrize("kwargs", [
    {"at": True}, {"start_op": True}, {"observed_wires": (True,)},
    {"observed_wires": (0, 0)}, {"observed_wires": ()}, {"at": 2},
])
def test_invalid_positions_and_wire_grammar_raise(kwargs):
    args = {"at": 1, "observed_wires": (0,), **kwargs}
    source = Circuit(2).x(0)
    with pytest.raises((ValueError, TypeError)):
        cones.extract_classical_cone(source, expected_source_sha256=_pin(source), **args)


@pytest.mark.sat
def test_spurious_cut_witness_causes_expansion_not_a_global_refutation():
    source, predicate = _product()
    initial = ((2, 0),)
    short = _prove(source, predicate, at=3, initial_constants=initial,
                   start_op=2, expand_cut=False)
    assert short.outcome == "not_proved" and not short.proved
    assert short.counterexample_input is None
    assert short.attempts[0].to_dict()["witness_kind"] == "arbitrary_cut_input"
    result = _prove(source, predicate, at=3, initial_constants=initial, start_op=2)
    assert result.proved
    assert [attempt.start_op for attempt in result.attempts] == [2, 1, 0]
    assert [attempt.outcome for attempt in result.attempts] == ["not_proved", "not_proved", "proved"]
    for value in range(1 << source.width):
        if not (value >> 2) & 1:
            state = _scalar(source.width, source.gates[:3], value)
            assert state[2] == state[0] * state[1]


@pytest.mark.sat
def test_dirty_ancilla_and_clobbered_product_have_replayed_global_witnesses():
    source, predicate = _product()
    for initial, clobber in (((), False), (((2, 0), (4, 1)), True)):
        current = source.snapshot()
        if clobber:
            current.gates.insert(2, Gate("x", (2,)))
        result = _prove(current, predicate, initial_constants=initial)
        assert result.outcome == "precondition_failed" and not result.proved
        value = result.counterexample_input
        assert value is not None
        assert all((value >> q) & 1 == bit for q, bit in initial)
        state = _scalar(current.width, current.gates, value)
        assert state[2] != state[0] * state[1]


@pytest.mark.sat
def test_initial_zero_is_not_assumed_at_a_later_cut():
    source = Circuit(2).x(1)
    result = _prove(source, Not(Var("u.1")), initial_constants=((1, 0),), start_op=1)
    assert result.outcome == "precondition_failed"
    assert result.counterexample_input == 0
    assert result.attempts[0].outcome == "not_proved"


@pytest.mark.sat
def test_exact_predicates_match_full_scalar_domains_in_seeded_small_circuits():
    rng = random.Random(9927)
    for _ in range(30):
        source = Circuit(4)
        for _ in range(12):
            arity = rng.randint(1, 4)
            source.append({1: "x", 2: "cx", 3: "ccx", 4: "mcx"}[arity],
                          *rng.sample(range(4), arity))
        a, b, c = rng.sample(range(4), 3)
        predicate = Eq(Var(f"u.{a}"), And(Var(f"u.{b}"), Var(f"u.{c}")))
        constants = ((rng.randrange(4), rng.randrange(2)),)
        states = [_scalar(4, source.gates, x) for x in range(16)
                  if all((x >> q) & 1 == bit for q, bit in constants)]
        expected = all(s[a] == s[b] * s[c] for s in states)
        result = _prove(source, predicate, initial_constants=constants)
        assert result.proved == expected
        assert result.outcome in {"proved", "precondition_failed"}


@pytest.mark.sat
def test_positive_receipt_replays_and_can_feed_existing_contextual_checker():
    source, predicate = _product()
    initial = ((2, 0),)
    result = _prove(source, predicate, at=3, initial_constants=initial, start_op=2)
    receipt = json.loads(json.dumps(result.to_dict()))
    replayed = cones.replay_cone_predicate(
        source, receipt, at=3, predicate=predicate, initial_constants=initial,
        expected_source_sha256=_pin(source),
    )
    assert replayed.proved
    contract = SubstitutionContract(
        initial_constants=replayed.initial_constants,
        cut_assumption=replayed.cut_assumption(source, at=3),
    )
    proof = check_substitution(source, (3, 4), Circuit(5).ccx(0, 1, 3), contract=contract)
    assert proof.equivalent
    assert receipt["candidate_authorized"] is False
    for fake in (replace(replayed, at=2), replace(replayed, initial_constants=())):
        assert not fake.proved
        with pytest.raises(ValueError):
            fake.cut_assumption(source, at=fake.at)
    with pytest.raises(ValueError, match="position"):
        replayed.cut_assumption(source, at=2)


@pytest.mark.sat
def test_positive_receipt_rejects_tampered_context_closure_and_witness():
    source, predicate = _product()
    initial = ((2, 0),)
    result = _prove(source, predicate, at=3, initial_constants=initial, start_op=2)

    def replay(receipt, **kwargs):
        args = {"at": 3, "predicate": predicate, "initial_constants": initial,
                "expected_source_sha256": _pin(source), **kwargs}
        return cones.replay_cone_predicate(source, receipt, **args)

    for key, value in (("at", True), ("initial_constants", []), ("source_sha256", "0" * 64),
                       ("candidate_authorized", True), ("schema_version", True)):
        receipt = result.to_dict()
        receipt[key] = value
        with pytest.raises(ValueError):
            replay(receipt)
    receipt = result.to_dict()
    receipt["cone"]["gate_indices"] = []
    with pytest.raises(ValueError):
        replay(receipt)
    receipt = result.to_dict()
    receipt["attempts"][0]["local_input"] = 0  # satisfies the product predicate
    with pytest.raises(ValueError, match="witness"):
        replay(receipt)
    with pytest.raises(ValueError):
        replay(result.to_dict(), initial_constants=())
    with pytest.raises(ValueError):
        replay(result.to_dict(), predicate=Not(Var("u.2")))


@pytest.mark.parametrize("limits", [
    cones.ConeLimits(max_source_gates=1), cones.ConeLimits(max_source_width=2),
    cones.ConeLimits(max_cone_gates=1), cones.ConeLimits(max_cone_width=1),
    cones.ConeLimits(max_scanned_gates=1),
])
def test_extraction_caps_never_return_a_partial_cone(limits):
    source = Circuit(3).cx(0, 1).cx(1, 2)
    result = _extract(source, wires=(2,), limits=limits)
    assert result.outcome == "inconclusive" and result.cone is None


@pytest.mark.sat
@pytest.mark.parametrize("limits", [
    cones.ConeLimits(max_attempts=1), cones.ConeLimits(max_predicate_nodes=1),
    cones.ConeLimits(max_variables=1), cones.ConeLimits(max_clauses=1),
])
def test_proof_caps_leave_no_usable_predicate(limits):
    source, predicate = _product()
    result = _prove(source, predicate, at=3, initial_constants=((2, 0),), start_op=2, limits=limits)
    assert result.outcome == "inconclusive" and not result.proved
    assert result.counterexample_input is None
    json.dumps(result.to_dict())
    with pytest.raises(ValueError):
        result.cut_assumption(source, at=3)


def test_missing_sat_and_expired_whole_call_budget_are_typed(monkeypatch):
    source, predicate = _product()
    monkeypatch.setattr(cones, "_solver_factory", lambda: None)
    assert _prove(source, predicate).outcome == "unsupported"
    expired = Budget(absolute_deadline=0)
    assert _extract(source, budget=expired).outcome == "inconclusive"
    result = _prove(source, predicate, budget=expired)
    assert result.outcome == "inconclusive"
    json.dumps(result.to_dict())
    receipt = _extract(source).to_dict()
    assert cones.verify_classical_cone(
        source, receipt, at=4, observed_wires=(0,), expected_source_sha256=_pin(source),
        budget=expired,
    ).outcome == "inconclusive"


@pytest.mark.sat
def test_solver_unknown_and_expired_replay_never_become_proved(monkeypatch):
    source, predicate = _product()
    original = cones.solve_with_deadline
    monkeypatch.setattr(cones, "solve_with_deadline", lambda *_: (None, False))
    result = _prove(source, predicate, initial_constants=((2, 0),))
    assert result.outcome == "inconclusive" and not result.proved
    monkeypatch.setattr(cones, "solve_with_deadline", original)
    good = _prove(source, predicate, initial_constants=((2, 0),))
    expired = Budget(absolute_deadline=0)
    replay = cones.replay_cone_predicate(
        source, good.to_dict(), at=4, predicate=predicate, initial_constants=((2, 0),),
        expected_source_sha256=_pin(source), budget=expired,
    )
    assert replay.outcome == "inconclusive" and not replay.proved


@pytest.mark.sat
def test_deadline_after_solver_cleanup_invalidates_a_decisive_answer(monkeypatch):
    source, predicate = _product()
    factory = cones._solver_factory()
    deleted = False
    original_check = cones.Guard.check_time

    class Solver:
        def __init__(self, **kwargs):
            self.delegate = factory(**kwargs)

        def __getattr__(self, name):
            return getattr(self.delegate, name)

        def delete(self):
            nonlocal deleted
            self.delegate.delete()
            deleted = True

    def check(guard):
        if deleted:
            raise ResourceLimitExceeded("seconds", 1, 2)
        original_check(guard)

    monkeypatch.setattr(cones, "_solver_factory", lambda: Solver)
    monkeypatch.setattr(cones.Guard, "check_time", check)
    result = _prove(source, predicate, initial_constants=((2, 0),))
    assert deleted
    assert result.outcome == "inconclusive" and not result.proved
    assert result.counterexample_input is None


@pytest.mark.parametrize("predicate", [Var("x.0"), Var("u.01"), Var("u.5"), Var("u.١")])
def test_predicate_names_are_closed_and_canonical(predicate):
    source, _ = _product()
    with pytest.raises(ValueError):
        _prove(source, predicate)


def test_general_initial_assumption_is_explicitly_unsupported():
    source, predicate = _product()
    with pytest.raises(TypeError, match="assumption"):
        _prove(source, predicate, assumption=Not(Var("x.2")))
