from __future__ import annotations

import time
from pathlib import Path
from threading import Event

import pytest

from symq.experimental import execution
from symq.experimental.execution import HardLimits, run_isolated
from symq.resources import Budget, ResourceLimitExceeded, VerificationSession


def _reconstruct(marker):
    Path(marker).write_text("untrusted reconstruction executed")
    time.sleep(3)
    return True


class _Poisoned:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return _reconstruct, (self.marker,)


def _poisoned(marker):
    return _Poisoned(marker)


def _oversized():
    return "x" * (execution.MAX_RESULT_BYTES + 1)


def _plain():
    return {"valid": True, "items": [None, -12, 2.5, "text"]}


def _slow_worker():
    time.sleep(3)
    return True


def test_returned_objects_cannot_reconstruct_in_parent(tmp_path):
    marker = tmp_path / "reconstructed"
    started = time.perf_counter()
    result = run_isolated(_poisoned, str(marker), limits=HardLimits(wall_seconds=2))
    assert result.status == "inconclusive" and result.value is None
    assert "typed IPC" in result.reason
    assert not marker.exists()
    assert time.perf_counter() - started < 2.75


def test_oversized_result_is_not_a_decision():
    result = run_isolated(_oversized, limits=HardLimits(wall_seconds=5))
    assert result.status == "inconclusive" and result.value is None
    assert "typed IPC" in result.reason


def test_parent_does_not_wait_for_slow_result_decoder(monkeypatch):
    entered = Event()
    original = execution.json.loads

    def slow_decode(value):
        entered.set()
        time.sleep(3)
        return original(value)

    monkeypatch.setattr(execution.json, "loads", slow_decode)
    started = time.perf_counter()
    result = run_isolated(_plain, limits=HardLimits(wall_seconds=1))
    assert entered.is_set(), "the result receiver must actually have started decoding"
    assert result.status == "inconclusive" and result.value is None
    assert time.perf_counter() - started < 1.75


def test_plain_result_roundtrips_without_reconstruction():
    result = run_isolated(_plain, limits=HardLimits(wall_seconds=5))
    assert result.status == "completed" and result.value == _plain()


@pytest.mark.parametrize("explicit_seconds", (None, 100))
def test_explicit_looser_session_cannot_hide_expired_active_parent(monkeypatch, explicit_seconds):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    unrelated = VerificationSession(Budget(max_seconds=explicit_seconds))

    def forbidden_spawn(*args):
        pytest.fail("an expired active parent must prevent process admission")

    monkeypatch.setattr(execution.multiprocessing, "get_context", forbidden_spawn)
    with pytest.raises(ResourceLimitExceeded, match="seconds"), \
            VerificationSession(Budget(max_seconds=10)):
        now[0] = 110.0
        result = run_isolated(_plain, session=unrelated,
                              limits=HardLimits(wall_seconds=60, memory_bytes=None))
        assert result.status == "inconclusive" and result.value is None
        assert "parent verification deadline" in result.reason


def test_explicit_unbounded_session_cannot_extend_live_active_parent():
    unrelated = VerificationSession()
    started = time.perf_counter()
    with pytest.raises(ResourceLimitExceeded, match="seconds"), \
            VerificationSession(Budget(max_seconds=0.05)):
        result = run_isolated(_slow_worker, session=unrelated,
                              limits=HardLimits(wall_seconds=5, memory_bytes=None))
        assert result.status == "inconclusive" and result.value is None
    assert time.perf_counter() - started < 0.75
