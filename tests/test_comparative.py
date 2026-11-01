"""comparative comparative-campaign protocol, source, oracle and failure-accounting tests.

No timing threshold or speedup assertion is allowed. The holdout remains
reserved and no unsupported semantics is silently converted to classical.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.comparative import (
    MANIFEST,
    _blob_sha1,
    _qualification,
    distribution,
    load_manifest,
    preflight,
    run_campaign,
    sha256,
    summarize,
)
from benchmarks.comparative_worker import _program_digest, build_case
from symq.corpus import load_corpus


def test_manifest_pins_all_development_sources_and_theorem_eligibility():
    manifest = load_manifest()
    assert len(manifest["cases"]) == 13
    assert manifest["schedule"]["default_repetitions"] == 15
    assert _blob_sha1(MANIFEST.read_bytes()) == "81fc4d7c5cf256ad98db614f5057273a108fc9a1"
    assert len(sha256(MANIFEST.read_bytes())) == 64
    cases = manifest["cases"]
    assert all(c["partition"] == "development" for c in cases)
    assert not any(c["fixture"].startswith("holdout") for c in cases)
    corpus = load_corpus(Path(__file__).parents[1] /
                         "benchmarks/corpus/qcec/MANIFEST.json")
    for c in cases:
        if c["family"] == "qcec":
            hit = next(e for e in corpus.entries if e.name == c["fixture"])
            assert hit.split == "dev" and hit.supported
    assert manifest["theorems"]["classical"]["backends"] == ["sat", "zdd", "qcec"]
    assert manifest["theorems"]["hmr"]["backends"] == ["zdd", "hybrid-exact"]
    assert "qcec_unitary_adapter_not_applicable" in (
        manifest["theorems"]["hmr"]["outside_scope"]
    )


def test_manifest_mutations_fail_closed(tmp_path):
    data = json.loads(MANIFEST.read_text())
    data["cases"][0]["expected"] = "different"
    path = tmp_path / "modified.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="pinned Git blob"):
        load_manifest(path)


def test_independent_oracles_qualify_all_13_reference_pairs():
    manifest = load_manifest()
    identities = preflight(manifest)
    assert len(identities) == 13
    for case in manifest["cases"]:
        row = identities[case["id"]]
        assert row["oracle"]["label_validated"]
        assert len(row["reference_sha256"]) == len(row["candidate_sha256"]) == 64
        assert row["theorem"] == manifest["theorems"][case["theorem"]]["name"]
        if case["expected"] == "different":
            assert row["oracle"]["witness"] is not None
    # A missing measurement correction can preserve classical diagonals
    # while changing off-diagonal coherences: never use a basis-only oracle.
    missing = identities["qualtran-m1-hmr-missing-correction"]["oracle"]
    assert missing["tested_input_coherences"] == 16
    assert missing["diagonals_equal"]
    assert not missing["exhaustive"] is False


def test_distinct_true_source_and_altered_kmb_candidate():
    cases = {c["id"]: c for c in load_manifest()["cases"]}
    good = cases["kmb-gf16-original-vs-tower"]
    bad = cases["kmb-gf16-target-flip-mutant"]
    left, right, info = build_case(good)
    altered, mutant, info2 = build_case(bad)
    assert _program_digest(left, "classical") == _program_digest(altered, "classical")
    assert _program_digest(right, "classical") != _program_digest(mutant, "classical")
    assert info["source_sha256"] == info2["source_sha256"]
    assert left.run(0) == right.run(0)
    assert left.run(0) != mutant.run(0)


@pytest.mark.parametrize(
    "execution_status,actual,expected,engine,witness,reason,category",
    [
        ("completed", "equivalent", "equivalent", "sat", False, "", "matched"),
        ("completed", "different", "different", "sat", True, "", "matched"),
        ("completed", "different", "different", "zdd", False, "", "invalid_witness"),
        ("completed", "different", "different", "qcec", False, "", "matched"),
        ("completed", "equivalent", "different", "sat", False, "", "incorrect_decision"),
        ("completed", "unsupported", "equivalent", "qcec", False, "", "unsupported"),
        ("completed", "inconclusive", "equivalent", "sat", False, "", "inconclusive"),
        ("inconclusive", "inconclusive", "different", "sat", False, "hard wall deadline", "timeout"),
        ("inconclusive", "inconclusive", "different", "sat", False, "memory limit", "inconclusive"),
        ("error", "error", "equivalent", "zdd", False, "unexpected exception", "error"),
    ],
)
def test_censored_categories_are_never_mistaken_for_disagreement(
    execution_status, actual, expected, engine, witness, reason, category
):
    row = {
        "execution_status": execution_status,
        "execution_reason": reason,
        "actual": actual, "engine": engine,
        "value": {"detail": {"witness_replayed": witness}},
    }
    assert _qualification(row, expected) == category


def test_ineligible_comparators_and_paired_summary():
    cases = [
        {"id": "s", "expected": "different", "theorem": "classical"},
        {"id": "q", "expected": "equivalent", "theorem": "hmr"},
    ]

    def row(case_id, engine, seconds):
        return {"case_id": case_id, "engine": engine, "repetition": 0,
                "qualification": "matched", "worker_wall_seconds": seconds + 0.4,
                "worker_cpu_seconds": seconds / 2, "worker_peak_rss_bytes": 123456,
                "value": {"decision_wall_seconds": seconds,
                          "engine_import_wall_seconds": 0.1}}

    summaries = summarize([
        row("s", "sat", 2.0), row("s", "qcec", 4.0),
        row("q", "zdd", 6.0), row("q", "hybrid-exact", 3.0),
    ], cases)
    assert summaries[0]["paired_ratio_only_matched"]["median"] == 0.5
    assert summaries[1]["paired_ratio_only_matched"]["median"] == 2.0
    assert summaries[1]["excluded_comparators"]["qcec"].startswith("not_applicable")
    assert summaries[0]["excluded_comparators"]["pyzx"].startswith("not_run")
    assert distribution([]) == {"n": 0, "median": None, "p10": None, "p90": None}


def test_small_isolated_smoke_includes_time_cpu_rss_and_source_pins():
    report = run_campaign(
        cases=["borrowed-dirty-roundtrip", "borrowed-dirty-missing-uncompute"],
        repetitions=1, wall_seconds=10.0,
    )
    assert report["source_unchanged"]
    assert report["eligible_trials"] == 6
    assert report["campaign_type"] == "single-repetition-smoke"
    assert sum(report["qualification_counts"].values()) == 6
    assert not any(r["qualification"] in ("incorrect_decision", "invalid_witness", "error")
                   for r in report["rows"]), report["rows"]
    for r in report["rows"]:
        assert r["execution_reason"]
        assert r["worker_wall_seconds"] >= 0
        assert r["worker_exitcode"] is None or type(r["worker_exitcode"]) is int
        if r["value"] is not None:
            measured = r["value"]
            assert measured["engine_import_wall_seconds"] >= 0
            assert measured["decision_wall_seconds"] >= 0
            assert measured["worker_inside_wall_seconds"] >= (
                measured["materialization_wall_seconds"]
                + measured["engine_import_wall_seconds"]
                + measured["decision_wall_seconds"] - 0.000001
            )
            exact = report["fixtures"][r["case_id"]]
            assert r["value"]["reference_sha256"] == exact["reference_sha256"]
            assert r["value"]["candidate_sha256"] == exact["candidate_sha256"]
