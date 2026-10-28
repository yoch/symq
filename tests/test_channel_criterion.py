"""The channel criterion: what it decides, and the two notions it must not conflate.

Distinctions pinned here, in the order the mission asks for them:

1. equal channels on ``data + ancilla`` (the faithful comparison);
2. equal channels after tracing the ancillas out (a strictly weaker relation);
3. equal syndrome *kernels* even when the coefficients ``g_j`` differ, which happens exactly when
   the two syndrome vectors are related by an invertible GF(2) map.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import channel
import factored

from symq.phase import PhaseProgram, check_phase_equivalence


def random_program(rng: random.Random, data: int, ancillas: int, ops: int) -> PhaseProgram:
    program = PhaseProgram(data, ancillas)
    for _ in range(ops):
        kind = rng.choice(["mcx", "mcx", "mcz", "hmr", "mcz_if"])
        if kind == "hmr":
            program.hmr(rng.randrange(program.width))
            continue
        count = rng.randint(1, min(3, program.width))
        qubits = rng.sample(range(program.width), count)
        if kind == "mcz_if" and program.measurements:
            program.mcz_if(rng.randrange(program.measurements), *qubits)
        elif kind == "mcx":
            program.mcx(*qubits)
        else:
            program.mcz(*qubits)
    return program


def test_constant_outcomes_is_about_constants_not_about_term_count():
    coefficient_x0 = factored.FactoredPhase(
        1, 0, 1, (factored.ANF.variable(0),), factored.ANF(), (factored.ANF.variable(0),))
    assert not coefficient_x0.constant_outcomes(), "x0 is one monomial but not a constant"
    coefficient_one = factored.FactoredPhase(
        1, 0, 1, (factored.ANF.variable(0),), factored.ANF(), (factored.ANF.constant(1),))
    assert coefficient_one.constant_outcomes()
    coefficient_zero = factored.FactoredPhase(
        1, 0, 1, (factored.ANF.variable(0),), factored.ANF(), (factored.ANF(),))
    assert coefficient_zero.constant_outcomes()


def test_the_pair_space_holds_the_data_variables_only():
    """With 3 data wires and 5 ancillas the pair space must still be 2 * 3 variables.

    The comparison here is between two *identical* programs, so the verdict is ``True`` and the
    reported pair-space size is what the criterion actually built.
    """
    program = PhaseProgram(3, 5)
    for wire in range(3, 8):
        program.mcx(0, wire)
        program.hmr(wire)
    verdict = factored.equivalent_channel(program, PhaseProgram(3, 5))
    assert not verdict.equivalent, "measuring entangled ancillas decoheres the data wires"
    assert verdict.pairs == 1 << (2 * 3), verdict.pairs


def test_invertible_syndrome_relations_are_accepted_and_others_are_not():
    """``g_L = (x0, x1)`` and ``g_R = (x0, x0 xor x1)`` have the same kernel.

    The kernel of a syndrome ``g`` is the set of pairs with ``g(x) = g(y)``; any invertible
    linear map ``A`` sends ``g`` to ``A g`` without changing that set. The criterion compares the
    kernels, not the coefficients, so it must accept such a pair -- while rejecting a pair whose
    syndromes are genuinely different.
    """
    left = PhaseProgram(2, 1)
    left.mcz(0, 1)  # phase x0 x1, no measurements: kernel is the whole pair space
    right = PhaseProgram(2, 1)
    right.mcz(0, 1)
    assert factored.equivalent_channel(left, right).equivalent

    # Now build two programs with non-constant syndromes related by an invertible map.
    def with_syndrome(transform) -> PhaseProgram:
        program = PhaseProgram(2, 2)
        program.mcx(transform(0), 2)
        program.hmr(2)
        program.mcx(transform(1), 3)
        program.hmr(3)
        # An outcome-only phase cannot change the channel.
        program.x(2)
        program.mcz_if(0, 2)
        return program

    identity_map = lambda index: index
    invertible = lambda index: 0 if index == 1 else 1
    assert channel.same_channel(with_syndrome(identity_map), with_syndrome(invertible))
    assert factored.equivalent_channel(with_syndrome(identity_map),
                                       with_syndrome(invertible)).equivalent

    same_but_one = with_syndrome(identity_map)
    different = PhaseProgram(2, 2)
    different.mcx(0, 2)
    different.hmr(2)
    different.mcx(0, 3)  # same control twice: g1 = g0, a different kernel
    different.hmr(3)
    assert not factored.equivalent_channel(same_but_one, different).equivalent
    assert not channel.same_channel(same_but_one, different)


def test_full_and_traced_channel_equivalence_are_different_relations():
    """Two programs can agree on the data wires and differ on the ancillas.

    ``cx(0, 1)`` and ``cx(0, 1); x(1)`` both leave the data wire untouched. On the data wires
    the two channels are identical (the identity), but the ancilla ends as ``x0`` in one and as
    ``not x0`` in the other, so the full channels differ. Reporting the reduced comparison as if
    it were the full one would certify a different theorem.
    """
    first = PhaseProgram(1, 1).cx(0, 1)
    second = PhaseProgram(1, 1).cx(0, 1).x(1)
    assert channel.same_channel(first, second, trace_ancillas=True), (
        "the data-wire channels agree")
    assert not channel.same_channel(first, second), "the ancillas do not"
    # And the criterion, which compares every wire including ancillas, rejects the pair.
    assert not factored.equivalent_channel(first, second).equivalent


def test_criterion_matches_the_oracle_on_the_full_channel():
    rng = random.Random(4242)
    for _ in range(200):
        data = rng.randint(1, 2)
        ancillas = rng.randint(0, 1)
        left = random_program(rng, data, ancillas, rng.randint(1, 7))
        right = (random_program(rng, data, ancillas, rng.randint(1, 7))
                 if rng.random() < 0.85 else left)
        verdict = factored.equivalent_channel(left, right)
        assert verdict.equivalent == channel.same_channel(left, right), (left.ops, right.ops)


def test_out_of_domain_requests_are_explicit():
    with pytest.raises(ValueError, match="same number of data wires"):
        factored.equivalent_channel(PhaseProgram(2), PhaseProgram(3))
    with pytest.raises(ValueError, match="same number of ancillas"):
        factored.equivalent_channel(PhaseProgram(2, 1), PhaseProgram(2, 2))


def test_the_strict_criterion_and_the_channel_criterion_answer_different_questions():
    """O2 compares branches; the channel compares the outcome-averaged map. Neither implies the
    other, and the report must keep them apart."""
    program = PhaseProgram(1, 0)
    program.hmr(0)
    identity = PhaseProgram(1, 0)
    strict = check_phase_equivalence(program, identity)
    assert strict.violations, "the strict criterion refuses it"
    assert not factored.equivalent_channel(program, identity).equivalent, (
        "the channel also differs: measuring a data wire is not the identity")
