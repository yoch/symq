"""Exact, source-pinned bilinear synthesis tests on independent oracles.

The original Kaggle inputs by James Barlow are public open-set fixtures;
these results are not a blind agent benchmark or a Kaggle score claim.
"""
from __future__ import annotations

import random

import pytest

from benchmarks.kmb import decode, encode
from symq import Budget, check_equivalence
from symq.circuit import Circuit
from symq.generators import gf2n
from symq.generators.bilinear_optimization import (
    MAX_SCHEDULE_TERMS,
    certify_decomposition,
)


@pytest.mark.parametrize(
    "n,modulus,rank,expected_cx",
    [(4, 0x13, 9, 30), (6, 0x49, 15, 82)],
)
def test_tower_factors_emit_with_shared_frames(n, modulus, rank, expected_cx):
    factors = gf2n.tower_factors(n, modulus=modulus)
    certify_decomposition(n, factors, modulus)
    plain = gf2n.emit(n, factors, strategy="pivot")
    optimized = gf2n.emit(n, factors, strategy="pivot-scheduled")
    assert optimized.ccx == len(factors) == rank and optimized.width == 3 * n
    assert optimized.cx == expected_cx and optimized.cx <= plain.cx
    assert optimized.fold_cx <= optimized.cx
    assert decode(encode(optimized.circuit)).gates == optimized.circuit.gates
    for a in range(1 << n):
        for b in range(1 << n):
            product = gf2n.gf_mul(n, a, b, modulus=modulus)
            for target in (0, (1 << n) - 1, 1, ((a << 1) ^ b) & ((1 << n) - 1)):
                x = a | (b << n) | (target << (2 * n))
                assert optimized.circuit.run(x) == a | (b << n) | ((target ^ product) << (2 * n))


@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("method", sorted(gf2n.DECOMPOSITIONS))
def test_pivot_synthesis_of_existing_multipliers(n, method):
    reference = gf2n.multiplier(n, method)
    plain = gf2n.multiplier(n, method, strategy="pivot")
    scheduled = gf2n.multiplier(n, method, strategy="pivot-scheduled")
    for x in range(1 << (3 * n)):
        expected = gf2n.multiplier_expected_output(n, x)
        assert reference.run(x) == plain.run(x) == scheduled.run(x) == expected
    assert len([g for g in scheduled.gates if g.name == "ccx"]) <= len([
        g for g in reference.gates if g.name == "ccx"
    ])
    assert scheduled.counts().get("cx", 0) <= plain.counts().get("cx", 0)


@pytest.mark.parametrize("n", [5, 6, 8, 12, 16, 24])
def test_pivot_schedule_larger_circuits_randomized(n):
    rng = random.Random(0xB111 + n)
    for method in ("schoolbook", "karatsuba", "rank_floor"):
        circuit = gf2n.multiplier(n, method, strategy="pivot-scheduled")
        for _ in range(12 if n >= 12 else 50):
            x = rng.randrange(1 << (3 * n))
            assert circuit.run(x) == gf2n.multiplier_expected_output(n, x), (n, method, x)


def test_certification_rejects_mutants_wrong_polynomial_and_invalid_masks():
    from symq.generators.gf2n import Term

    terms = gf2n.tower_factors(6, modulus=0x49)
    certify_decomposition(6, terms, 0x49)
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(6, terms, 0x43)
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(6, terms[:-1], 0x49)
    altered = list(terms)
    altered[0] = Term(terms[0].left, terms[0].right, terms[0].into ^ 1)
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(6, altered, 0x49)
    assert gf2n.is_irreducible(6, 0x49) and gf2n.is_irreducible(6, 0x43)
    assert not gf2n.is_irreducible(4, 0x15)
    with pytest.raises(ValueError, match="irreducible"):
        certify_decomposition(6, terms, 0x45)
    with pytest.raises(ValueError, match="invalid bilinear factor"):
        gf2n.emit(6, [Term(0, 1, 1)], strategy="pivot")
    with pytest.raises(ValueError, match="invalid bilinear factor"):
        gf2n.emit(6, [Term(True, 1, 1)], strategy="pivot")
    with pytest.raises(ValueError, match="invalid bilinear factor"):
        gf2n.emit(6, [Term(1, 64, 1)], strategy="pivot")
    with pytest.raises(ValueError, match="strategy"):
        gf2n.emit(6, terms, strategy="unsupported")
    with pytest.raises(ValueError, match="share"):
        gf2n.emit(6, terms, share=True, strategy="pivot")
    with pytest.raises(ValueError, match="at most"):
        gf2n.emit(6, [terms[0]] * (MAX_SCHEDULE_TERMS + 1), strategy="pivot-scheduled")


def test_in_context_full_permutation_and_negative_mutant():
    """Whole-circuit context; does not claim a local relational SAT cut theorem."""
    from symq.generators.gf2n import Term

    n, modulus = 4, 0x13
    rank_terms = gf2n.tower_factors(n, modulus=modulus)
    baseline_terms = [
        Term(1 << i, 1 << j, gf2n.gf_mul(n, 1 << i, 1 << j, modulus=modulus))
        for i in range(n) for j in range(n)
    ]
    baseline = gf2n.emit(n, baseline_terms, strategy="incidence").circuit
    optimized = gf2n.emit(n, rank_terms, strategy="pivot-scheduled").circuit
    prefix = Circuit(3 * n).cx(0, 8).cx(9, 1).cx(2, 10)
    suffix = Circuit(3 * n).ccx(4, 1, 11).cx(11, 0)
    left = Circuit(3 * n, [*prefix.gates, *baseline.gates, *suffix.gates])
    right = Circuit(3 * n, [*prefix.gates, *optimized.gates, *suffix.gates])
    result = check_equivalence(left, right, backend="zdd", budget=Budget(max_seconds=20))
    assert result.equivalent
    mutant = Circuit(right.width, list(right.gates))
    mutant.gates.pop()
    bad = check_equivalence(left, mutant, backend="zdd", budget=Budget(max_seconds=20))
    assert not bad.equivalent
    assert left.run(bad.witness) != mutant.run(bad.witness)
