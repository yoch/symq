"""Low-degree refinement stays behind source replay, rank and fresh-check gates."""
from __future__ import annotations

import random
from fractions import Fraction
from itertools import product
from types import SimpleNamespace

import pytest

from symq.errors import InternalInconsistency, ResourceLimitExceeded
from symq.labs import nonlinear_phase_bits, phase_adaptive, phase_discovery, phase_separator
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.resources import Budget, Guard, VerificationSession
from tests.test_phase_adaptive import check_growth
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def assert_bound(result):
    check_growth(result)
    for event in result['growth']:
        assert event['added_mask'].bit_count() <= len(event['signature_words']).bit_length() - 1


@pytest.mark.sat
def test_all_two_signature_functions_with_halving_and_fresh_oracle_checks():
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        result = discover_adaptive_phase(left, right, d, support=support, separator_strategy='halving')
        assert result['status'] == 'proved' and result['fresh_verified']
        assert same_channel(left, right, d, columns=support.columns)
        planes = tuple(tuple(p) for p in result['certificate'])
        fresh = nonlinear_phase_bits.check_nonlinear_phase(left, right, d, planes, support=support)
        assert fresh['status'] == 'proved' and fresh['source_sha256'] == result['source_sha256']
        assert result['feature_count'] <= 4 and result['source_preparations'] == 1
        assert_bound(result)


def test_halving_completion_retains_all_old_samples_and_rank_evidence(monkeypatch):
    monkeypatch.setattr(phase_discovery, '_sample', lambda p, z, _c, _g: p[z])
    symbolic = SimpleNamespace(_bool=lambda masks, _h, _g: masks[0])
    rng = random.Random(16603)
    for width in range(1, 9):
        for _ in range(20):
            words = rng.sample(range(1 << width), rng.randint(1, min(64, 1 << width)))
            samples = [{'parameter': i, 'input': i, 'signature': word, 'delta': rng.randrange(256)}
                       for i, word in enumerate(words)]
            masks = [0] + [1 << i for i in range(width)]
            initial = list(masks)
            features = list(masks)
            result = {'basis_rebuilds': 0, 'growth': [], 'initial_dictionary': initial, 'samples': samples}
            basis = phase_adaptive._complete(samples, masks, features, None, samples, None,
                                             symbolic, None, Guard(Budget(max_seconds=5)),
                                             512, result, 'halving')
            result['dictionary'] = sorted(masks)
            coefficients = basis.solution()
            for sample in samples:
                actual = 0
                for mask, coefficient in zip(masks, coefficients):
                    if sample['signature'] & mask == mask:
                        actual ^= coefficient
                assert actual == sample['delta']
            assert_bound(result)


@pytest.mark.sat
def test_original_default_unchanged_and_halving_collision_is_real():
    left, right, d, support = fixture((0, 0, 0, 1))
    implicit = discover_adaptive_phase(left, right, d, support=support)
    explicit = discover_adaptive_phase(left, right, d, support=support, separator_strategy='greedy')
    for key in ('certificate', 'dictionary', 'samples', 'growth', 'rank', 'rounds', 'source_sha256'):
        assert implicit[key] == explicit[key]
    left.phase(0, Fraction(1, 4))
    wrong = discover_adaptive_phase(left, right, d, support=support, separator_strategy='halving')
    assert wrong['status'] == 'different'
    assert not same_channel(left, right, d, columns=support.columns)
    a, b = wrong['witness']['left'], wrong['witness']['right']
    assert a['signature'] == b['signature'] and a['delta'] != b['delta']


@pytest.mark.sat
def test_halving_helper_is_untrusted_and_caps_never_mean_difference(monkeypatch):
    left, right, d, support = fixture((0, 0, 0, 1))
    for fake in (0, True, -1, 1 << 128):
        with monkeypatch.context() as context:
            context.setattr(phase_separator, 'halving_separator', lambda *args, v=fake: v)
            with pytest.raises(InternalInconsistency):
                discover_adaptive_phase(left, right, d, support=support, separator_strategy='halving')
    for options in ({'max_features': 3}, {'max_samples': 1}, {'max_rounds': 1}):
        result = discover_adaptive_phase(left, right, d, support=support,
                                          separator_strategy='halving', **options)
        assert result['status'] == 'inconclusive' and result['certificate'] is None
        assert result['witness'] is None and not result['fresh_verified']
    with VerificationSession(Budget(max_terms=1)):
        assert discover_adaptive_phase(left, right, d, support=support,
                                        separator_strategy='halving')['status'] == 'inconclusive'


@pytest.mark.sat
def test_halving_does_not_reset_deadline_or_trust_a_fake_fresh_check(monkeypatch):
    left, right, d, support = fixture((0, 0, 0, 1))
    real_fresh, real_clock = phase_discovery._fresh_check, Guard.check_time
    expired = [False]

    def clock(self):
        if expired[0]:
            raise ResourceLimitExceeded('post-fresh expiry', 1, 2)
        return real_clock(self)

    def expire(*args):
        result = real_fresh(*args)
        expired[0] = True
        return result

    with monkeypatch.context() as context:
        context.setattr(Guard, 'check_time', clock)
        context.setattr(phase_discovery, '_fresh_check', expire)
        result = discover_adaptive_phase(left, right, d, support=support, separator_strategy='halving')
        assert result['status'] == 'inconclusive' and not result['fresh_verified']
        assert result['certificate'] is None
    with monkeypatch.context() as context:
        context.setattr(phase_discovery, '_fresh_check', lambda *args: {'status': 'proved'})
        with pytest.raises(InternalInconsistency):
            discover_adaptive_phase(left, right, d, support=support, separator_strategy='halving')


def test_separator_option_is_closed():
    left, right, d, support = fixture()
    for invalid in (True, None, 'auto', 1):
        with pytest.raises(ValueError):
            discover_adaptive_phase(left, right, d, support=support, separator_strategy=invalid)
