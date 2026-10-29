from __future__ import annotations

import time

import pytest

from symq.resources import (
    Budget,
    Guard,
    ResourceLimitExceeded,
    VerificationSession,
    current_session,
    session_scoped,
)


def test_nested_guards_share_deadline_and_cannot_weaken_limits():
    with VerificationSession(Budget(max_seconds=5, max_nodes=20)) as session:
        first = Guard()
        with VerificationSession(Budget(max_seconds=10)) as nested:
            second = Budget(max_seconds=100).start()
            assert second.deadline == first.deadline == nested.deadline == session.deadline
            with pytest.raises(ResourceLimitExceeded):
                second.check_nodes(21)
    assert current_session() is None


def test_late_return_and_late_replay_are_not_decisions():
    @session_scoped
    def late(*, budget=None):
        assert Guard(budget).deadline == current_session().deadline
        time.sleep(0.01)
        return "equivalent"

    with pytest.raises(ResourceLimitExceeded):
        late(budget=Budget(max_seconds=0.001))


def test_reservations_are_simultaneous_and_work_is_cumulative():
    with VerificationSession(Budget(max_nodes=10)) as session:
        session.reserve("left", nodes=6, bytes_=100)
        with pytest.raises(ResourceLimitExceeded):
            session.reserve("right", nodes=5)
        assert session.available_nodes == 4
        session.release("left")
        session.reserve("right", nodes=5, bytes_=200)
        session.count("operations", 7)
        assert session.peaks == {"resident_nodes": 6, "retained_bytes": 200}
        assert session.counters == {"operations": 7}


@pytest.mark.parametrize("seconds", [True, float("nan"), float("inf"), -1, 0])
def test_invalid_time_budget(seconds):
    with pytest.raises(ValueError):
        Budget(max_seconds=seconds)
