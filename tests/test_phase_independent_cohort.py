"""Audit #166: every #163 route against an independent cohort and the exact channel oracle."""
from __future__ import annotations

import random

import pytest

from symq.labs.affine_phase import AffineSupport
from symq.labs.nonlinear_phase_bits import check_nonlinear_phase
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.labs.phase_discovery import discover_phase_certificate
from symq.labs.phase_factored import check_factored_phase, discover_factored_phase
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.phase_mixing_cohort import certificates, make_case

pytestmark = pytest.mark.sat
DISCOVERIES = {
    'factored': lambda l, r, d, s: discover_factored_phase(l, r, d, support=s),
    'fixed': lambda l, r, d, s: discover_phase_certificate(l, r, d, support=s),
    'adaptive': lambda l, r, d, s: discover_adaptive_phase(l, r, d, support=s),
    'halving+seeds': lambda l, r, d, s: discover_adaptive_phase(
        l, r, d, support=s, initial_degree=0, separator_strategy='halving', source_monomials=True),
}


def test_independent_cohort_never_confuses_refusal_with_difference():
    rng = random.Random(16600)
    equal = 0
    for _ in range(40):
        left, right, d, offset, columns, h = make_case(rng)
        support = AffineSupport(left.width, offset & ~(1 << (left.width - 1)), columns)
        same = same_channel(left, right, d, offset=support.offset, columns=columns)
        equal += same
        planes, factored, _consistent = certificates(left, right, d, support.offset, columns, h)
        # Supplied true certificates: complete and sound.
        assert (check_factored_phase(left, right, d, factored, support=support)['status'] == 'proved') == same
        assert (check_nonlinear_phase(left, right, d, planes, support=support)['status'] == 'proved') == same
        for name, run in DISCOVERIES.items():
            result = run(left, right, d, support)
            assert result['status'] in ('proved', 'different', 'not_proved', 'dictionary_exhausted'), (name, result)
            if result['status'] == 'proved':
                assert same, name
            if result['status'] == 'different':
                assert not same, name
            if same:   # a safe refusal on equal channels is never a difference
                assert result['status'] != 'different', name
        reuse = discover_adaptive_phase(left, right, d, support=support)
        rebuild = discover_adaptive_phase(left, right, d, support=support, reuse_basis=False)
        for key in ('status', 'obligation', 'certificate', 'witness', 'certificate_sha256'):
            assert reuse.get(key) == rebuild.get(key), key
    assert equal >= 15
