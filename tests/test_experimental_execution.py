from __future__ import annotations

import sys
import time

from symq.experimental.execution import HardLimits, run_isolated


def _success():
    return {"outcome": "equivalent"}


def _late():
    time.sleep(2)
    return "equivalent"


def _fail():
    raise ValueError("invalid worker input")


def test_spawn_returns_metrics_and_value():
    result = run_isolated(_success, limits=HardLimits(wall_seconds=5))
    assert result.status == "completed"
    assert result.value == {"outcome": "equivalent"}
    assert result.peak_rss_bytes > 0 and result.cpu_seconds >= 0


def test_hard_timeout_never_returns_late_verdict():
    result = run_isolated(_late, limits=HardLimits(wall_seconds=0.1))
    assert result.status == "inconclusive" and result.value is None


def test_worker_exception_is_not_a_counterexample():
    result = run_isolated(_fail, limits=HardLimits(wall_seconds=5))
    assert result.status == "error" and result.value is None


def test_spawn_uses_the_same_package_when_an_old_checkout_precedes_it(tmp_path, monkeypatch):
    old = tmp_path / "symq"
    old.mkdir()
    (old / "__init__.py").write_text("# historical checkout without experimental APIs\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    before = list(sys.path)
    result = run_isolated(_success, limits=HardLimits(wall_seconds=5))
    assert result.status == "completed" and result.value["outcome"] == "equivalent"
    assert sys.path == before
