"""Source structure is an optional feature seed, not a substitute for exact proof."""
from __future__ import annotations

import random
from fractions import Fraction
from itertools import product

import pytest

from benchmarks.phase_adaptive import fresh
from benchmarks.phase_separator_frontier import conjunction_family
from symq.errors import InternalInconsistency
from symq.labs import phase_discovery, phase_separator
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.labs.phase_separator import source_monomial_seeds
from symq.resources import Budget, Guard, VerificationSession
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def test_source_monomial_factorization_is_exact_and_complete_for_eligible_products():
    rng = random.Random(16606)
    checked = 0
    for width in range(1, 7):
        for _ in range(40):
            signature = [frozenset({rng.randrange(1 << width)}) if rng.randrange(3)
                         else frozenset(rng.sample(range(1 << width), rng.randrange(min(4, 1 << width) + 1)))
                         for _ in range(12)]
            delta = {frozenset({x}): 1 for x in range(1, 1 << width)}
            rows = source_monomial_seeds(signature, delta, Guard(Budget(max_seconds=5)), 256)
            targets = {r['source_monomial'] for r in rows}
            for target in range(1, 1 << width):
                union = 0
                for polynomial in signature:
                    if len(polynomial) == 1:
                        m = next(iter(polynomial))
                        if m & ~target == 0:
                            union |= m
                assert (target in targets) == (union == target)
            for row in rows:
                for assignment in range(1 << width):
                    actual = 1
                    for i, polynomial in enumerate(signature):
                        if row['feature'] >> i & 1:
                            actual &= sum(m & assignment == m for m in polynomial) % 2
                    expected = int(assignment & row['source_monomial'] == row['source_monomial'])
                    assert actual == expected
                checked += 1
    assert checked > 1000


@pytest.mark.sat
@pytest.mark.parametrize('degree', (3, 7, 16, 32))
def test_one_high_degree_source_factor_avoids_a_dense_degree_layer(degree):
    left, right, d, support = conjunction_family(degree if degree <= 16 else 16)
    if degree == 32:
        from symq.labs.affine_phase import AffineSupport
        from symq.labs.dyadic_phase import DyadicPhaseProgram
        from symq.phase import PhaseProgram

        left, right = DyadicPhaseProgram(65, k=3), DyadicPhaseProgram(65, k=3)
        d = PhaseProgram(65, 1)
        for i in range(32):
            d.ccx(2 * i, 2 * i + 1, 65).hmr(65)
        left.mcx(*range(64), 64).phase(64, Fraction(1, 8)).mcx(*range(64), 64)
        support = AffineSupport(65, 0, tuple(1 << i for i in range(64)))
    # Same linear seed as the unseeded learner, plus one structurally derived term.
    result = discover_adaptive_phase(left, right, d, support=support,
                                      source_monomials=True, separator_strategy='halving', max_samples=64)
    assert result['status'] == 'proved' and result['fresh_verified']
    assert len(result['source_seed_records']) == 1
    assert result['source_seed_records'][0]['feature'] == (1 << degree) - 1
    assert result['feature_count'] == degree + 2
    assert result['sample_count'] <= degree + 2 and not result['growth']
    fresh(left, right, d, support, result)
    # An explicitly smaller constant seed uses only the known feature and constant.
    minimal_seed = discover_adaptive_phase(left, right, d, support=support, initial_degree=0,
                                           source_monomials=True, separator_strategy='halving', max_samples=2)
    assert minimal_seed['status'] == 'proved' and minimal_seed['sample_count'] == 2
    assert minimal_seed['feature_count'] == 2
    fresh(left, right, d, support, minimal_seed)


@pytest.mark.sat
def test_all_aggregate_functions_keep_carries_and_cross_predicate_cancellation():
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        result = discover_adaptive_phase(left, right, d, support=support, source_monomials=True)
        assert result['status'] == 'proved'
        assert same_channel(left, right, d, columns=support.columns)
        fresh(left, right, d, support, result)
    left.phase(0, Fraction(1, 4))
    bad = discover_adaptive_phase(left, right, d, support=support, source_monomials=True)
    assert bad['status'] == 'different' and bad['obligation'] == 'signature_collision'
    assert not same_channel(left, right, d, columns=support.columns)


@pytest.mark.sat
def test_source_seeds_cannot_bypass_fresh_verification_or_strict_caps(monkeypatch):
    left, right, d, support = conjunction_family(5)
    with monkeypatch.context() as context:
        context.setattr(phase_discovery, '_fresh_check', lambda *args: {'status': 'inconclusive'})
        answer = discover_adaptive_phase(left, right, d, support=support, source_monomials=True)
        assert answer['status'] == 'inconclusive' and not answer['fresh_verified']
        assert answer['certificate'] is None
    with monkeypatch.context() as context:
        context.setattr(phase_separator, 'source_monomial_seeds',
                        lambda *args: [{'feature': True, 'source_monomial': 1}])
        with pytest.raises(InternalInconsistency):
            discover_adaptive_phase(left, right, d, support=support, source_monomials=True)
    capped = discover_adaptive_phase(left, right, d, support=support,
                                     initial_degree=0, source_monomials=True, max_features=1)
    assert capped['status'] == 'inconclusive' and capped['certificate'] is None
    assert capped['witness'] is None
    with VerificationSession(Budget(max_terms=1)):
        assert discover_adaptive_phase(left, right, d, support=support,
                                        source_monomials=True)['status'] == 'inconclusive'
    with pytest.raises(ValueError):
        discover_adaptive_phase(left, right, d, support=support, source_monomials=1)
