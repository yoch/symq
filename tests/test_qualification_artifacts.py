"""Integrity and evidence accounting of the completed, immutable classical archive.

These tests replay no benchmark and import no optional solver. Receipts and
hashes establish artifact identity, not independently checked certificates.
"""
from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.qualification_report import STATUSES, summarise

ARTIFACTS = Path(__file__).resolve().parents[1] / "benchmarks/qualification/classical-20261030"
SOURCE = "49f5c438fe8916d2d2abf0a1dd137c33fd752184"
TREE = "18e930ff435de1591b144f34e69dbf408a6351d5"
MANIFEST_SHA256 = "5753129962a3dd6e6b77ffd5c9272391e51ee4f8b73e731e721fef42809d8b37"
BINARY_SHA256 = "2a14a3eac241d2e4de22ebda12880505f8bf0b63b4d07f6a9c9460269b4a8bc4"
CLASSIFICATION_SHA256 = "2604175d57a3100d420cce3826a6ffdaa850ffa1593d017db27c37a8d9e2b242"
SELECTED = {"fresh-affine-4", "fresh-shear-5", "fresh-increment-5",
            "adverse-nonlinear-14", "adverse-nonlinear-18"}
QCEC_CONFIGURATION = {"run_alternating_checker": True, "run_simulation_checker": False,
                      "run_zx_checker": False, "run_construction_checker": False,
                      "parallel": False}
QCEC_CONCLUSIVE = {"equivalent": True, "equivalent_up_to_global_phase": True,
                   "not_equivalent": False}


def sha256(content):
    return hashlib.sha256(content).hexdigest()


@pytest.fixture(scope="module")
def archive():
    receipt = json.loads((ARTIFACTS / "receipt.json").read_text())
    compressed = (ARTIFACTS / "results.json.gz").read_bytes()
    raw = gzip.decompress(compressed)
    return {"receipt": receipt, "compressed": compressed, "raw": raw,
            "data": json.loads(raw),
            "freeze": json.loads((ARTIFACTS / "freeze.json").read_text()),
            "manifest": json.loads((ARTIFACTS / "frozen-manifest.json").read_text()),
            "classification": json.loads((ARTIFACTS / "case-classification.json").read_text())}


