"""Exact SAT HMR channel-kernel pilot against independent Kraus/density oracle."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import channel
import channel_sat

from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram, check_phase_equivalence
from symq.resources import Budget
from symq.sat import available

pytestmark = pytest.mark.skipif(not available(), reason="requires optional PySAT")


def random_program(rng, data, ancillas, operations):
    p = PhaseProgram(data, ancillas)
    for _ in range(operations):
        kind = rng.choice(["mcx", "mcx", "mcz", "hmr", "mcz_if"])
        if kind == "hmr":
            p.hmr(rng.randrange(p.width))
            continue
        count = rng.randint(1, min(p.width, 3))
        wires = rng.sample(range(p.width), count)
        if kind == "mcz_if" and p.measurements:
            p.mcz_if(rng.randrange(p.measurements), *wires)
        elif kind == "mcx":
            p.mcx(*wires)
        else:
            p.mcz(*wires)
    return p


def test_an_outcome_only_global_sign_is_channel_equivalent_but_not_branch_equivalent():
    left = PhaseProgram(1, 1)
    left.x(1)
    left.hmr(1)  # g(x)=1, a global (-1)^m that disappears in the channel
    right = PhaseProgram(1, 1)
    assert not check_phase_equivalence(left, right).equivalent
    assert channel.same_channel(left, right)
    proof = channel_sat.check_channel_sat(left, right, budget=Budget(max_seconds=10))
    assert proof.outcome == "equivalent"
    assert proof.queries == 3


def test_kernel_difference_returns_independent_pair():
    left = PhaseProgram(1, 1)
    left.cx(0, 1)
    left.hmr(1)     # dephases coherence between |0> and |1>
    right = PhaseProgram(1, 1)
    proof = channel_sat.check_channel_sat(left, right)
    assert proof.outcome == "different" and proof.reason == "kernel"
    assert proof.witness in {(0, 1), (1, 0)}
    assert not channel.same_channel(left, right)
    x, y = proof.witness
    assert channel.coherence_image(left, x, y, trace_ancillas=False) != (
        channel.coherence_image(right, x, y, trace_ancillas=False)
    ), "the reported SAT cut-pair must also differ in an independent exact Kraus oracle"


def test_phase_difference_and_output_mismatch_have_distinct_witness_types():
    phase = channel_sat.check_channel_sat(PhaseProgram(1).z(0), PhaseProgram(1))
    assert phase.outcome == "different" and phase.reason == "relative_phase"
    assert len(phase.witness) == 2
    x, y = phase.witness
    assert channel.coherence_image(PhaseProgram(1).z(0), x, y, trace_ancillas=False) != (
        channel.coherence_image(PhaseProgram(1), x, y, trace_ancillas=False)
    )
    changed = channel_sat.check_channel_sat(PhaseProgram(1).x(0), PhaseProgram(1))
    assert changed.outcome == "different" and changed.reason == "outputs"
    assert len(changed.witness) == 1
    (x,) = changed.witness
    assert channel.coherence_image(PhaseProgram(1).x(0), x, x, trace_ancillas=False) != (
        channel.coherence_image(PhaseProgram(1), x, x, trace_ancillas=False)
    )


@pytest.mark.parametrize("seed", range(35))
def test_full_channel_sat_agrees_with_independent_density_oracle(seed):
    rng = random.Random(2026102800 + seed)
    data, ancillas = rng.randint(1, 2), rng.randint(0, 1)
    left = random_program(rng, data, ancillas, rng.randint(0, 7))
    right = left if rng.random() < .20 else random_program(rng, data, ancillas, rng.randint(0, 7))
    verdict = channel_sat.check_channel_sat(left, right, budget=Budget(max_seconds=10))
    assert verdict.outcome != "inconclusive", (seed, verdict)
    assert (verdict.outcome == "equivalent") == channel.same_channel(left, right), (
        seed, verdict, left.ops, right.ops)



# Public HMR source: andigu/uncompute@64b5a13aa249f1360846657392e6c66817b26d0f
# (Apache-2.0), uncompute/builder.py::and_compute/and_release and
# uncompute/gadgets/arith.py::booth_columns_release.
# This is a hand-built miniature of that *documented* release idiom, not
# an import of that project or a claim to run its large real compiled circuit.
def _public_and_release_fragment(*, correct_second: bool = True):
    implementation = PhaseProgram(3, 1)
    implementation.ccx(0, 1, 3).cx(3, 2)
    outcome_0 = implementation.hmr(3)
    implementation.cz_if(outcome_0, 0, 1)
    implementation.ccx(1, 2, 3).cx(3, 0)
    outcome_1 = implementation.hmr(3)
    if correct_second:
        implementation.cz_if(outcome_1, 1, 2)
    specification = PhaseProgram(3, 1).ccx(0, 1, 2).ccx(1, 2, 0)
    return implementation, specification


def test_public_gadget_two_temporary_and_releases():
    """Two actual public temporary-AND release patterns chained in one fragment."""
    implementation, specification = _public_and_release_fragment()
    assert implementation.measurements == 2
    assert channel.same_channel(implementation, specification)
    equivalent = channel_sat.check_channel_sat(
        implementation, specification, budget=Budget(max_seconds=10)
    )
    assert equivalent.outcome == "equivalent" and equivalent.queries == 3
    assert check_phase_equivalence(implementation, specification).equivalent


def test_public_gadget_missing_second_phase_correction_is_detected():
    implementation, specification = _public_and_release_fragment(correct_second=False)
    assert not channel.same_channel(implementation, specification)
    different = channel_sat.check_channel_sat(
        implementation, specification, budget=Budget(max_seconds=10)
    )
    assert different.outcome == "different"
    assert different.reason in ("kernel", "relative_phase")
    assert different.witness is not None and len(different.witness) == 2
    x, y = different.witness
    assert channel.coherence_image(implementation, x, y, trace_ancillas=False) != (
        channel.coherence_image(specification, x, y, trace_ancillas=False)
    )


def test_tiny_budget_and_cnf_budget_are_not_proofs():
    a, b = PhaseProgram(2), PhaseProgram(2)
    tiny = channel_sat.check_channel_sat(a, b, budget=Budget(max_seconds=1e-9))
    assert tiny.outcome == "inconclusive" and tiny.reason == "timeout"
    limited = channel_sat.check_channel_sat(a, b, max_clauses=1)
    assert limited.outcome == "inconclusive" and limited.reason == "limit"


def test_malformed_program_and_dimensional_mismatch_are_explicit():
    with pytest.raises(ValueError, match="matching"):
        channel_sat.check_channel_sat(PhaseProgram(1, 1), PhaseProgram(1, 0))
    bad = PhaseProgram(1)
    bad.ops.append(object())
    with pytest.raises(UnsupportedOperation):
        channel_sat.check_channel_sat(bad, PhaseProgram(1))



def test_clause_guard_stops_during_encoding_without_creating_solver(monkeypatch):
    """A clause cap must stop CNF emission, not just reject its finished huge list."""
    calls = []
    original = channel_sat._BoundedEncoder.add

    def count(self, *literals):
        calls.append(len(self.clauses))
        return original(self, *literals)

    def no_solver():
        raise AssertionError("solver must not start after a clause cap")

    monkeypatch.setattr(channel_sat._BoundedEncoder, "add", count)
    monkeypatch.setattr(channel_sat, "_solver_factory", no_solver)
    result = channel_sat.check_channel_sat(PhaseProgram(2), PhaseProgram(2), max_clauses=1)
    assert result.outcome == "inconclusive" and result.reason == "limit"
    assert result.clauses <= 1
    assert calls and max(calls) <= 1


def test_clause_budget_is_for_the_entire_three_query_proof():
    left, right = PhaseProgram(2), PhaseProgram(2)
    full = channel_sat.check_channel_sat(left, right, budget=Budget(max_seconds=10))
    assert full.outcome == "equivalent" and full.queries == 3
    assert full.clauses > 5
    capped = channel_sat.check_channel_sat(
        left, right, budget=Budget(max_seconds=10), max_clauses=full.clauses - 1,
    )
    assert capped.outcome == "inconclusive" and capped.reason == "limit"
    assert capped.clauses <= full.clauses - 1


def test_shared_factorization_deadline_does_not_restart_on_second_program(monkeypatch):
    """Measured global deadline is not two separately refreshed factor() deadlines."""
    import time

    original = channel_sat.factor
    calls = []

    def delayed(program, budget=None):
        calls.append(budget.max_seconds)
        time.sleep(0.025)
        return original(program, budget)

    monkeypatch.setattr(channel_sat, "factor", delayed)
    result = channel_sat.check_channel_sat(
        PhaseProgram(1), PhaseProgram(1), budget=Budget(max_seconds=0.040),
    )
    assert result.outcome == "inconclusive" and result.reason == "timeout"
    assert calls
    if len(calls) > 1:
        assert calls[1] < calls[0]  # the second pass sees the remaining time, not a fresh 40ms


def test_late_three_query_result_cannot_certify_after_deadline(monkeypatch):
    import time

    def late(*args, **kwargs):
        time.sleep(0.012)
        return channel_sat.ChannelSATResult(
            "equivalent", "none", clauses=1, variables=2, queries=1,
        )

    monkeypatch.setattr(channel_sat, "_query", late)
    result = channel_sat.check_channel_sat(
        PhaseProgram(1), PhaseProgram(1), budget=Budget(max_seconds=0.025),
    )
    assert result.outcome == "inconclusive" and result.reason == "timeout"


def test_cnf_capacity_checks_do_not_turn_a_real_difference_into_equivalent():
    a = PhaseProgram(2).cx(0, 1)
    b = PhaseProgram(2)
    for limit in (1, 2, 5):
        verdict = channel_sat.check_channel_sat(a, b, max_clauses=limit)
        assert verdict.outcome == "inconclusive" and verdict.reason == "limit"
        assert verdict.clauses <= limit
    proved = channel_sat.check_channel_sat(a, b, budget=Budget(max_seconds=10))
    assert proved.outcome == "different" and proved.reason == "outputs"
