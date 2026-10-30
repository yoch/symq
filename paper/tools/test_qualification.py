"""Evidence-accounting regressions; synthetic fixtures here are never measured data."""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import math
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("paper_qualification", Path(__file__).with_name("make_qualification.py"))
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
summarise = _MODULE.summarise


def test_compressed_artifact_preserves_raw_bytes_and_both_hashes(tmp_path):
    raw = b'{"rows": []}\n'
    encoded = gzip.compress(raw, mtime=0)
    path = tmp_path / "results.json.gz"
    path.write_bytes(encoded)
    decoded, artifact_hash = _MODULE.read_artifact(path)
    assert decoded == raw
    assert artifact_hash == hashlib.sha256(encoded).hexdigest()
    plain = tmp_path / "results.json"
    plain.write_bytes(raw)
    assert _MODULE.read_artifact(plain) == (raw, hashlib.sha256(raw).hexdigest())


def row(case, family, backend, seconds, *, status="ok", repetition=0, task="equivalence"):
    return {"case_id": case, "family": family, "backend": backend,
            "boundary": "public_api_end_to_end", "repetition": repetition,
            "task": task, "status": status, "service_seconds": seconds,
            "source_hash_checked": True, "exported": task == "anf_export",
            "witness_checked": task == "counterexample", "oracle_checked": True,
            "split": "new_holdout"}


def adjudicated_fixture():
    rows = [row("fresh", "stochastic", "zdd-native-fused", 1),
            row("fresh", "stochastic", "zdd", 4),
            row("known", "deterministic", "zdd-native-fused", 4),
            row("known", "deterministic", "zdd", 1)]
    data = {"rows": rows, "source": {"commit": "a" * 40}, "manifest_sha256": "b" * 64,
            "cases": [{"id": name, "split": "new_holdout"} for name in ("fresh", "known")]}
    classification = {"schema": "symq/case-classification/v1", "measured_source_commit": "a" * 40,
                      "raw_manifest_sha256": "b" * 64,
                      "classification": {name: {"classification": case_class,
                                                "raw_split": "new_holdout", "reason": "fixture"}
                                         for name, case_class in (("fresh", "fresh_stochastic_holdout"),
                                                                  ("known", "development_calibration"))}}
    return data, classification


def test_adjudication_preserves_raw_labels_and_primary_mixed_study():
    data, classification = adjudicated_fixture()
    original = copy.deepcopy(data)
    primary = summarise(data)
    sensitivity = _MODULE.holdout_sensitivity(data, classification)
    assert data == original
    assert primary["case_count"] == 2
    assert primary["effects"][0]["family_balanced_ratio"] == 1
    assert sensitivity["case_count"] == 1
    assert sensitivity["effects"][0]["family_balanced_ratio"] == 4
    assert sensitivity["effects"][0]["descriptive_family_resampling"] is None


@pytest.mark.parametrize("defect", ("source", "manifest", "missing", "extra", "raw_split", "unknown_class"))
def test_adjudication_must_match_measured_source_manifest_and_all_cases(defect):
    data, classification = adjudicated_fixture()
    if defect == "source":
        classification["measured_source_commit"] = "c" * 40
    elif defect == "manifest":
        classification["raw_manifest_sha256"] = "c" * 64
    elif defect == "missing":
        del classification["classification"]["known"]
    elif defect == "extra":
        classification["classification"]["absent"] = classification["classification"]["known"]
    elif defect == "raw_split":
        classification["classification"]["known"]["raw_split"] = "corrected_in_place"
    else:
        classification["classification"]["known"]["classification"] = "unverified_new_label"
    with pytest.raises(ValueError):
        _MODULE.validate_classification(data, classification)


def test_equal_family_weight_is_not_equal_circuit_weight():
    rows = []
    for case in range(8):
        rows += [row(f"a{case}", "large_family", "zdd-native", 1),
                 row(f"a{case}", "large_family", "zdd", 4)]
    rows += [row("b", "small_family", "zdd-native", 4), row("b", "small_family", "zdd", 1)]
    effect = summarise({"rows": rows})["effects"][0]
    assert effect["common_cases"] == 9 and effect["paired_successes"] == 9
    assert math.isclose(effect["family_balanced_ratio"], 1)
    assert effect["leave_one_family_out"] == [0.25, 4]


