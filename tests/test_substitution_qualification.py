"""Semantic and provenance tests for the substitution qualification corpus."""
import json

import pytest

from benchmarks.substitution_qualification import (
    _execute,
    _qcec,
    load_manifest,
)

pytestmark = pytest.mark.sat


def test_manifest_is_closed_and_public_sources_are_disclosed():
    manifest = load_manifest()
    cases = manifest["cases"]
    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    assert all("holdout" not in case["provenance"] for case in cases)
    assert any(case["family"] == "qualtran" for case in cases)
    assert any(case["family"] == "classical" for case in cases)
    assert any(case["family"] == "qcec" for case in cases)


@pytest.mark.parametrize("case", load_manifest()["cases"], ids=lambda c: c["id"])
def test_expected_semantic_status_and_witness_boundary(case):
    result = _execute(case)
    assert result["outcome"] == case["expected"]
    if case["family"] == "classical" and result["outcome"] == "proved":
        assert result["global_exhaustive_oracle"] is not False
    if case["scenario"] == "dirty_not_restored":
        assert result["facts"]["unproved_slot"] == 0


def test_pinned_qcec_blob_checksum_is_checked(monkeypatch, tmp_path):
    from benchmarks import substitution_qualification as module

    source_path = module.ROOT / "benchmarks/corpus/qcec"
    copy = tmp_path / "benchmarks/corpus/qcec"
    copy.mkdir(parents=True)
    (copy / "alu1_198.qasm").write_text("OPENQASM 2.0; qreg q[2];", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "QCEC_MANIFEST",
                        source_path / "MANIFEST.json")
    with pytest.raises(ValueError, match="checksum"):
        _qcec("alu1_198")


def test_manifest_refuses_mutated_expected_labels(tmp_path):
    manifest = load_manifest()
    document = dict(manifest)
    document["cases"] = list(manifest["cases"])
    document["cases"][0] = dict(manifest["cases"][0], expected="magic")
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="expected"):
        load_manifest(path)
