"""Exact SAT HMR channel-kernel pilot against independent Kraus/density oracle."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import channel
import channel_sat
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


def test_phase_difference_and_output_mismatch_have_distinct_witness_types():
    phase = channel_sat.check_channel_sat(PhaseProgram(1).z(0), PhaseProgram(1))
    assert phase.outcome == "different" and phase.reason == "relative_phase"
    assert len(phase.witness) == 2
    changed = channel_sat.check_channel_sat(PhaseProgram(1).x(0), PhaseProgram(1))
    assert changed.outcome == "different" and changed.reason == "outputs"
    assert len(changed.witness) == 1


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
    with pytest.raises(Exception):
        channel_sat.check_channel_sat(bad, PhaseProgram(1))
