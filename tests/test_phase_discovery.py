"""Source-derived discovery: rank progress, dictionary obstructions and real witnesses."""
from __future__ import annotations

import random
from fractions import Fraction
from itertools import product

import pytest

from symq.errors import InternalInconsistency, SatUnavailable
from symq.labs import kraus_graph, nonlinear_phase_bits, phase_discovery
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_discovery import _Basis, _evaluate, discover_phase_certificate
from symq.phase import PhaseProgram
from symq.resources import Budget, VerificationSession
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def test_multi_rhs_elimination_and_xor_obstructions():
    rng = random.Random(163)
    for width in range(1, 7):
        for bits in range(1, 5):
            for _ in range(30):
                basis, samples = _Basis(width, lambda: None), []
                for index in range(width + 4):
                    row, label = rng.randrange(1 << width), rng.randrange(1 << bits)
                    samples.append((row, label))
                    obstruction = basis.add(row, label, index)
                    if obstruction and obstruction[0]:
                        origin, _ = obstruction
                        row_xor = label_xor = 0
                        for j, (old_row, old_label) in enumerate(samples):
                            if origin >> j & 1:
                                row_xor ^= old_row
                                label_xor ^= old_label
                        assert row_xor == 0 and label_xor != 0
                        break
                    candidate = basis.solution()
                    assert all(_evaluate(candidate, r) == v for r, v in samples)


@pytest.mark.sat
def test_all_256_source_functions_discovered_and_freshly_checked():
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        result = discover_phase_certificate(left, right, d, support=support)
        assert result['status'] == 'proved', (values, result)
        assert result['fresh_verified'] and result['rounds'] <= 5
        assert result['rank'] <= 4
        assert same_channel(left, right, d, columns=support.columns)


@pytest.mark.sat
def test_dictionary_obstruction_is_not_inequivalence():
    left, right, d, support = fixture((0, 0, 0, 1))
    limited = discover_phase_certificate(left, right, d, support=support, max_degree=1)
    assert limited['status'] == 'dictionary_exhausted', limited
    assert limited['certificate'] is None and limited['witness'] is None
    assert same_channel(left, right, d, columns=support.columns)
    rows = limited['obstruction']['samples']
    feature_xor = label_xor = 0
    for sample in rows:
        # Independent direct feature calculation for dictionary (1,h0,h1).
        h = sample['signature']
        feature_xor ^= 1 | ((h & 1) << 1) | ((h >> 1 & 1) << 2)
        label_xor ^= sample['delta']
    assert feature_xor == 0 and label_xor != 0
    full = discover_phase_certificate(left, right, d, support=support, max_degree=2)
    assert full['status'] == 'proved' and full['fresh_verified']


@pytest.mark.sat
def test_same_signature_different_source_delta_is_a_channel_witness():
    d = PhaseProgram(3, 1).ccx(0, 1, 3)
    d.hmr(3)
    left = DyadicPhaseProgram(3, k=2).phase(0, Fraction(1, 4))
    right = DyadicPhaseProgram(3, k=2)
    result = discover_phase_certificate(left, right, d)
    assert result['status'] == 'different' and result['obligation'] == 'signature_collision'
    x, y = result['witness']['left'], result['witness']['right']
    assert x['signature'] == y['signature']
    assert x['delta'] != y['delta']
    assert not same_channel(left, right, d)


@pytest.mark.sat
def test_24_signature_bits_without_enumerating_the_input_cube():
    left = DyadicPhaseProgram(24, k=3).s(0).z(5).phase(23, Fraction(1, 8))
    right, d = DyadicPhaseProgram(24, k=3), PhaseProgram(24, 1)
    for q in range(24):
        d.cx(q, 24).hmr(24)
    result = discover_phase_certificate(left, right, d, max_degree=1)
    assert result['status'] == 'proved' and result['fresh_verified']
    assert result['feature_count'] == 25 and result['parameter_dimension'] == 24
    assert result['rounds'] <= 26 and result['sample_count'] <= 25


def test_output_mismatch_does_not_depend_on_candidate_search():
    left, right, d, support = fixture((0, 0, 0, 0))
    left.x(0)
    result = discover_phase_certificate(left, right, d, support=support)
    assert result['status'] == 'different' and result['obligation'] == 'outputs'
    assert not same_channel(left, right, d, columns=support.columns)


@pytest.mark.sat
def test_closed_options_and_resource_failures():
    a, b, d, support = fixture()
    for options in ({'dictionary': []}, {'dictionary': (True,)}, {'dictionary': (0, 0)},
                    {'dictionary': (-1,)}, {'dictionary': (4,)}, {'max_degree': True},
                    {'max_features': 0}, {'max_rounds': 4098}):
        with pytest.raises(ValueError):
            discover_phase_certificate(a, b, d, support=support, **options)
    for options in ({'max_features': 2}, {'max_rounds': 1}, {'max_graph_nodes': 1},
                    {'budget': Budget(max_seconds=1e-12)}):
        result = discover_phase_certificate(a, b, d, support=support, **options)
        assert result['status'] == 'inconclusive'
        assert not result['fresh_verified'] and result['certificate'] is None
    with VerificationSession(Budget(max_terms=1)):
        assert discover_phase_certificate(a, b, d, support=support)['status'] == 'inconclusive'
    with VerificationSession(Budget(max_bytes=1)), pytest.raises(ValueError):
        discover_phase_certificate(a, b, d, support=support)


def test_missing_solver_is_unsupported(monkeypatch):
    def missing():
        raise SatUnavailable('injected absence')

    monkeypatch.setattr(kraus_graph, '_new_solver', missing)
    a, b, d, support = fixture()
    assert discover_phase_certificate(a, b, d, support=support)['status'] == 'unsupported'


@pytest.mark.sat
def test_fresh_check_is_required_and_counts_against_original_deadline(monkeypatch):
    a, b, d, support = fixture()
    def refused(*args, **kwargs):
        return {'status': 'inconclusive', 'reason': 'injected fresh-check resource cap'}

    monkeypatch.setattr(nonlinear_phase_bits, 'check_nonlinear_phase', refused)
    result = discover_phase_certificate(a, b, d, support=support)
    assert result['status'] == 'inconclusive' and result['obligation'] == 'fresh_check'
    assert result['certificate'] is None and not result['fresh_verified']
    def forged(*args, **kwargs):
        return {'status': 'proved', 'source_sha256': '0' * 64}

    monkeypatch.setattr(nonlinear_phase_bits, 'check_nonlinear_phase', forged)
    with pytest.raises(InternalInconsistency):
        discover_phase_certificate(a, b, d, support=support)


@pytest.mark.sat
def test_original_objects_are_not_reused_after_snapshot(monkeypatch):
    a, b, d, support = fixture()
    expected = discover_phase_certificate(a, b, d, support=support)
    prepare = phase_discovery._prepare
    def mutate(*args):
        problem, metadata = prepare(*args)
        a.gates.clear()
        d.ops.clear()
        return problem, metadata

    monkeypatch.setattr(phase_discovery, '_prepare', mutate)
    result = discover_phase_certificate(a, b, d, support=support)
    assert result['status'] == 'proved' and result['fresh_verified']
    assert result['source_sha256'] == expected['source_sha256']