def test_not_run_and_unsupported_stay_in_denominator_without_ratios():
    rows = [row("a", "f", "zdd-native", 1), row("a", "f", "sat", 1, status="unsupported"),
            row("b", "f", "zdd-native", None, status="not_run"),
            row("b", "f", "sat", None, status="not_run")]
    derived = summarise({"rows": rows})
    assert derived["statuses"] == {"ok": 1, "unsupported": 1, "not_run": 2}
    assert derived["effects"][0]["common_cases"] == 0
    assert derived["effects"][0]["family_balanced_ratio"] is None
    assert sum(x["trials"] for x in derived["coverage"]) == 4


def test_repeats_do_not_increase_case_or_family_count():
    rows = [row("a", "f", backend, seconds, repetition=i)
            for i in range(15) for backend, seconds in (("zdd-native", 1), ("zdd", 2))]
    derived = summarise({"rows": rows})
    assert derived["case_count"] == derived["family_count"] == 1
    assert derived["effects"][0]["paired_successes"] == 15
    assert derived["effects"][0]["common_cases"] == 1
    assert derived["effects"][0]["descriptive_family_resampling"] is None


def test_unequal_successful_repeat_counts_do_not_reweight_cases():
    # Both cases belong to one family. Fifteen successful repeats on the first
    # case must not outweigh the single successful repeat on the second case.
    rows = [row("many", "f", backend, seconds, repetition=i)
            for i in range(15) for backend, seconds in (("zdd-native-fused", 1), ("zdd", 4))]
    rows += [row("one", "f", "zdd-native-fused", 4), row("one", "f", "zdd", 1)]
    effect = next(e for e in summarise({"rows": rows})["effects"]
                  if e["candidate"] == "zdd-native-fused" and e["baseline"] == "zdd")
    assert effect["paired_successes"] == 16 and effect["common_cases"] == 2
    assert math.isclose(effect["family_effects"]["f"], 1)
    assert math.isclose(effect["family_balanced_ratio"], 1)


def test_duplicate_trial_is_rejected():
    value = row("a", "f", "zdd", 1)
    with pytest.raises(ValueError, match="duplicate"):
        summarise({"rows": [value, copy.deepcopy(value)]})


@pytest.mark.parametrize("task,flag", (("equivalence", "source_hash_checked"),
                                      ("anf_export", "exported"),
                                      ("counterexample", "witness_checked")))
def test_unestablished_evidence_cannot_be_an_ordinary_success(task, flag):
    value = row("a", "f", "zdd", 1, task=task)
    value[flag] = False
    with pytest.raises(ValueError):
        summarise({"rows": [value]})


def test_cross_algorithm_agreement_is_not_exhaustive_oracle_timing_evidence():
    rows = [row("large", "f", "zdd-native", 1), row("large", "f", "sat", 2)]
    for value in rows:
        value["oracle_checked"] = False
        value["cross_algorithm_checked"] = True
    result = summarise({"rows": rows})
    assert result["effects"][0]["common_cases"] == 0
    assert result["effects"][0]["family_balanced_ratio"] is None
    assert result["statuses"] == {"ok": 2}


def test_validation_failure_preserves_service_checkpoint_without_success_ratio():
    value = row("a", "f", "zdd-native", 0.1, status="inconclusive")
    value.update(service_completed=True, validation_status="timeout", oracle_checked=False)
    result = summarise({"rows": [value]})
    assert result["coverage"][0]["service_completed"] == 1
    assert result["coverage"][0]["validation_outcomes"] == {"timeout": 1}
    assert result["statuses"] == {"inconclusive": 1}


def test_shipped_and_matched_native_configurations_are_never_pooled():
    rows = [row("a", "f", "zdd-native-fused", 10),
            row("a", "f", "zdd-native", 1), row("a", "f", "zdd", 2)]
    effects = summarise({"rows": rows})["effects"]
    fused = next(e for e in effects if e["candidate"] == "zdd-native-fused" and e["baseline"] == "zdd")
    matched = next(e for e in effects if e["candidate"] == "zdd-native" and e["baseline"] == "zdd")
    assert math.isclose(fused["family_balanced_ratio"], 0.2)
    assert math.isclose(matched["family_balanced_ratio"], 2)
