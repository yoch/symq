"""Protocol correctness, task semantics, accounting and clustered uncertainty."""
from __future__ import annotations

import json

import pytest

from benchmarks.qualification_protocol import (
    MANIFEST,
    build_case,
    check_worker_diagnostics,
    digest,
    execute_trial,
    exhaustive_pair,
    scalar_run,
    verify_snapshot,
)
from benchmarks.qualification_report import cross_algorithm_groups, family_summary, summarise

MANIFEST_DATA = json.loads(MANIFEST.read_text())


@pytest.mark.parametrize("case", [c for c in MANIFEST_DATA["cases"] if c["width"] <= 10], ids=lambda c: c["id"])
def test_independent_constructions_and_rare_mutants(case):
    # Unit-test generator correctness on independent development seeds, without
    # inspecting the frozen holdout's concrete circuits before measurement.
    case = {**case, "seed": 1000 + case["width"] + len(case["family"])}
    left, right, mutant = build_case(case)
    assert exhaustive_pair(left, right)[0]
    same, witness = exhaustive_pair(left, mutant)
    assert not same and witness is not None
    assert scalar_run(left, witness) != scalar_run(mutant, witness)
    for value in range(1 << left.width):
        assert scalar_run(left, value) == left.run(value)
    if case["family"] == "increment":
        assert all(scalar_run(left, value) == (value + 1) % (1 << left.width)
                   for value in range(1 << left.width))


@pytest.mark.parametrize("backend", ["sparse", "zdd"])
@pytest.mark.parametrize("task", MANIFEST_DATA["tasks"])
@pytest.mark.parametrize("boundary", MANIFEST_DATA["boundaries"])
def test_task_services_are_correct_and_exclusive(backend, task, boundary):
    case = {**MANIFEST_DATA["cases"][1], "seed": 19871}
    row = execute_trial(case, task, backend, boundary, MANIFEST_DATA["limits"])
    assert row["status"] == "ok", row
    assert row["computed"] and row["oracle_checked"]
    assert sum(value or 0.0 for value in row["phases"].values()) == pytest.approx(row["trial_wall_seconds"])
    if task == "counterexample":
        assert row["equivalent"] is False and row["witness_checked"]
    if task == "anf_export":
        assert row["exported"] and row["export_sha256"]


@pytest.mark.parametrize("backend", ["sat", "qcec"])
@pytest.mark.parametrize("task", ["simulate", "anf_export"])
def test_decision_tools_never_claim_symbolic_exports(backend, task):
    row = execute_trial({**MANIFEST_DATA["cases"][0], "seed": 27191}, task, backend,
                        "public_api_end_to_end", MANIFEST_DATA["limits"])
    assert row["status"] == "unsupported" and not row["exported"]


@pytest.mark.parametrize("backend", MANIFEST_DATA["backends"])
@pytest.mark.parametrize("task", ["equivalence", "counterexample", "anf_export"])
def test_available_tool_adapters_have_the_same_full_input_contract(backend, task):
    # Development inputs only; native/foreign availability stays explicit.
    case = {"id": "adapter-development", "family": "triangular_shear", "width": 4,
            "depth": 12, "seed": 811771}
    row = execute_trial(case, task, backend, "public_api_end_to_end", MANIFEST_DATA["limits"])
    if row["status"] == "unsupported":
        assert row["reason"]
        return
    assert row["status"] == "ok", row
    assert row["oracle_checked"]
    if task == "counterexample":
        assert row["witness_checked"] and row["equivalent"] is False
    if task == "equivalence":
        assert row["equivalent"] is True


