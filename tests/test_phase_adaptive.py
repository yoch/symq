"""Adaptive dictionaries: exact rank growth, independent channels, fail-closed paths."""
from __future__ import annotations

import random
from fractions import Fraction
from itertools import product

import pytest

from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
from symq.labs import kraus_graph, nonlinear_phase_bits, phase_discovery
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_adaptive import _separator, discover_adaptive_phase
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard, VerificationSession
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def check_growth(result):
    """Independent arithmetic check of every claimed rank-breaking column."""
    masks = list(result['initial_dictionary'])
    for event in result['growth']:
        feature_xor = label_xor = 0
        signatures = []
        for index in event['sample_indices']:
            sample = result['samples'][index]
            signatures.append(sample['signature'])
            feature_xor ^= sum(int(sample['signature'] & mask == mask) << j
                               for j, mask in enumerate(masks))
            label_xor ^= sample['delta']
        assert feature_xor == 0 and label_xor == event['xor_labels'] != 0
        assert signatures == event['signature_words']
        mask = event['added_mask']
        assert mask not in masks
        assert sum(word & mask == mask for word in signatures) % 2 == 1
        assert event['rank_after'] > event['rank_before']
        masks.append(mask)
    assert sorted(masks) == result['dictionary']


def test_separator_exhaustive_sets_and_deletion_minimality():
    for width in range(1, 5):
        for members in range(1, 1 << (1 << width)):
            words = tuple(x for x in range(1 << width) if members >> x & 1)
            result = _separator(words, lambda: None)
            assert sum(x & result == result for x in words) % 2 == 1
            for q in range(width):
                if result >> q & 1:
                    reduced = result ^ (1 << q)
                    assert sum(x & reduced == reduced for x in words) % 2 == 0


def test_separator_wide_and_invalid_inputs_and_budget_callback():
    rng = random.Random(166)
    for width in (8, 24, 48, 128, 256):
        for _ in range(100):
            words = tuple(sorted({rng.getrandbits(width) for _ in range(rng.randrange(1, 70))}))
            mask = _separator(words, lambda: None)
            assert sum(x & mask == mask for x in words) % 2 == 1
    for invalid in ((), (1, 1), (True,), (-1,), [0]):
        with pytest.raises(ValueError):
            _separator(invalid, lambda: None)

    def expired():
        raise TimeoutError('injected expiration')

    with pytest.raises(TimeoutError):
        _separator((0, 1, 2, 3), expired)


@pytest.mark.sat
def test_all_two_signature_phase_functions_are_discovered_from_linear_seeds():
    grew = 0
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        result = discover_adaptive_phase(left, right, d, support=support)
        assert result['status'] == 'proved' and result['fresh_verified']
        assert result['feature_count'] <= 4 and result['sample_count'] <= 4
        assert result['source_preparations'] == 1
        assert same_channel(left, right, d, columns=support.columns)
        cert = tuple(tuple(p) for p in result['certificate'])
        again = nonlinear_phase_bits.check_nonlinear_phase(left, right, d, cert, support=support)
        assert again['status'] == 'proved' and again['source_sha256'] == result['source_sha256']
        check_growth(result)
        grew += bool(result['growth'])
    assert grew == 192


@pytest.mark.sat
def test_same_fibre_collision_is_a_real_channel_difference():
    left, right, d, support = fixture((0, 1, 2, 3))
    left.phase(0, Fraction(1, 4))
    result = discover_adaptive_phase(left, right, d, support=support, max_features=16)
    assert result['status'] == 'different' and result['obligation'] == 'signature_collision'
    a, b = result['witness']['left'], result['witness']['right']
    assert a['signature'] == b['signature'] and a['delta'] != b['delta']
    assert not same_channel(left, right, d, columns=support.columns)
    assert result['certificate'] is None and not result['fresh_verified']


@pytest.mark.sat
def test_feature_round_and_sample_caps_do_not_become_inequivalence():
    left, right, d, support = fixture((0, 0, 0, 1))
    for options in ({'initial_degree': 0, 'max_features': 1}, {'max_rounds': 1}, {'max_samples': 1}):
        result = discover_adaptive_phase(left, right, d, support=support, **options)
        assert result['status'] == 'inconclusive'
        assert result['certificate'] is None and result['witness'] is None
        assert not result['fresh_verified']
    assert same_channel(left, right, d, columns=support.columns)


def test_output_difference_and_constant_signature_no_extra_backend_needed():
    left, right, d, support = fixture((0, 0, 0, 0))
    left.x(0)
    result = discover_adaptive_phase(left, right, d, support=support)
    assert result['status'] == 'different' and result['obligation'] == 'outputs'
    empty = DyadicPhaseProgram(2, k=2)
    result = discover_adaptive_phase(empty, empty, PhaseProgram(2))
    assert result['status'] == 'proved' and result['dictionary'] == [0]


