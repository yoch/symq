"""Audit #166: a revoked positive must not leave any field of the positive answer behind.

The clock jumps past the deadline right after the inner fresh check (discoveries) or
right after the SAT graph is closed (checkers), i.e. after all the positive work is
done and before the final deadline check. The top-level status must be inconclusive
AND no nested diagnostic may still read as an authorization.
"""
from __future__ import annotations

import time

import pytest

from benchmarks.phase_factored import MATRICES, VALUES, small_mixed
from symq.labs import kraus_graph, phase_adaptive, phase_discovery, phase_factored
from symq.labs.nonlinear_phase_bits import check_nonlinear_phase
from tests.testkit.nonlinear_phase_cases import candidate, fixture

pytestmark = pytest.mark.sat
AUTHORITY = ('fresh_metrics', 'checked_bits')


def _expire_after(monkeypatch, owner, name):
    real = time.perf_counter
    state = {'expired': False}
    original = getattr(owner, name)

    def wrapped(*args, **kwargs):
        out = original(*args, **kwargs)
        state['expired'] = True
        return out

    monkeypatch.setattr(owner, name, wrapped)
    monkeypatch.setattr(time, 'perf_counter', lambda: real() + (1e6 if state['expired'] else 0.0))
    return state


def _assert_revoked(result, discovered=False):
    assert result['status'] == 'inconclusive' and result['obligation'] == 'resources'
    for key in AUTHORITY:
        assert key not in result, key
    if discovered:
        assert result['certificate'] is None and result['fresh_verified'] is False
        assert 'certificate_sha256' not in result and 'certificate_items' not in result


def test_factored_discovery_revoked_after_fresh_success(monkeypatch):
    left, right, d, support = small_mixed(VALUES[1], MATRICES[1], 1)
    assert phase_factored.discover_factored_phase(left, right, d, support=support)['status'] == 'proved'
    _expire_after(monkeypatch, phase_factored, '_fresh')
    _assert_revoked(phase_factored.discover_factored_phase(left, right, d, support=support), True)


@pytest.mark.parametrize('engine', ['fixed', 'adaptive'])
def test_bitplane_discoveries_revoked_after_fresh_success(monkeypatch, engine):
    left, right, d, support = fixture((0, 1, 2, 3))
    run = (phase_discovery.discover_phase_certificate if engine == 'fixed'
           else phase_adaptive.discover_adaptive_phase)
    assert run(left, right, d, support=support)['status'] == 'proved'
    _expire_after(monkeypatch, phase_discovery, '_fresh_check')
    _assert_revoked(run(left, right, d, support=support), True)


@pytest.mark.parametrize('checker', ['factored', 'bitplanes'])
def test_supplied_checkers_revoked_after_proof(monkeypatch, checker):
    if checker == 'factored':
        left, right, d, support = small_mixed(VALUES[2], MATRICES[3], 2)
        cert = phase_factored.discover_factored_phase(left, right, d, support=support)['certificate']
        run = lambda: phase_factored.check_factored_phase(left, right, d, cert, support=support)
    else:
        left, right, d, support = fixture((0, 1, 2, 3))
        run = lambda: check_nonlinear_phase(left, right, d, candidate((0, 1, 2, 3)), support=support)
    assert run()['status'] == 'proved'
    _expire_after(monkeypatch, kraus_graph.Graph, 'close')
    _assert_revoked(run())
