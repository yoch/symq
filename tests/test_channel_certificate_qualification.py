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
    monkeypatch.setattr(bench, "_cases", lambda: iter([
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