@pytest.mark.sat
def test_offsets_unreachable_signatures_and_alternative_seed_dictionaries():
    from symq.labs.affine_phase import AffineSupport

    # h=(x0,x0): only 00 and 11 are reachable. The physical support has offset1.
    d = PhaseProgram(2, 1).cx(0, 2)
    d.hmr(2)
    d.cx(0, 2).hmr(2)
    left, right = DyadicPhaseProgram(2, k=2).s(0), DyadicPhaseProgram(2, k=2)
    domain = AffineSupport(2, 1, (3,))
    for seed in ((0,), (0, 1), (0, 2)):
        result = discover_adaptive_phase(left, right, d, support=domain, initial_dictionary=seed)
        assert result['status'] == 'proved'
        check_growth(result)
        assert same_channel(left, right, d, offset=1, columns=(3,))


@pytest.mark.sat
def test_hostile_separator_and_fresh_checker_are_not_authorities(monkeypatch):
    import symq.labs.phase_adaptive as adaptive

    left, right, d, support = fixture((0, 0, 0, 1))
    with monkeypatch.context() as context:
        context.setattr(adaptive, '_separator', lambda *args: 0)
        with pytest.raises(InternalInconsistency):
            discover_adaptive_phase(left, right, d, support=support)
    for status in ('inconclusive', 'unsupported'):
        with monkeypatch.context() as context:
            context.setattr(phase_discovery, '_fresh_check', lambda *args, s=status: {'status': s})
            result = discover_adaptive_phase(left, right, d, support=support)
            assert result['status'] == status and not result['fresh_verified']
            assert result['certificate'] is None
    with monkeypatch.context() as context:
        context.setattr(phase_discovery, '_fresh_check', lambda *args: {'status': 'proved'})
        with pytest.raises(InternalInconsistency):
            discover_adaptive_phase(left, right, d, support=support)


@pytest.mark.sat
def test_clock_after_success_and_mutation_after_snapshot(monkeypatch):
    left, right, d, support = fixture((0, 0, 0, 1))
    old_prepare = phase_discovery._prepare

    def mutate(*args):
        prepared = old_prepare(*args)
        left.gates.clear()
        d.ops.clear()
        return prepared

    with monkeypatch.context() as context:
        context.setattr(phase_discovery, '_prepare', mutate)
        result = discover_adaptive_phase(left, right, d, support=support)
        assert result['status'] == 'proved' and result['growth']
    left, right, d, support = fixture((0, 0, 0, 1))
    real_fresh, real_clock = phase_discovery._fresh_check, Guard.check_time
    expired = [False]

    def clock(self):
        if expired[0]:
            raise ResourceLimitExceeded('injected deadline', 1, 2)
        return real_clock(self)

    def expire(*args):
        answer = real_fresh(*args)
        expired[0] = True
        return answer

    with monkeypatch.context() as context:
        context.setattr(Guard, 'check_time', clock)
        context.setattr(phase_discovery, '_fresh_check', expire)
        result = discover_adaptive_phase(left, right, d, support=support)
        assert result['status'] == 'inconclusive' and not result['fresh_verified']
        assert result['certificate'] is None


def test_invalid_options_inherited_caps_and_missing_solver(monkeypatch):
    left, right, d, support = fixture()
    for options in ({'max_features': True}, {'max_samples': 0}, {'max_rounds': 4098},
                    {'initial_degree': -1}, {'initial_dictionary': (0, True)}):
        with pytest.raises(ValueError):
            discover_adaptive_phase(left, right, d, support=support, **options)
    with VerificationSession(Budget(max_bytes=1)), pytest.raises(ValueError):
        discover_adaptive_phase(left, right, d, support=support)
    with VerificationSession(Budget(max_terms=1)):
        assert discover_adaptive_phase(left, right, d, support=support)['status'] == 'inconclusive'
    result = discover_adaptive_phase(left, right, d, support=support, budget=Budget(max_seconds=1e-12))
    assert result['status'] == 'inconclusive' and result['certificate'] is None

    def absent():
        raise SatUnavailable('injected missing SAT')

    monkeypatch.setattr(kraus_graph, '_new_solver', absent)
    assert discover_adaptive_phase(left, right, d, support=support)['status'] == 'unsupported'


def test_greedy_separator_is_not_misrepresented_as_minimum_degree():
    words = (2, 3, 4, 5, 6, 7, 8, 9)
    # All constant/linear features cancel; degree-two mask9 exists, but greedy returns7.
    assert len(words) % 2 == 0
    assert all(sum(x >> q & 1 for x in words) % 2 == 0 for q in range(4))
    assert _separator(words, lambda: None) == 7
    assert sum(x & 9 == 9 for x in words) % 2 == 1
