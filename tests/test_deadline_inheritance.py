from __future__ import annotations

import time

import pytest

from symq import Budget, Circuit
from symq.equivalence import check_equivalence, check_equivalence_by_blocks
from symq.resources import Guard, ResourceLimitExceeded, VerificationSession


@pytest.mark.parametrize("elapsed", [0, 6, 9.999])
def test_inherited_deadline_survives_multiple_blocks(monkeypatch, elapsed):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    program = Circuit(3).x(0).x(1).x(2)
    with VerificationSession(Budget(max_seconds=10, max_nodes=20, max_terms=8)) as parent:
        now[0] += elapsed
        view = parent.remaining_budget()
        assert view.absolute_deadline == 110
        assert view.max_seconds is None
        with VerificationSession(view) as child:
            assert child.deadline == 110
            assert Guard(view).deadline == 110
            assert check_equivalence_by_blocks(program, program, backend="sparse", budget=view).equivalent


def test_nested_relative_limits_intersect_without_reanchoring_parent(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    with VerificationSession(Budget(max_seconds=10, max_nodes=20, max_terms=8)) as parent:
        now[0] = 106
        with VerificationSession(Budget(max_seconds=2, max_nodes=12, max_terms=10)) as child:
            assert child.deadline == 108
            assert child.budget.max_nodes == 12
            assert child.budget.max_terms == 8
            assert Guard(Budget(max_seconds=100)).deadline == 108
        assert parent.deadline == 110
        detached = parent.subprocess_budget()
        assert detached.max_seconds == 4
        assert detached.absolute_deadline is None


def test_exact_deadline_expires_and_cannot_be_extended(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    with pytest.raises(ResourceLimitExceeded), VerificationSession(Budget(max_seconds=10)) as parent:
        now[0] = 110
        Guard(Budget(max_seconds=100)).check_time()
    with pytest.raises(ResourceLimitExceeded):
        Guard(parent.inherited_budget()).check_time()


def test_concrete_witness_replay_cannot_return_late_difference(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    original = Circuit.run

    def late_run(self, value):
        result = original(self, value)
        now[0] = 110
        return result

    monkeypatch.setattr(Circuit, "run", late_run)
    with pytest.raises(ResourceLimitExceeded):
        check_equivalence(Circuit(1), Circuit(1).x(0), budget=Budget(max_seconds=10))