def test_checksums_cover_every_archived_file_exactly_once():
    checksums = {}
    for line in (ARTIFACTS / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
        assert name == Path(name).name and name not in checksums and name != "SHA256SUMS"
        checksums[name] = digest
    expected = {p.name for p in ARTIFACTS.iterdir() if p.is_file() and p.name != "SHA256SUMS"}
    assert set(checksums) == expected
    for name, expected_hash in checksums.items():
        assert sha256((ARTIFACTS / name).read_bytes()) == expected_hash, name


def test_result_gzip_is_bound_to_the_original_raw_bytes(archive):
    receipt, compressed, raw = (archive[k] for k in ("receipt", "compressed", "raw"))
    assert receipt["schema"] == "symq/classical-qualification-receipt/v1"
    result = receipt["results"]
    assert result["file"] == "results.json.gz"
    assert result["sha256"] == sha256(compressed)
    assert result["raw_sha256"] == sha256(raw)
    assert result["gzip_bytes"] == len(compressed) and result["raw_bytes"] == len(raw)
    assert json.loads(raw) == archive["data"]


def test_source_manifest_and_native_identity_are_the_measured_ones(archive):
    data, freeze, receipt = (archive[k] for k in ("data", "freeze", "receipt"))
    assert data["schema"] == freeze["schema"] == "symq/qualification/v1"
    assert data["source"] == freeze["source"]
    assert data["source"]["commit"] == receipt["source_commit"] == SOURCE
    assert data["source"]["tree"] == receipt["source_tree"] == TREE
    assert data["manifest_sha256"] == freeze["manifest_sha256"] == MANIFEST_SHA256
    assert receipt["manifest_sha256"] == MANIFEST_SHA256
    assert sha256((ARTIFACTS / "frozen-manifest.json").read_bytes()) == MANIFEST_SHA256
    assert data["cases"] == archive["manifest"]["cases"]
    native = data["source"]["native"]
    assert native["abi"] == receipt["native_abi"] == 5
    assert native["binary_sha256"] == receipt["native_binary_sha256"] == BINARY_SHA256
    build_bytes = (ARTIFACTS / "build.json").read_bytes()
    assert sha256(build_bytes) == native["receipt_sha256"]
    build = json.loads(build_bytes)
    assert build["binary_sha256"] == BINARY_SHA256
    assert build["source_sha256"] == native["source_sha256"]


def test_complete_trial_grid_has_no_duplicates_missing_cells_or_hidden_skips(archive):
    data, manifest, grid = (archive["data"], archive["manifest"], archive["receipt"]["grid"])
    assert data["complete"] is True and not data.get("aborted")
    assert data["qualification_only"] is False and data["repetitions"] == 15
    selection = data["selection"]
    assert set(selection["cases"]) == SELECTED
    assert set(selection["backends"]) == set(manifest["backends"])
    assert set(selection["tasks"]) == set(manifest["tasks"])
    assert selection["boundaries"] == ["public_api_end_to_end"]
    expected = set(itertools.product(
        (c["id"] for c in manifest["cases"]), selection["tasks"],
        selection["backends"], selection["boundaries"], range(15)))
    actual = [(r["case_id"], r["task"], r["backend"], r["boundary"], r["repetition"])
              for r in data["rows"]]
    assert len(actual) == len(set(actual)) == len(expected) == 4320
    assert set(actual) == expected
    assert all(r["status"] in STATUSES for r in data["rows"])
    assert all((r["status"] != "not_run") == (r["case_id"] in SELECTED)
               for r in data["rows"])
    counts = Counter(r["status"] for r in data["rows"])
    assert counts["not_run"] == grid["not_run"] == 1620
    assert sum(v for k, v in counts.items() if k != "not_run") == grid["attempted"] == 2700
    assert grid["planned"] == 4320 and grid["repetitions"] == 15
    assert grid["status_counts"] == dict(counts)


def test_raw_case_labels_survive_the_explicit_classification_erratum(archive):
    data, classification, receipt = (archive[k] for k in ("data", "classification", "receipt"))
    assert classification["schema"] == "symq/case-classification/v1"
    assert classification["measured_source_commit"] == SOURCE
    assert classification["raw_manifest_sha256"] == MANIFEST_SHA256
    assert receipt["classification"]["file"] == "case-classification.json"
    assert receipt["classification"]["sha256"] == CLASSIFICATION_SHA256
    assert sha256((ARTIFACTS / "case-classification.json").read_bytes()) == CLASSIFICATION_SHA256
    cases = {c["id"]: c for c in archive["manifest"]["cases"]}
    classes = classification["classification"]
    assert set(classes) == set(cases)
    for case_id, case in cases.items():
        entry = classes[case_id]
        assert entry["raw_split"] == case["split"] == "new_holdout"
        expected = ("development_calibration" if case["family"] == "increment" else
                    "fresh_adverse_holdout" if case["family"] == "mixed_nonlinear" else
                    "fresh_stochastic_holdout")
        assert entry["classification"] == expected and entry["reason"]
    for row in data["rows"]:
        assert row["family"] == cases[row["case_id"]]["family"]
        assert row["split"] == cases[row["case_id"]]["split"]


def test_success_flags_require_the_requested_service_and_checked_provenance(archive):
    data = archive["data"]
    cases = {c["id"]: c for c in archive["manifest"]["cases"]}
    for row in data["rows"]:
        if row["status"] == "not_run":
            continue
        if row["status"] in {"timeout", "oom", "inconclusive", "killed", "error"}:
            assert row.get("equivalent") is None and row.get("witness") is None
            assert not row.get("oracle_checked") and not row.get("witness_checked")
        if row["backend"] in {"sat", "qcec"} and row["task"] in {"simulate", "anf_export"}:
            assert row["status"] == "unsupported" and not row.get("exported")
        if row["status"] != "ok":
            continue
        assert row["computed"] is True and row["service_completed"] is True
        assert row["source_hash_checked"] is True and row["source_commit"] == SOURCE
        assert row["native_sha256"] == BINARY_SHA256 and row["native_abi"] == 5
        assert row["worker_exitcode"] == 0
        assert math.isfinite(row["service_seconds"]) and row["service_seconds"] >= 0
        assert row["service_wall_seconds"] < data["limits"]["verification_wall_seconds"]
        assert row["service_cpu_seconds"] < data["limits"]["verification_cpu_seconds"]
        if row["task"] == "anf_export":
            assert row["exported"] is True and len(row["export_sha256"]) == 64
        if row["task"] == "counterexample":
            assert row["backend"] != "qcec" and row["equivalent"] is False
            assert row["witness_checked"] is True and type(row["witness"]) is int
            assert 0 <= row["witness"] < 1 << cases[row["case_id"]]["width"]
        if row["task"] == "equivalence":
            assert row["equivalent"] is True
        assert row["oracle_checked"] is (cases[row["case_id"]]["width"] <= 10)
        if row["oracle_checked"]:
            assert row["validation_status"] == "passed"


def test_development_qa_remains_separate_complete_and_independently_checked(archive):
    receipt = archive["receipt"]["development_qa"]
    assert receipt["file"] == "development-qa.json.gz"
    compressed = (ARTIFACTS / receipt["file"]).read_bytes()
    raw = gzip.decompress(compressed)
    assert sha256(compressed) == receipt["sha256"] and sha256(raw) == receipt["raw_sha256"]
    qa = json.loads(raw)
    assert qa["complete"] is True and qa["source"] == archive["freeze"]["source"]
    assert qa["manifest_sha256"] == MANIFEST_SHA256
    assert qa["case"]["split"] == "development_protocol_qa"
    assert qa["case"]["seed"] == 811771 and qa["case"]["width"] == 4
    assert len(qa["rows"]) == 108
    keys = [(r["backend"], r["task"], r["boundary"]) for r in qa["rows"]]
    assert len(set(keys)) == 108
    assert set(keys) == set(itertools.product(archive["manifest"]["backends"],
                                             archive["manifest"]["tasks"],
                                             archive["manifest"]["boundaries"]))
    assert Counter(r["status"] for r in qa["rows"]) == {"ok": 93, "unsupported": 15}
    for row in qa["rows"]:
        if row["status"] == "ok":
            assert row["oracle_checked"] is True and row["source_hash_checked"] is True
            assert row["source_commit"] == SOURCE and row["native_sha256"] == BINARY_SHA256
            if row["task"] == "counterexample":
                assert row["witness_checked"] is True


def _assert_same_report(actual, expected):
    if type(expected) is float:
        assert type(actual) in {int, float} and math.isfinite(actual)
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
    elif isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys()
        for key in expected:
            _assert_same_report(actual[key], expected[key])
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected)
        for left, right in zip(actual, expected):
            _assert_same_report(left, right)
    else:
        assert type(actual) is type(expected) and actual == expected


