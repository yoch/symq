"""Exact prefix relations, independent finite oracles, and untrusted receipt tests."""
from __future__ import annotations

import copy
import hashlib
import random
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from symq import Circuit, Gate
from symq.errors import InternalInconsistency
from symq.labs import cut_invariants as ci
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.resources import Budget
from symq.sat.assumptions import Const, Eq, Not, Var, evaluate


def _rank(matrix):
    """Small dense elimination, deliberately independent of the learner's bitset kernel."""
    matrix = [list(row) for row in matrix]
    rank = 0
    if not matrix:
        return 0
    for column in range(len(matrix[0])):
        pivot = next((i for i in range(rank, len(matrix)) if matrix[i][column]), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        for i in range(rank + 1, len(matrix)):
            if matrix[i][column]:
                matrix[i] = [a ^ b for a, b in zip(matrix[i], matrix[rank])]
        rank += 1
    return rank


def _oracle(prefix, result, constants=(), assumption=None):
    reachable = []
    for value in range(1 << prefix.width):
        if any(((value >> q) & 1) != bit for q, bit in constants):
            continue
        if assumption is not None and not evaluate(
                assumption, {f"x.{q}": (value >> q) & 1 for q in range(prefix.width)}):
            continue
        reachable.append(prefix.run(value))
    if not reachable:
        assert result.outcome == "empty_domain"
        assert not result.proved and result.invariants == ()
        return
    assert result.proved
    matrix = [[int(state & mask == mask) for mask in result.dictionary] for state in reachable]
    assert result.rank == _rank(matrix)
    assert len(result.invariants) == len(result.dictionary) - result.rank
    vectors = [[(row >> j) & 1 for j in range(len(result.dictionary))]
               for row in result.invariants]
    assert _rank(vectors) == len(vectors)
    for row in matrix:
        for relation in vectors:
            assert sum(a * b for a, b in zip(row, relation)) % 2 == 0


@pytest.mark.sat
def test_quadratic_relation_and_dirty_ancilla_have_distinct_domains():
    prefix = Circuit(3).ccx(0, 1, 2)
    clean = ci.discover_cut_invariants(prefix, initial_constants=((2, 0),))
    dirty = ci.discover_cut_invariants(prefix)
    _oracle(prefix, clean, ((2, 0),))
    _oracle(prefix, dirty)
    assert clean.rank == 4 and len(clean.invariants) == 3
    assert dirty.rank == 7 and dirty.invariants == ()
    assert clean.problem_sha256 != dirty.problem_sha256
    assert all(not x & 4 for x in clean.sample_inputs)


@pytest.mark.sat
def test_explicit_dictionary_without_constant_handles_zero_seed_row():
    prefix = Circuit(3).ccx(0, 1, 2)
    result = ci.discover_cut_invariants(prefix, initial_constants=((2, 0),), dictionary=(3, 4))
    assert result.dictionary == (4, 3)
    assert result.invariants == (3,)
    assert result.rank == 1
    replay = ci.replay_cut_invariants(prefix, result.to_dict(), initial_constants=((2, 0),))
    assert replay.proved and replay.invariants == result.invariants


@pytest.mark.sat
def test_relational_input_domain_and_empty_domain():
    prefix = Circuit(4).cx(0, 2).ccx(1, 2, 3)
    relation = Eq(Var("x.0"), Var("x.1"))
    result = ci.discover_cut_invariants(prefix, assumption=relation)
    _oracle(prefix, result, assumption=relation)
    assert ci.replay_cut_invariants(prefix, result.to_dict(), assumption=relation).proved
    for empty in (Const(False), Not(Var("x.0"))):
        result = ci.discover_cut_invariants(prefix, initial_constants=((0, 1),), assumption=empty)
        _oracle(prefix, result, ((0, 1),), empty)
        with pytest.raises(ValueError, match="complete result"):
            result.cut_assumption(prefix)


@pytest.mark.sat
def test_seeded_small_circuits_match_all_legal_inputs_and_full_relation_dimension():
    randomizer = random.Random(20261101)
    for width in range(1, 7):
        for case in range(8):
            prefix = Circuit(width)
            for _ in range(6):
                size = randomizer.randint(1, min(4, width))
                wires = randomizer.sample(range(width), size)
                name = {1: "x", 2: "cx", 3: "ccx"}.get(size, "mcx")
                prefix.gates.append(Gate(name, tuple(wires)))
            constants = tuple((q, randomizer.randrange(2)) for q in range(width) if q % 3 == case % 3)
            result = ci.discover_cut_invariants(prefix, initial_constants=constants)
            _oracle(prefix, result, constants)
            assert result.refinements <= len(result.dictionary) - 1
            assert ci.replay_cut_invariants(prefix, result.to_dict(),
                                            initial_constants=constants).proved


@pytest.mark.sat
def test_learned_predicate_is_useful_but_never_replaces_contextual_proof():
    prefix = Circuit(4).ccx(0, 1, 2)
    learned = ci.discover_cut_invariants(prefix, initial_constants=((2, 0),))
    predicate = learned.cut_assumption(prefix)
    source = Circuit(4, prefix.gates + [Gate("cx", (2, 3))])
    candidate = Circuit(4).ccx(0, 1, 3)
    proved = check_substitution(
        source, (1, 2), candidate,
        contract=SubstitutionContract(initial_constants=((2, 0),), cut_assumption=predicate),
    )
    assert proved.outcome == "equivalent"
    no_relation = check_substitution(
        source, (1, 2), candidate, contract=SubstitutionContract(initial_constants=((2, 0),)),
    )
    assert no_relation.outcome != "equivalent"
    bad_context = Circuit(4).x(2).ccx(0, 1, 2).cx(2, 3)
    refused = check_substitution(
        bad_context, (2, 3), candidate,
        contract=SubstitutionContract(initial_constants=((2, 0),), cut_assumption=predicate),
    )
    assert refused.outcome != "equivalent"
    assert learned.to_dict()["candidate_authorized"] is False


@pytest.mark.sat
def test_unproved_sample_relations_are_refuted_by_sat_replay():
    prefix = Circuit(3).ccx(0, 1, 2)
    correct = ci.discover_cut_invariants(prefix, initial_constants=((2, 0),))
    forged = correct.to_dict()
    # One sample suggests every nonconstant feature is zero. It is not a proof.
    forged.update(sample_inputs=[0], rank=1,
                  invariants=[1 << j for j in range(1, len(correct.dictionary))])
    result = ci.replay_cut_invariants(prefix, forged, initial_constants=((2, 0),))
    assert result.outcome == "not_proved"
    assert not result.proved and result.invariants == ()
    assert result.counterexample_input is not None
    assert result.counterexample_input & 4 == 0
    assert prefix.run(result.counterexample_input) != 0


@pytest.mark.sat
def test_receipt_and_in_memory_mutations_never_authorize_a_predicate():
    prefix = Circuit(3).ccx(0, 1, 2)
    result = ci.discover_cut_invariants(prefix, initial_constants=((2, 0),))
    changed = replace(result, invariants=(1,))
    assert not changed.proved
    with pytest.raises(ValueError, match="complete result"):
        changed.cut_assumption(prefix)
    mutations = (
        lambda d: d.update(schema_version=True),
        lambda d: d.update(unrecognized=True),
        lambda d: d.update(candidate_authorized=True),
        lambda d: d.update(theorem="quantum_channel"),
        lambda d: d.update(rank=True),
        lambda d: d.update(invariants=[True]),
        lambda d: d.update(sample_inputs=[True]),
        lambda d: d.update(sample_inputs=[4]),
        lambda d: d.update(sample_inputs=d["sample_inputs"] * 2),
        lambda d: d.update(invariants=d["invariants"][:-1]),
        lambda d: d.update(dictionary=list(reversed(d["dictionary"]))),
        lambda d: d.update(problem_sha256="0" * 64),
        lambda d: d["problem"].update(initial_constants=[]),
        lambda d: d["problem"]["initial_constants"][0].__setitem__(1, False),
    )
    for mutate in mutations:
        receipt = copy.deepcopy(result.to_dict())
        mutate(receipt)
        with pytest.raises(ValueError):
            ci.replay_cut_invariants(prefix, receipt, initial_constants=((2, 0),))
    with pytest.raises(ValueError, match="identity mismatch"):
        ci.replay_cut_invariants(prefix, result.to_dict())
    prefix.x(0)
    with pytest.raises(ValueError, match="prefix differs"):
        result.cut_assumption(prefix)
    with pytest.raises(ValueError, match="identity mismatch"):
        ci.replay_cut_invariants(prefix, result.to_dict(), initial_constants=((2, 0),))
    assert ci.replay_cut_invariants(Circuit(3).ccx(0, 1, 2), result.to_dict(),
                                    initial_constants=((2, 0),)).proved


@pytest.mark.sat
def test_public_inc8_prefix_recovers_all_five_low_degree_relations():
    from symq.kickmix import parse_kmx

    raw = (Path(__file__).resolve().parents[1] / "benchmarks/corpus/kickmix/inc8.kmx").read_bytes()
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == (
        "0604339b577f47d5cc63de0a89088863e1e8a935")
    phase = parse_kmx(raw.decode()).to_phase_program(range(8))
    assert phase.width == 13
    assert all(op.kind == "mcx" and len(op.qubits) == 3 for op in phase.ops[:5])
    prefix = Circuit(13, [Gate("ccx", op.qubits) for op in phase.ops[:5]])
    constants = tuple((q, 0) for q in range(8, 13))
    result = ci.discover_cut_invariants(prefix, initial_constants=constants)
    assert result.proved and len(result.dictionary) == 92
    assert result.rank == 57 and len(result.invariants) == 35
    assert result.refinements == 56
    # All 256 legal data assignments; five ancillas were explicitly initialized.
    _oracle(prefix, result, constants)
    features = {mask: i for i, mask in enumerate(result.dictionary)}
    vectors = [[(row >> j) & 1 for j in range(92)] for row in result.invariants]
    for gate in prefix.gates:
        target = (1 << features[1 << gate.target]) ^ (
            1 << features[sum(1 << q for q in gate.controls)])
        assert _rank(vectors + [[(target >> j) & 1 for j in range(92)]]) == 35
    assert ci.replay_cut_invariants(prefix, result.to_dict(), initial_constants=constants).proved


@pytest.mark.parametrize("kwargs", [
    {"dictionary": ()}, {"dictionary": [0, 1]}, {"dictionary": (0, True)},
    {"dictionary": (0, 1, 1)}, {"dictionary": (0, 8)}, {"degree": True},
    {"degree": -1}, {"initial_constants": ((True, 0),)},
    {"initial_constants": ((2, True),)}, {"initial_constants": ((2, 0), (2, 1))},
    {"assumption": Var("u.0")}, {"assumption": object()},
])
def test_invalid_input_is_rejected_before_solver_work(kwargs):
    with pytest.raises((ValueError, TypeError)):
        ci.discover_cut_invariants(Circuit(3), **kwargs)


def test_assumption_name_subclasses_cannot_inject_dynamic_comparison_semantics():
    class DynamicName(str):
        pass

    with pytest.raises(ValueError, match="plain strings"):
        ci.discover_cut_invariants(Circuit(1), assumption=Var(DynamicName("x.0")))


@pytest.mark.parametrize("attribute,value", [
    ("name", "h"), ("name", "cx"), ("name", True),
    ("qubits", ()), ("qubits", (0, 1)), ("qubits", (True,)),
    ("qubits", (-1,)), ("qubits", (1,)), ("qubits", [0]),
])
def test_mutated_gate_internals_are_revalidated_before_discovery(attribute, value):
    gate = Gate("x", (0,))
    prefix = Circuit(1, [gate])
    object.__setattr__(gate, attribute, value)
    with pytest.raises((ValueError, TypeError)):
        ci.discover_cut_invariants(prefix, initial_constants=((0, 0),))


@pytest.mark.parametrize("attribute,value", [
    ("width", True), ("width", 0), ("gates", None), ("gates", ()), ("gates", [object()]),
])
def test_mutated_prefix_shape_is_rejected_explicitly(attribute, value):
    prefix = Circuit(1)
    setattr(prefix, attribute, value)
    with pytest.raises((ValueError, TypeError)):
        ci.discover_cut_invariants(prefix)


@pytest.mark.sat
def test_owned_source_snapshot_and_predicate_reject_bypassed_frozen_gate_mutation():
    prefix = Circuit(1).x(0)
    result = ci.discover_cut_invariants(prefix, initial_constants=((0, 0),))
    assert result.proved
    receipt = result.to_dict()
    object.__setattr__(prefix.gates[0], "name", "h")
    # The certificate owns reconstructed gates, not the caller's Gate objects.
    assert result.proved and result.to_dict() == receipt
    with pytest.raises((ValueError, TypeError)):
        result.cut_assumption(prefix)
    with pytest.raises((ValueError, TypeError)):
        ci.replay_cut_invariants(prefix, receipt, initial_constants=((0, 0),))
    original = Circuit(1).x(0)
    assert ci.replay_cut_invariants(original, receipt, initial_constants=((0, 0),)).proved
    assert evaluate(result.cut_assumption(original), {"u.0": 1})


@pytest.mark.parametrize("limits", [
    ci.InvariantLimits(max_monomials=1), ci.InvariantLimits(max_variables=1),
    ci.InvariantLimits(max_clauses=1), ci.InvariantLimits(max_refinements=0),
    ci.InvariantLimits(max_prefix_gates=1), ci.InvariantLimits(max_assumption_nodes=1),
])
@pytest.mark.sat
def test_resource_caps_are_inconclusive_without_invariant_leakage(limits):
    result = ci.discover_cut_invariants(
        Circuit(3).cx(0, 1).ccx(0, 1, 2), assumption=Eq(Var("x.0"), Var("x.1")), limits=limits,
    )
    assert result.outcome == "inconclusive"
    assert not result.proved and result.invariants == ()
    assert "cap" in result.reason


def test_missing_solver_and_expired_budget_fail_closed(monkeypatch):
    monkeypatch.setattr(ci, "_solver_factory", lambda: None)
    result = ci.discover_cut_invariants(Circuit(3))
    assert result.outcome == "inconclusive" and result.invariants == ()
    assert result.engine == "unavailable"
    expired = ci.discover_cut_invariants(Circuit(3), budget=Budget(absolute_deadline=0))
    assert expired.outcome == "inconclusive" and expired.invariants == ()
    with pytest.raises(ValueError, match="time budgets"):
        ci.discover_cut_invariants(Circuit(3), budget=Budget(max_nodes=10))


def test_watchdog_interrupts_a_blocking_solve(monkeypatch):
    event = threading.Event()
    deleted = []

    class SlowSolver:
        def __init__(self, **kwargs):
            pass

        def solve_limited(self, **kwargs):
            assert event.wait(1), "watchdog did not interrupt the solver"

        def interrupt(self):
            event.set()

        def delete(self):
            deleted.append(True)

    monkeypatch.setattr(ci, "_solver_factory", lambda: SlowSolver)
    result = ci.discover_cut_invariants(Circuit(2), budget=Budget(max_seconds=0.03))
    assert event.is_set() and deleted == [True]
    assert result.outcome == "inconclusive" and result.invariants == ()


def test_solver_cleanup_is_inside_the_same_deadline(monkeypatch):
    class LateCleanup:
        def __init__(self, **kwargs):
            pass

        def solve_limited(self, **kwargs):
            return True

        def interrupt(self):
            pass

        def get_model(self):
            return []

        def delete(self):
            time.sleep(0.02)

    monkeypatch.setattr(ci, "_solver_factory", lambda: LateCleanup)
    result = ci.discover_cut_invariants(Circuit(2), budget=Budget(max_seconds=0.01))
    assert result.outcome == "inconclusive" and result.invariants == ()


@pytest.mark.sat
def test_encoder_cleanup_is_checked_before_a_positive_result(monkeypatch):
    def slow_release(self):
        time.sleep(0.03)

    monkeypatch.setattr(ci._BoundedEncoder, "__del__", slow_release, raising=False)
    result = ci.discover_cut_invariants(
        Circuit(1), initial_constants=((0, 0),), budget=Budget(max_seconds=0.01),
    )
    assert result.outcome == "inconclusive" and not result.proved


def test_sat_counterexample_is_replayed_through_concrete_prefix(monkeypatch):
    class BogusModel:
        def __init__(self, **kwargs):
            pass

        def solve_limited(self, **kwargs):
            return True

        def interrupt(self):
            pass

        def get_model(self):
            return []  # Valid domain input zero, but not a violating second witness.

        def delete(self):
            pass

    monkeypatch.setattr(ci, "_solver_factory", lambda: BogusModel)
    with pytest.raises(InternalInconsistency, match="counterexample failed"):
        ci.discover_cut_invariants(Circuit(2))
