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
    # Randomized families use independent development seeds. Increment ignores
    # its seed and is explicitly development calibration, never a fresh holdout.
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


def test_unequal_completed_repetitions_do_not_reweight_cases():
    rows = []
    # Three common completions for one case, one for another in the same
    # family. The case medians are 2 and 8, so their equal-case mean is 4.
    for case, repetitions, ratios in [("a-1", 3, [1.0, 2.0, 3.0]), ("a-2", 1, [8.0])]:
        for repetition, ratio in zip(range(repetitions), ratios):
            rows.extend([_row("zdd-native-fused", case_id=case, repetition=repetition),
                         _row("sparse", case_id=case, repetition=repetition, service_seconds=ratio)])
    # An unmatched timeout remains in coverage and supplies no ratio.
    rows.extend([_row("zdd-native-fused", case_id="a-2", repetition=1),
                 _row("sparse", "timeout", case_id="a-2", repetition=1)])
    report = summarise({"rows": rows})
    comparison, = report["conditional_comparisons"]
    assert comparison["denominator_backend"] == "zdd-native-fused"
    assert comparison["common_verified_pairs"] == 4
    assert comparison["common_verified_cases"] == 2
    assert comparison["family_ratios"] == {"a": pytest.approx(4.0)}
    assert comparison["family_balanced_ratio"] == pytest.approx(4.0)
    assert [(c["case_id"], c["common_verified_pairs"], c["median_paired_ratio"])
            for c in comparison["case_summaries"]] == [("a-1", 3, 2.0), ("a-2", 1, 8.0)]
    assert report["status_counts"]["timeout"] == 1


def test_manifest_separates_stochastic_holdout_from_calibration():
    assert MANIFEST_DATA["selection_frozen_before_measurement"]
    assert all(c["split"] == ("development_calibration" if c["family"] == "increment" else "new_holdout")
               for c in MANIFEST_DATA["cases"])
    assert len({c["seed"] for c in MANIFEST_DATA["cases"]}) == len(MANIFEST_DATA["cases"])
    assert all(not c["qualification"] for c in MANIFEST_DATA["cases"] if c["family"] == "mixed_nonlinear")
    assert len(digest(MANIFEST_DATA)) == 64
    assert MANIFEST_DATA["analysis_plan"]["primary_native_denominator"] == "zdd-native-fused"
    assert MANIFEST_DATA["analysis_plan"]["secondary_native_configuration"] == "zdd-native"
    assert "not the shipped default" in MANIFEST_DATA["backend_configurations"]["zdd-native"]
    assert "predeclared mixed-study aggregate" in MANIFEST_DATA["analysis_plan"]["calibration_disclosure"]


@pytest.mark.parametrize("case", [c for c in MANIFEST_DATA["cases"] if c["family"] == "increment"],
                         ids=lambda c: c["id"])
def test_seed_independent_increment_streams_require_calibration_label(case):
    first = build_case({**case, "seed": 1})
    second = build_case({**case, "seed": 2})
    assert all(left.width == right.width and left.gates == right.gates
               for left, right in zip(first, second))
    assert case["split"] == "development_calibration"


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


def _budget_clock(monkeypatch, *, service_seconds, validation_seconds, service_cpu=0.5, validation_cpu=0.25):
    import time

    import benchmarks.qualification_protocol as protocol
    from symq.resources import current_session

    now, cpu, deadlines = [100.0], [0.0], []
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    monkeypatch.setattr(protocol, "_cpu_seconds", lambda: cpu[0])

    def public(*args):
        deadlines.append(("service", current_session().deadline))
        now[0] += service_seconds
        cpu[0] += service_cpu
        return {"computed": True, "equivalent": True}, None, None, None

    def oracle(*args):
        deadlines.append(("validation", current_session().deadline))
        now[0] += validation_seconds
        cpu[0] += validation_cpu
        return True, None

    monkeypatch.setattr(protocol, "_public_service", public)
    monkeypatch.setattr(protocol, "exhaustive_pair", oracle)
    case = {"id": "separate-clock-development", "family": "affine", "width": 3, "depth": 2, "seed": 791}
    checkpoints = []
    row = execute_trial(case, "equivalence", "sparse", "public_api_end_to_end",
                        MANIFEST_DATA["limits"], checkpoint=checkpoints.append)
    return row, checkpoints, deadlines