def test_report_counts_evidence_and_family_statistics_recompute_from_all_rows(archive):
    independent = summarise(archive["data"])
    _assert_same_report(archive["data"]["report"], independent)
    _assert_same_report(json.loads((ARTIFACTS / "report.json").read_text()), independent)


def test_qcec_raw_labels_are_not_promoted_from_probabilistic_or_unknown_verdicts(archive):
    qcec = archive["receipt"]["qcec"]
    assert qcec["configuration"] == QCEC_CONFIGURATION
    assert qcec["source_sha256"] == archive["freeze"]["source"]["files"][
        "src/symq/external/qcec.py"]
    assert qcec["evidence_level"] == "external_engine_verdict_not_independently_checked_certificate"
    counts = {}
    for task in ("equivalence", "counterexample"):
        rows = [r for r in archive["data"]["rows"] if r["backend"] == "qcec"
                and r["task"] == task and r["status"] != "not_run"]
        counts[task] = dict(Counter(r.get("statistics", {}).get("verdict", "<no returned verdict>")
                                    for r in rows))
        for row in rows:
            verdict = row.get("statistics", {}).get("verdict")
            if row["status"] == "ok":
                assert verdict in QCEC_CONCLUSIVE
                assert row["equivalent"] is QCEC_CONCLUSIVE[verdict]
            if verdict is not None and verdict not in QCEC_CONCLUSIVE:
                assert row.get("equivalent") is None and row["status"] != "ok"
    assert qcec["verdict_counts_by_task"] == counts


def test_receipt_does_not_retroactively_supply_complete_cpu_or_cleanup_metrics(archive):
    limitations = archive["receipt"]["measurement_limitations"]
    assert limitations["full_reaped_worker_cpu_available"] is False
    assert limitations["cpu_seconds"] == "pre_result_sample_excludes_json_and_teardown"
    assert limitations["cleanup_phase"] == "zero_placeholder_uninstrumented"
    assert limitations["public_api_from"] == "frozen_source_snapshot"
    assert all("worker_cpu_seconds_reaped" not in r for r in archive["data"]["rows"])