def test_frozen_source_changes_are_detected_before_execution(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("original")
    from benchmarks.qualification_protocol import file_hash
    (tmp_path / "FREEZE.json").write_text(json.dumps({
        "source": {"files": {"source.py": file_hash(source)}}}))
    verify_snapshot(tmp_path)
    source.write_text("changed")
    with pytest.raises(RuntimeError, match="frozen source changed"):
        verify_snapshot(tmp_path)


def _row(backend, status="ok", **extra):
    return {"family": "a", "task": "equivalence", "boundary": "public_api_end_to_end",
            "case_id": "a-1", "repetition": 0, "backend": backend, "status": status,
            "service_seconds": 1.0, "oracle_checked": True, **extra}


def test_coverage_counts_missing_failures_and_requires_two_verified_implementations():
    rows = [_row("zdd-native-fused"), _row("sat", "not_run"),
            _row("cudd-bdd", "timeout"), _row("polybori", oracle_checked=False)]
    report = summarise({"rows": rows})
    assert report["status_counts"] == {"ok": 2, "not_run": 1, "timeout": 1}
    assert report["conditional_comparisons"] == []
    rows.append(_row("sparse", service_seconds=2.0))
    report = summarise({"rows": rows})
    comparison = report["conditional_comparisons"][0]
    assert comparison["common_verified_pairs"] == 1
    assert comparison["family_balanced_ratio"] == 2.0


def test_family_statistics_do_not_turn_size_variants_into_independent_families():
    report = family_summary({"a": [2.0] * 30, "b": [0.5]})
    assert report["families"] == 2
    assert report["family_balanced_ratio"] == 1.0
    assert report["leave_one_family_out"] == {"a": 0.5, "b": 2.0}


def test_manifest_is_new_and_selection_is_canonically_identifiable():
    assert MANIFEST_DATA["selection_frozen_before_measurement"]
    assert all(c["split"] == "new_holdout" for c in MANIFEST_DATA["cases"])
    assert len({c["seed"] for c in MANIFEST_DATA["cases"]}) == len(MANIFEST_DATA["cases"])
    assert all(not c["qualification"] for c in MANIFEST_DATA["cases"] if c["family"] == "mixed_nonlinear")
    assert len(digest(MANIFEST_DATA)) == 64


def test_public_boundary_invokes_installed_public_api_with_unknown_inner_costs(monkeypatch):
    import symq

    original = symq.check_equivalence
    calls = []

    def public(*args, **kwargs):
        calls.append(kwargs["backend"])
        return original(*args, **kwargs)

    monkeypatch.setattr(symq, "check_equivalence", public)
    case = {"id": "public-development", "family": "affine", "width": 3, "depth": 5, "seed": 31}
    row = execute_trial(case, "equivalence", "sparse", "public_api_end_to_end", MANIFEST_DATA["limits"])
    assert calls == ["sparse"] and row["status"] == "ok"
    assert row["phases"]["compute"] is None and row["phases"]["conversion"] is None
    assert row["service_seconds"] == row["phases"]["public_api"] > 0


def test_missing_optional_native_is_an_admission_refusal(monkeypatch):
    from symq.backends import BACKENDS

    monkeypatch.delitem(BACKENDS, "zdd-native", raising=False)
    case = {"id": "missing-development", "family": "affine", "width": 3, "depth": 4, "seed": 73}
    for boundary in MANIFEST_DATA["boundaries"]:
        row = execute_trial(case, "equivalence", "zdd-native-fused", boundary, MANIFEST_DATA["limits"])
        assert row["status"] == "unsupported" and row["equivalent"] is None


def test_native_shutdown_diagnostics_never_count_as_success():
    record = {"status": "ok", "equivalent": True, "witness": 3, "witness_checked": True}
    failure = "Exception ignored in: 'dd.cudd_zdd.ZDD.__dealloc__'\nAssertionError: Still 3 nodes referenced"
    result = check_worker_diagnostics(record, failure)
    assert result["status"] == "error" and result["equivalent"] is None
    assert result["witness"] is None and not result["witness_checked"]
    assert result["stderr"] == failure
    benign = check_worker_diagnostics({"status": "ok"}, "UserWarning: optional version message")
    assert benign["status"] == "ok" and benign["stderr"]


@pytest.mark.parametrize("task,wrong", [("equivalence", False), ("counterexample", True)])
def test_large_cases_cannot_accept_a_wrong_expected_verdict(monkeypatch, task, wrong):
    from types import SimpleNamespace

    import symq

    # No final holdout seed or costly symbolic calculation is executed.
    case = {"id": "large-label-development", "family": "affine", "width": 14, "depth": 5, "seed": 81191}
    monkeypatch.setattr(symq, "check_equivalence", lambda *args, **kwargs: SimpleNamespace(
        equivalent=wrong, witness=None, stats=SimpleNamespace()))
    row = execute_trial(case, task, "sparse", "public_api_end_to_end", MANIFEST_DATA["limits"])
    assert row["status"] == "error" and "expected label" in row["reason"]
    assert row["equivalent"] is None and not row["oracle_checked"]


def test_cross_algorithm_agreement_never_masquerades_as_exhaustive_oracle():
    rows = [_row("zdd-native-fused", equivalent=True, oracle_checked=False),
            _row("zdd", equivalent=True, oracle_checked=False)]
    groups, checked = cross_algorithm_groups(rows)
    assert groups[0]["status"] == "insufficient_diversity" and not checked
    rows.append(_row("sat", equivalent=True, oracle_checked=False))
    groups, checked = cross_algorithm_groups(rows)
    assert groups[0]["status"] == "agreement" and len(checked) == 3
    assert groups[0]["exhaustive_oracle_backends"] == []
    report = summarise({"rows": rows})
    assert sum(g["cross_algorithm_checked"] for g in report["coverage"]) == 3
    assert not any(r["oracle_checked"] for r in rows)
    assert report["conditional_comparisons"] == []
    rows[-1]["equivalent"] = False
    groups, checked = cross_algorithm_groups(rows)
    assert groups[0]["status"] == "disagreement" and not checked


def test_counterexample_service_requires_a_returned_and_replayed_witness(monkeypatch):
    from types import SimpleNamespace

    import symq

    case = {"id": "witness-development", "family": "affine", "width": 3, "depth": 5, "seed": 17}
    monkeypatch.setattr(symq, "check_equivalence", lambda *args, **kwargs: SimpleNamespace(
        equivalent=False, witness=None, stats=SimpleNamespace()))
    row = execute_trial(case, "counterexample", "sparse", "public_api_end_to_end", MANIFEST_DATA["limits"])
    assert row["status"] == "error" and "no replayed witness" in row["reason"]
    assert row["equivalent"] is None and not row["witness_checked"]
