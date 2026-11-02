"""New source families and refusal paths, separate from the two-signature campaign."""
from __future__ import annotations

import random
import time
from fractions import Fraction

import pytest

from symq.errors import InternalInconsistency
from symq.labs import affine_phase, phase_discovery
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.kraus_graph import Graph
from symq.labs.phase_discovery import discover_phase_certificate
from symq.phase import PhaseProgram
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def _three_signature_source(values):
    # h=(ab,bc,cd); one of its eight signature words is unreachable.
    pairs = ((0, 1), (1, 2), (2, 3))
    d = PhaseProgram(5, 1)
    for a, b in pairs:
        d.ccx(a, b, 5).hmr(5)
    coefficients = list(values)
    for j in range(3):
        for mask in range(8):
            if mask >> j & 1:
                coefficients[mask] = (coefficients[mask] - coefficients[mask ^ (1 << j)]) % 8
    left = DyadicPhaseProgram(5, k=3)
    for mask, coefficient in enumerate(coefficients):
        if not coefficient:
            continue
        controls = sorted({q for j, pair in enumerate(pairs) if mask >> j & 1 for q in pair})
        if controls:
            left.mcx(*controls, 4).phase(4, Fraction(coefficient, 8)).mcx(*controls, 4)
        else:
            left.x(4).phase(4, Fraction(coefficient, 8)).x(4)
    support = affine_phase.AffineSupport(5, 1, (2, 1, 8, 4))
    return left, DyadicPhaseProgram(5, k=3), d, support


@pytest.mark.sat
def test_three_nonlinear_signatures_carries_offsets_and_unreachable_words():
    rng = random.Random(1633)
    for _ in range(16):
        a, b, d, support = _three_signature_source([rng.randrange(8) for _ in range(8)])
        proved = discover_phase_certificate(a, b, d, support=support, max_degree=3)
        assert proved['status'] == 'proved' and proved['fresh_verified']
        assert proved['rank'] <= 7 and proved['rounds'] <= 8
        assert same_channel(a, b, d, columns=support.columns, offset=support.offset)
        a.phase(0, Fraction(1, 8))
        negative = discover_phase_certificate(a, b, d, support=support, max_degree=3)
        assert negative['status'] == 'different' and negative['obligation'] == 'signature_collision'
        assert not same_channel(a, b, d, columns=support.columns, offset=support.offset)


def test_singleton_and_no_signature_constant_phase_without_sat():
    a = DyadicPhaseProgram(1, k=2).phase(0, Fraction(1, 4))
    b, d = DyadicPhaseProgram(1, k=2), PhaseProgram(1)
    support = affine_phase.AffineSupport(1, 1, ())
    result = discover_phase_certificate(a, b, d, support=support)
    assert result['status'] == 'proved' and result['certificate'] == [[0], []]
    assert result['signature_width'] == 0 and result['parameter_dimension'] == 0
    d.x(0)
    result = discover_phase_certificate(a, b, d, support=support)
    assert result['status'] == 'not_proved' and result['obligation'] == 'dephaser_restoration'


@pytest.mark.sat
def test_deadline_expiring_after_fresh_success_removes_decisive_result(monkeypatch):
    a, b, d, support = fixture()
    fresh = phase_discovery._fresh_check

    def expire(problem, certificate, checker, guard, max_nodes, max_clauses):
        result = fresh(problem, certificate, checker, guard, max_nodes, max_clauses)
        assert result['status'] == 'proved'
        guard._deadline = time.perf_counter() - 1
        return result

    monkeypatch.setattr(phase_discovery, '_fresh_check', expire)
    result = discover_phase_certificate(a, b, d, support=support)
    assert result['status'] == 'inconclusive' and result['certificate'] is None
    assert result['witness'] is None and result['obstruction'] is None
    assert result['fresh_verified'] is False


def test_fake_or_non_refining_counterexample_is_not_accepted(monkeypatch):
    a, b, d, support = fixture()
    monkeypatch.setattr(Graph, 'witness', lambda self, expression: 0)
    with pytest.raises(InternalInconsistency, match='does not refute'):
        discover_phase_certificate(a, b, d, support=support)
