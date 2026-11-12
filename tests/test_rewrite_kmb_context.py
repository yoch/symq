"""The classical KMB rewrite, qualified through ``symq rewrite`` and ``symq replay``."""
from __future__ import annotations

import filecmp
import hashlib

import pytest

from benchmarks import rewrite_kmb_context as kmb
from benchmarks.rewrite_cli import INPUTS
from symq.circuit import Circuit
from symq.generators.gf2n import gf_mul
from tests.testkit.field_oracle import multiply


@pytest.mark.corpus_bilinear
def test_the_versioned_case_is_a_fresh_export_of_the_authenticated_kmb(tmp_path):
    kmb.export(tmp_path)
    for file in INPUTS:
        assert filecmp.cmp(tmp_path / kmb.CASE / file, kmb.CORPUS / kmb.CASE / file,
                           shallow=False), file
    assert filecmp.cmp(tmp_path / "MANIFEST.json", kmb.CORPUS / "MANIFEST.json", shallow=False)
    raw = kmb.source_starts()["gf16-07.kmb"]
    assert hashlib.sha256(raw).hexdigest() == kmb.KMB_SHA256


@pytest.mark.corpus_bilinear
def test_the_independent_field_oracle_agrees_with_the_library_and_catches_a_mutant():
    for n, modulus in ((4, 0x13), (6, 0x49)):
        for a in range(1 << n):
            for b in range(1 << n):
                assert multiply(n, a, b, modulus) == gf_mul(n, a, b, modulus=modulus)
    source = kmb.public_source()
    assert kmb.oracle_states(source) == 4096
    mutant = Circuit(source.width, list(source.gates)[:-1])
    with pytest.raises(AssertionError, match="differs"):
        kmb.oracle_states(mutant)


@pytest.mark.corpus_bilinear
@pytest.mark.sat
def test_the_public_kmb_rewrite_is_proved_replayed_and_checked_on_every_legal_state(tmp_path):
    result = kmb.run(tmp_path)
    case = result["case"]
    assert result["source"]["kmb_sha256"] == kmb.KMB_SHA256
    assert result["independent_oracle_states"] == 4096
    assert result["context"]["width"] == 13 and result["context"]["ancilla"] == 12
    assert (case["rewrite_exit_code"], case["replay_exit_code"]) == (0, 0)
    assert case["outcome"] == "equivalent" and case["theorem"] == "classical_contextual_full"
    assert case["obligations"] == dict.fromkeys(kmb.OBLIGATIONS, "passed")
    assert case["cost"]["weighted_delta"] < 0
    assert case["legal_states_agreeing"] == case["legal_states_checked"] == 4096
    assert case["inputs_deleted_before_replay"] and case["replay"]["reverified"]
    assert case["execution"]["status"] == "completed"
    refused = {row["case"]: row for row in result["negatives"]}
    assert refused["unprepared ancilla"]["outcome"] == "precondition_failed"
    assert refused["corrupted replacement"]["outcome"] == "not_proved"
    assert not any(row.get("candidate_exported") for row in result["negatives"])
    assert all(row["replay_exit_code"] == 3 for name, row in refused.items()
               if name.startswith("report:"))
    for kept in ("summary.json", f"{kmb.CASE}/report.json"):
        assert (tmp_path / kept).exists()
    assert not result["receipt"]["symq_location"].startswith("/")


@pytest.mark.corpus_bilinear
def test_a_changed_versioned_file_is_refused(tmp_path, monkeypatch):
    kmb.export(tmp_path)
    request = tmp_path / kmb.CASE / "request.json"
    request.write_text(request.read_text().replace('"default": 1', '"default": 2'))
    monkeypatch.setattr(kmb, "CORPUS", tmp_path)
    with pytest.raises(AssertionError, match="changed"):
        kmb.run(tmp_path / "out")


def test_an_isolated_worker_failure_is_reported_with_its_reason(tmp_path, monkeypatch):
    from benchmarks import rewrite_cli

    monkeypatch.setattr(rewrite_cli, "cli", lambda *args, **kwargs: (
        2, {"outcome": "inconclusive", "reason": "hard whole-call wall deadline exhausted"}))
    with pytest.raises(AssertionError, match="isolated execution failed.*deadline"):
        rewrite_cli.rewrite(tmp_path)
