from __future__ import annotations

import json
import subprocess
import sys

import pytest

from benchmarks import affine_basis as campaign


@pytest.mark.checkout
def test_provenance_refuses_unavailable_pinned_ancestry(monkeypatch):
    monkeypatch.setattr(campaign, "PINNED_HEAD", "0" * 40)
    with pytest.raises(ValueError, match="ancestry unavailable; use a full Git checkout"):
        campaign.provenance()


def test_setup_refusal_is_written_before_exit_one(monkeypatch, tmp_path):
    def unavailable():
        raise ValueError("published baseline ancestry unavailable")

    monkeypatch.setattr(campaign, "provenance", unavailable)
    target = tmp_path / "setup-failure.json"
    assert campaign.main(["--cases", "tiny_reference", "--methods", "canonical_cache",
                          "--repetitions", "1", "--output", str(target)]) == 1
    document = json.loads(target.read_text())
    assert not document["qualified"] and document["trials"] == []
    assert document["setup_error"] == "ValueError: published baseline ancestry unavailable"


def test_positive_requires_receipt_and_fresh_replay(monkeypatch):
    monkeypatch.setattr(campaign.prototype, "run", lambda *args, **kwargs: {
        "status": "equivalent", "receipt": None, "witness": None, "metrics": {}})
    result = campaign.trial(campaign.cases()[0], "canonical_cache")
    assert not result["qualified"] and not result["source_binding_valid"]


def test_replay_exception_is_preserved(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("injected replay failure")

    monkeypatch.setattr(campaign.core, "replay_affine_phase", broken)
    result = campaign.trial(campaign.cases()[0], "canonical_cache")
    assert not result["qualified"]
    assert result["replay_error"] == "RuntimeError: injected replay failure"
    assert result["result"]["status"] == "equivalent"
    assert result["proof_and_replay_seconds"] >= result["proof_outer_seconds"]


@pytest.mark.checkout
def test_main_continues_and_writes_failed_trials_before_return_one(monkeypatch, tmp_path):
    calls = []

    def failed(case, method):
        calls.append((case["id"], method))
        return {"case_id": case["id"], "method": method, "qualified": len(calls) > 1,
                "worker_source_hashes": campaign.source_hashes(),
                "result": {"status": "error" if len(calls) == 1 else "equivalent"}}

    monkeypatch.setattr(campaign, "isolated_trial", failed)
    target = tmp_path / "failure.json"
    result = campaign.main(["--cases", "tiny_reference", "--methods", "canonical_cache", "published",
                            "--repetitions", "2", "--output", str(target)])
    document = json.loads(target.read_text())
    assert result == 1 and not document["qualified"] and len(document["trials"]) == 4
    assert [row["qualified"] for row in document["trials"]] == [False, True, True, True]
    assert {row["repetition"] for row in document["trials"]} == {0, 1}


@pytest.mark.checkout
def test_summary_cli_accepts_a_single_selected_method(tmp_path):
    target, summary = tmp_path / "single-method.json", tmp_path / "summary.json"
    assert campaign.main(["--cases", "tiny_reference", "--methods", "canonical_cache",
                          "--repetitions", "1", "--output", str(target)]) == 0
    result = subprocess.run([sys.executable, "-m", "benchmarks.affine_basis_summary", str(target),
                             "--output", str(summary)], cwd=campaign.ROOT, text=True,
                            capture_output=True, check=False, timeout=20)
    assert result.returncode == 0, result.stderr
    document = json.loads(summary.read_text())
    assert document["qualified"] and document["trials"] == 1
    assert document["paired_ratios"] == {}
    assert list(document["cases"][0]["methods"]) == ["canonical_cache"]
    assert "| Case | Cache | Status |" in result.stdout


@pytest.mark.checkout
def test_real_cli_writes_json_before_exit_one_on_cap(tmp_path):
    target = tmp_path / "term-cap.json"
    result = subprocess.run([sys.executable, "-m", "benchmarks.affine_basis",
                             "--cases", "dense_expansion_term_cap", "--methods", "canonical_cache",
                             "--repetitions", "1", "--require-decision", "--output", str(target)],
                            cwd=campaign.ROOT, text=True, capture_output=True, check=False, timeout=20)
    document = json.loads(target.read_text())
    assert result.returncode == 1 and not document["qualified"]
    assert len(document["trials"]) == 1
    assert document["trials"][0]["result"]["status"] == "inconclusive"
