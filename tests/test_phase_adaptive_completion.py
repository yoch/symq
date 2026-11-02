"""Independent completion regressions: column growth can leave another obstruction."""
from __future__ import annotations

import random
from fractions import Fraction
from types import SimpleNamespace

import pytest

from symq.labs import nonlinear_phase_bits, phase_adaptive, phase_discovery
from symq.labs.affine_phase import AffineSupport
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def test_column_growth_may_consume_an_earlier_dependency_not_the_failing_row(monkeypatch):
    # This pure interpolation regression failed at first adaptive checkpoint 22516fb.
    # New mask5 increases rank4->5 at row4, yet row5 still contradicts another relation.
    words = (0, 4, 5, 3, 6, 1, 7)
    labels = (137, 119, 149, 233, 245, 150, 254)
    samples = [{'parameter': i, 'input': i, 'signature': h, 'delta': value}
               for i, (h, value) in enumerate(zip(words, labels))]
    monkeypatch.setattr(phase_discovery, '_sample', lambda p, z, _c, _g: p[z])
    symbolic = SimpleNamespace(_bool=lambda masks, _h, _g: masks[0])
    masks, features = [0, 1, 2, 4], [0, 1, 2, 4]
    result = {'basis_rebuilds': 0, 'growth': []}
    basis = phase_adaptive._complete(samples, masks, features, None, samples, None,
                                     symbolic, None, Guard(Budget(max_seconds=5)), 8, result)
    coefficients = basis.solution()
    for sample in samples:
        row = phase_discovery._features(sample['signature'], masks)
        assert phase_discovery._evaluate(coefficients, row) == sample['delta']
    assert result['growth'][0]['added_mask'] == 5
    assert result['growth'][0]['rank_before'] == 4 and result['growth'][0]['rank_after'] == 5
    assert len(result['growth']) <= len(samples)
    assert all(e['rank_after'] > e['rank_before'] for e in result['growth'])


def test_random_multilabel_completion_uses_only_rank_raising_columns(monkeypatch):
    # Pure kernel test only: literal phase samples are tested separately below.
    monkeypatch.setattr(phase_discovery, '_sample', lambda p, z, _c, _g: p[z])
    symbolic = SimpleNamespace(_bool=lambda masks, _h, _g: masks[0])
    rng = random.Random(167)
    for width in range(1, 9):
        for _ in range(30):
            words = rng.sample(range(1 << width), rng.randint(1, min(64, 1 << width)))
            samples = [{'parameter': j, 'input': j, 'signature': h, 'delta': rng.randrange(256)}
                       for j, h in enumerate(words)]
            masks = [0] + [1 << j for j in range(width)]
            features = list(masks)
            result = {'basis_rebuilds': 0, 'growth': []}
            basis = phase_adaptive._complete(samples, masks, features, None, samples, None,
                                             symbolic, None, Guard(Budget(max_seconds=5)), 512, result)
            coefficients = basis.solution()
            assert len(result['growth']) <= len(samples)
            for sample in samples:
                row = sum(int(sample['signature'] & m == m) << j for j, m in enumerate(masks))
                value = 0
                for j, coefficient in enumerate(coefficients):
                    if row >> j & 1:
                        value ^= coefficient
                assert value == sample['delta']
            assert all(e['rank_after'] > e['rank_before'] for e in result['growth'])


@pytest.mark.sat
def test_incremental_reuse_and_full_refit_agree_exactly():
    rng = random.Random(168)
    fields = ('status', 'certificate', 'dictionary', 'samples', 'growth', 'rank',
              'graph_nodes', 'cnf_clauses', 'sat_calls', 'rounds', 'source_sha256')
    for _ in range(30):
        left, right, d, support = fixture(tuple(rng.randrange(4) for _ in range(4)))
        reuse = discover_adaptive_phase(left, right, d, support=support)
        refit = discover_adaptive_phase(left, right, d, support=support, reuse_basis=False)
        assert reuse['status'] == refit['status'] == 'proved'
        assert {k: reuse[k] for k in fields} == {k: refit[k] for k in fields}
        assert reuse['basis_rebuilds'] <= refit['basis_rebuilds']
        if not reuse['growth']:
            assert reuse['basis_rebuilds'] == 0
    with pytest.raises(ValueError):
        discover_adaptive_phase(left, right, d, support=support, reuse_basis=1)


@pytest.mark.sat
def test_irregular_mod256_source_not_only_two_signature_truth_tables():
    # Exact handoff from independently specified 3-input phase table to a real source.
    table = (137, 150, 80, 233, 119, 149, 245, 254)
    left, right = DyadicPhaseProgram(4, k=8), DyadicPhaseProgram(4, k=8)
    d = PhaseProgram(4, 1)
    for wire in range(3):
        d.cx(wire, 4).hmr(4)
    for word, exponent in enumerate(table):
        zeros = [q for q in range(3) if not word >> q & 1]
        for q in zeros:
            left.x(q)
        left.mcx(0, 1, 2, 3).phase(3, Fraction(exponent, 256)).mcx(0, 1, 2, 3)
        for q in reversed(zeros):
            left.x(q)
    support = AffineSupport(4, 0, (1, 2, 4))
    result = discover_adaptive_phase(left, right, d, support=support, max_features=8)
    assert result['status'] == 'proved' and result['fresh_verified']
    assert result['feature_count'] <= 8 and result['added_features'] <= result['sample_count']
    assert same_channel(left, right, d, columns=support.columns)
    for x in range(8):
        assert left.run(x) == (x, table[x])
    cert = tuple(tuple(p) for p in result['certificate'])
    assert nonlinear_phase_bits.check_nonlinear_phase(left, right, d, cert, support=support)['status'] == 'proved'
