from __future__ import annotations

import json

import pytest

from benchmarks import affine_phase as benchmark
from symq.labs.affine_phase import AffinePhaseResult


def test_every_small_qualification_case_matches_the_independent_reference():
    for case in benchmark.CASES:
        if case[1] <= 6:
            a, b, source, support, _ = benchmark.build_case(case)
            expected = case[3] == "equivalent" or case[0] == "nonlinear-signature"
            assert benchmark.exhaustive_fibre_reference(a, b, source, support) is expected


def test_early_failure_is_retained_after_later_success(monkeypatch):
    monkeypatch.setattr(benchmark, "CASES", (benchmark.CASES[0],))
    calls = []

    def trial(case, method, repetition):
        calls.append(repetition)
        return {"method": method, "status": "error" if len(calls) == 1 else "equivalent",
                "qualification_passed": len(calls) > 1, "repetition": repetition}

    monkeypatch.setattr(benchmark, "_trial", trial)
    document = benchmark.run_qualification(3)
    assert len(document["trials"]) == 3
    assert not document["qualification_passed"]
    assert document["trials"][0]["status"] == "error"


def test_failed_qualification_is_written_before_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "run_qualification", lambda n: {
        "qualification_passed": False, "trials": [{"status": "error"}], "counts": {"error": 1}})
    destination = tmp_path / "result.json"
    assert benchmark.main(["--output", str(destination)]) == 1
    assert json.loads(destination.read_text())["trials"][0]["status"] == "error"


def test_positive_without_receipt_cannot_qualify(monkeypatch):
    monkeypatch.setattr(benchmark, "check_affine_phase", lambda *args, **kwargs:
                        AffinePhaseResult("equivalent", "injected missing receipt"))
    trial = benchmark._trial(benchmark.CASES[0], "derivative", 0)
    assert trial["status"] == "equivalent"
    assert not trial["receipt_present"] and trial["fresh_replay"] is False
    assert not trial["qualification_passed"]
    assert "no receipt" in trial["replay_error"]


def test_replay_exception_is_preserved_in_a_failed_trial(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("injected replay failure")

    monkeypatch.setattr(benchmark, "replay_affine_phase", fail)
    trial = benchmark._trial(benchmark.CASES[0], "derivative", 0)
    assert trial["status"] == "equivalent" and trial["receipt_present"]
    assert trial["fresh_replay"] is False and not trial["qualification_passed"]
    assert trial["replay_error"] == "RuntimeError: injected replay failure"


@pytest.mark.parametrize("failure", ["missing_receipt", "replay_exception"])
def test_cli_preserves_replay_failures_and_later_trials_before_exit_one(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(benchmark, "CASES", (benchmark.CASES[0],))
    original_check = benchmark.check_affine_phase
    original_replay = benchmark.replay_affine_phase
    calls = []

    def injected_check(*args, **kwargs):
        calls.append("check")
        if len(calls) == 1:
            return AffinePhaseResult("equivalent", "injected missing receipt")
        return original_check(*args, **kwargs)

    def injected_replay(*args, **kwargs):
        calls.append("replay")
        if len(calls) == 1:
            raise RuntimeError("injected first replay failure")
        return original_replay(*args, **kwargs)

    if failure == "missing_receipt":
        monkeypatch.setattr(benchmark, "check_affine_phase", injected_check)
    else:
        monkeypatch.setattr(benchmark, "replay_affine_phase", injected_replay)
    destination = tmp_path / "actual-failed-campaign.json"
    assert benchmark.main(["--repetitions", "3", "--output", str(destination)]) == 1
    document = json.loads(destination.read_text())
    assert not document["qualification_passed"] and len(document["trials"]) == 3
    first, *later = document["trials"]
    assert first["replay_error"] and first["fresh_replay"] is False
    assert not first["qualification_passed"]
    assert all(trial["qualification_passed"] and trial["fresh_replay"] is True for trial in later)
