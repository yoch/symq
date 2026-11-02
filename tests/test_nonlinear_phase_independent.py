"""Audit #164: supplied certificates against an independent cohort and exact channels."""
from __future__ import annotations

import random

import pytest

from symq.labs import affine_phase as core
from symq.labs.nonlinear_phase_bits import check_nonlinear_phase
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cohort import certificate, make_dephaser, make_pair, support

pytestmark = pytest.mark.sat


def test_independent_cohort_is_sound_complete_for_true_certificates_and_never_claims_difference():
    rng = random.Random(16461)
    equal = proved = refused_wrong = 0
    for _ in range(60):
        dephaser = make_dephaser(rng)
        left, right = make_pair(rng, dephaser)
        offset, columns = support(rng)
        k = max(left.k, right.k)
        cert, _consistent = certificate(left, right, dephaser, offset, columns, k)
        same = same_channel(left, right, dephaser, offset=offset, columns=columns)
        domain = core.AffineSupport(4, offset, columns)
        result = check_nonlinear_phase(left, right, dephaser, cert, support=domain)
        assert result['status'] in ('proved', 'not_proved'), result
        assert (result['status'] == 'proved') == same, result
        equal += same
        proved += result['status'] == 'proved'
        if same and any(cert):
            planes = list(cert)
            j = rng.randrange(k)
            planes[j] = tuple(sorted(set(planes[j]) ^ {0}))
            wrong = check_nonlinear_phase(left, right, dephaser, tuple(planes), support=domain)
            # A wrong candidate on equal channels is a certificate failure, never a difference.
            assert wrong['status'] == 'not_proved' and wrong['obligation'] == 'candidate_phase_bit'
            assert wrong['witness']['source_delta'] != wrong['witness']['candidate_delta']
            refused_wrong += 1
    assert equal >= 20 and proved == equal and refused_wrong >= 10
