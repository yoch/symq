"""A low-degree feature rule is not a universally efficient sparse learner."""
from __future__ import annotations

import pytest

from benchmarks.phase_adaptive import fresh
from benchmarks.phase_separator_frontier import conjunction_family
from symq.labs.phase_adaptive import discover_adaptive_phase
from tests.testkit.affine_phase_oracle import same_channel


@pytest.mark.sat
@pytest.mark.parametrize('degree', (2, 3, 4))
def test_full_degree_monomial_forces_all_signature_words_under_halving(degree):
    left, right, d, support = conjunction_family(degree)
    answer = discover_adaptive_phase(left, right, d, support=support,
                                      separator_strategy='halving', max_samples=1 << degree)
    assert answer['status'] == 'proved' and answer['sample_count'] == 1 << degree
    assert any(((1 << degree) - 1) in plane for plane in answer['certificate'])
    fresh(left, right, d, support, answer)
    # Low-dimensional complete-channel oracle; larger cases use exact symbolic proofs.
    if degree == 2:
        assert same_channel(left, right, d, columns=support.columns)
    for event in answer['growth']:
        assert event['added_mask'].bit_count() <= len(event['signature_words']).bit_length() - 1


@pytest.mark.sat
def test_low_sample_cap_must_refuse_the_high_degree_conjunction():
    left, right, d, support = conjunction_family(7)
    answer = discover_adaptive_phase(left, right, d, support=support,
                                      separator_strategy='halving', max_samples=32)
    assert answer['status'] == 'inconclusive'
    assert answer['reason'] == 'adaptive sample limit'
    assert answer['sample_count'] == 32 and not answer['fresh_verified']
    assert answer['certificate'] is None and answer['witness'] is None
