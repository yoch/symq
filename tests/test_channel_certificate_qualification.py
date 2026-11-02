"""Qualification is a failing gate when a result or a public input changes."""
from __future__ import annotations

import json
import sys

import pytest

from benchmarks import channel_certificate as bench
from symq.labs.channel_certificate import CertificateResult
from symq.phase import PhaseProgram


def test_qualification_preserves_failure_evidence_and_returns_nonzero(tmp_path, monkeypatch):
    output = tmp_path / "failed.json"
    program = PhaseProgram(1)
    monkeypatch.setattr(bench, "_cases", lambda blobs: iter([
        ("injected", "test only", "equivalent", program, program),
    ]))
    monkeypatch.setattr(bench, "discover_certificate", lambda *args, **kwargs:
                        CertificateResult("inconclusive", "injected exhaustion"))
    monkeypatch.setattr(sys, "argv", ["qualification", "--repetitions", "1", "--output", str(output)])
    assert bench.main() == 1
    report = json.loads(output.read_text())
    assert report["qualification_passed"] is False
    assert report["records"][0]["trials"][0]["reason"] == "injected exhaustion"


def test_public_fixture_is_authenticated_before_any_search(tmp_path, monkeypatch):
    for relative in bench.PUBLIC_FIXTURE_BLOBS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((bench.ROOT / relative).read_bytes() + b"\n")
    monkeypatch.setattr(bench, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="pinned Git blob"):
        bench.run(repetitions=1)


def test_exceptions_in_search_or_fresh_check_are_recorded(tmp_path, monkeypatch):
    output = tmp_path / "raised.json"
    program = PhaseProgram(1)
    monkeypatch.setattr(bench, "_cases", lambda blobs: iter([
        ("raises", "test only", "equivalent", program, program),
    ]))

    def boom(*args, **kwargs):
        raise ValueError("injected refusal")

    monkeypatch.setattr(bench, "discover_certificate", boom)
    monkeypatch.setattr(sys, "argv", ["qualification", "--repetitions", "2", "--output", str(output)])
    assert bench.main() == 1
    report = json.loads(output.read_text())
    assert report["qualification_passed"] is False
    trials = report["records"][0]["trials"]
    assert len(trials) == 2
    assert all(t["outcome"] == "error" and t["error"] == {
        "stage": "discover", "type": "ValueError", "detail": "injected refusal"} for t in trials)


def test_fresh_check_exception_and_reason_are_recorded(tmp_path, monkeypatch):
    from symq.labs import channel_certificate as module

    output = tmp_path / "fresh.json"
    left = PhaseProgram(2, 1)
    left.mcx(0, 2).hmr(2)
    monkeypatch.setattr(bench, "_cases", lambda blobs: iter([
        ("fresh", "test only", "equivalent", left, left),
    ]))
    found = module.discover_certificate(left, left)
    assert found.outcome == "equivalent"
    monkeypatch.setattr(bench, "verify_certificate", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("replay crashed")))
    monkeypatch.setattr(sys, "argv", ["qualification", "--repetitions", "1", "--output", str(output)])
    assert bench.main() == 1
    trial = json.loads(output.read_text())["records"][0]["trials"][0]
    assert trial["outcome"] == "equivalent"
    assert trial["error"]["stage"] == "fresh_check" and trial["error"]["type"] == "RuntimeError"
    monkeypatch.setattr(bench, "verify_certificate", module.verify_certificate)
    assert bench.main() == 0
    trial = json.loads(output.read_text())["records"][0]["trials"][0]
    assert trial["fresh_check_outcome"] == "equivalent" and trial["fresh_check_reason"]


def test_setup_failure_still_writes_json(tmp_path, monkeypatch):
    for relative in bench.PUBLIC_FIXTURE_BLOBS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"tampered")
    monkeypatch.setattr(bench, "ROOT", tmp_path)
    output = tmp_path / "setup.json"
    monkeypatch.setattr(sys, "argv", ["qualification", "--repetitions", "1", "--output", str(output)])
    assert bench.main() == 1
    report = json.loads(output.read_text())
    assert report["qualification_passed"] is False
    assert "pinned Git blob" in report["error"]["detail"]


def test_cases_are_parsed_from_the_authenticated_bytes(tmp_path, monkeypatch):
    for relative in bench.PUBLIC_FIXTURE_BLOBS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((bench.ROOT / relative).read_bytes())
    monkeypatch.setattr(bench, "ROOT", tmp_path)
    _hashes, blobs = bench._authenticate_fixtures()
    for relative in bench.PUBLIC_FIXTURE_BLOBS:  # swap every file after authentication
        (tmp_path / relative).write_bytes(b"swapped after authentication")
    names = [case[0] for case in bench._cases(blobs)]
    assert {"inc8", "qualtran_m1", "qualtran_m2"} <= set(names)
