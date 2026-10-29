from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from symq.experimental import execution
from symq.experimental.execution import HardLimits, run_isolated


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
