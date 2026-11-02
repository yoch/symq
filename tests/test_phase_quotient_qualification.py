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
    stages = {failure["stage"] for failure in first["failures"]}
    assert stages >= {"expected_outcome", "replay"}
    assert "scalar_oracle" not in stages  # not_proved is sound; only expectations catch it
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


def test_wrong_proved_constant_fails_the_scalar_oracle(tmp_path, monkeypatch):
    import symq.labs.phase_quotient as module

    actual = module.check_prefix_phase

    def shifted(*args, **kwargs):
        proof = actual(*args, **kwargs)
        if proof.outcome == "proved":
            return replace(proof, constant=(proof.constant + 3) % (1 << proof.k))
        return proof

    monkeypatch.setattr(module, "check_prefix_phase", shifted)  # replay uses it too
    monkeypatch.setattr(phase_quotient, "check_prefix_phase", shifted)
    output = tmp_path / "wrong-constant.json"
    assert phase_quotient.main(["--repetitions", "1", "--output", str(output)]) == 1
    public = json.loads(output.read_text())["cases"][0]
    assert public["outcome"] == "proved" and public["passed"] is False
    assert [f["stage"] for f in public["failures"]] == ["scalar_oracle"]


def test_sound_refusal_of_a_true_claim_is_not_an_oracle_failure(tmp_path, monkeypatch):
    actual = phase_quotient.check_prefix_phase

    def refuse(*args, **kwargs):
        proof = actual(*args, **kwargs)
        return replace(proof, outcome="not_proved", constant=None, reason="incomplete")

    monkeypatch.setattr(phase_quotient, "check_prefix_phase", refuse)
    output = tmp_path / "refusal.json"
    assert phase_quotient.main(["--repetitions", "1", "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    public = report["cases"][0]
    assert "scalar_oracle" not in {f["stage"] for f in public["failures"]}
    assert "expected_outcome" in {f["stage"] for f in public["failures"]}


def test_adverse_case_that_is_actually_true_is_flagged(monkeypatch):
    oracle = {"inputs": 1, "invariant_violations": 0, "phase_differences": 0, "phases": [0]}
    prefix, certificate, constants, _ = phase_quotient.public_case()
    trial = phase_quotient._trial(prefix, certificate, constants, "not_proved", oracle, 1)
    assert "adverse_fixture" in {f["stage"] for f in trial["failures"]}