def test_optional_validation_gets_fresh_budget_after_service_completes(monkeypatch):
    row, checkpoints, deadlines = _budget_clock(monkeypatch, service_seconds=2.9, validation_seconds=1.8)
    assert row["status"] == "ok" and row["oracle_checked"]
    assert row["trial_wall_seconds"] == pytest.approx(4.7)
    assert row["service_wall_seconds"] == row["service_seconds"] == pytest.approx(2.9)
    assert row["validation_wall_seconds"] == pytest.approx(1.8)
    assert row["service_cpu_seconds"] == 0.5 and row["validation_cpu_seconds"] == 0.25
    assert deadlines == [("service", 103.0), ("validation", 104.9)]
    assert checkpoints[0]["computed"] and checkpoints[0]["service_completed"]
    assert not checkpoints[0]["oracle_checked"]


def test_late_service_never_gets_an_independent_validation_extension(monkeypatch):
    row, checkpoints, deadlines = _budget_clock(monkeypatch, service_seconds=3.01, validation_seconds=0.1)
    assert row["status"] == "timeout" and row["failure_stage"] == "service"
    assert not checkpoints and deadlines == [("service", 103.0)]
    assert not row["service_completed"] and row["equivalent"] is None


@pytest.mark.parametrize("resource_name", ["wall", "cpu"])
def test_validation_timeout_retains_service_checkpoint_without_verified_verdict(monkeypatch, resource_name):
    row, checkpoints, deadlines = _budget_clock(
        monkeypatch, service_seconds=2.9, validation_seconds=2.01 if resource_name == "wall" else 0.1,
        validation_cpu=2.01 if resource_name == "cpu" else 0.25)
    assert row["status"] == "inconclusive" and row["failure_stage"] == "validation"
    assert row["validation_status"] == "timeout"
    assert row["service_completed"] and row["service_status"] == "ok"
    assert row["computed"] and not row["oracle_checked"] and row["equivalent"] is None
    assert len(checkpoints) == 1 and len(deadlines) == 2
    assert row["service_checkpoint"]["service_seconds"] == pytest.approx(2.9)


def test_simulation_validation_rebinds_its_retained_manager_guard(monkeypatch):
    import time

    import benchmarks.qualification_protocol as protocol

    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    real = protocol._simulate
    guards = []

    def simulate(*args, **kwargs):
        algebra = args[1]
        result = real(*args, **kwargs)
        now[0] = 102.9
        original = algebra.to_anf

        def export(value):
            guards.append(algebra.guard.deadline)
            now[0] = 103.5
            return original(value)

        algebra.to_anf = export
        return result

    monkeypatch.setattr(protocol, "_simulate", simulate)
    case = {"id": "rebind-development", "family": "affine", "width": 3, "depth": 2, "seed": 411}
    row = execute_trial(case, "simulate", "zdd", "task_service_end_to_end", MANIFEST_DATA["limits"])
    assert row["status"] == "ok" and row["oracle_checked"]
    assert guards and all(deadline == pytest.approx(104.9) for deadline in guards)


def test_parent_validation_kill_preserves_only_nondecisive_service_evidence():
    from benchmarks.qualification_protocol import _parent_failure

    saved = {"computed": True, "service_completed": True, "service_status": "ok",
             "service_cpu_seconds": 0.5, "equivalent": True, "oracle_checked": False}
    row = _parent_failure("timeout", "validation wall limit", "wall", "validation", saved)
    assert row["status"] == "inconclusive" and row["failure_stage"] == "validation"
    assert row["computed"] and row["service_completed"] and row["service_status"] == "ok"
    assert row["equivalent"] is None and not row["oracle_checked"]
    assert row["service_checkpoint"] == saved
