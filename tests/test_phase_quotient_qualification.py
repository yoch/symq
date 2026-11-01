"""An early failed trial cannot be hidden by a later successful repetition."""
from __future__ import annotations

import json
from dataclasses import replace

from benchmarks import phase_quotient
from symq.errors import ResourceLimitExceeded


def test_first_wrong_verdict_then_correct_still_fails_and_writes_json(tmp_path, monkeypatch):
    actual = phase_quotient.check_prefix_phase
    calls = 0

    def first_wrong(*args, **kwargs):
        nonlocal calls
        calls += 1
        proof = actual(*args, **kwargs)
        if calls == 1:
            return replace(proof, outcome="not_proved", constant=None,
                           reason="injected early incorrect verdict")
        return proof

    monkeypatch.setattr(phase_quotient, "check_prefix_phase", first_wrong)
    output = tmp_path / "failed-qualification.json"
    assert phase_quotient.main(["--repetitions", "2", "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert report["passed"] is False and report["failed_trials"] == 1
    public = report["cases"][0]
    assert public["passed"] is False and public["outcome"] == "mixed"
    assert public["receipt"] is None  # No last-successful receipt replaces conflicting trials.
    first, second = public["trials"]
    assert first["outcome"] == "not_proved" and first["passed"] is False
    assert first["receipt"]["reason"] == "injected early incorrect verdict"
    assert {failure["stage"] for failure in first["failures"]} >= {
        "expected_outcome", "scalar_oracle", "replay",
    }
    assert first["replay"]["status"] == "error"
    assert second["outcome"] == "proved" and second["passed"] is True
    assert second["replay"]["status"] == "matched"
    assert public["failures"] and all(failure["repetition"] == 1 for failure in public["failures"])
    assert all(row["passed"] for row in report["cases"][1:])


def test_early_resource_failure_is_preserved_after_later_success(tmp_path, monkeypatch):
    actual = phase_quotient.check_prefix_phase
    calls = 0

    def first_exhausted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ResourceLimitExceeded("terms", 100, 101)
        return actual(*args, **kwargs)

    monkeypatch.setattr(phase_quotient, "check_prefix_phase", first_exhausted)
    output = tmp_path / "resource-failure.json"
    assert phase_quotient.main(["--repetitions", "2", "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert report["passed"] is False and report["failed_trials"] == 1
    first, second = report["cases"][0]["trials"]
    assert first["outcome"] == "inconclusive" and first["receipt"] is None
    assert first["replay"]["status"] == "not_run"
    assert first["failures"][0] == {
        "stage": "verification", "type": "ResourceLimitExceeded",
        "detail": "terms limit exceeded: observed 101, limit 100",
    }
    assert second["passed"] is True and second["replay"]["status"] == "matched"
