"""Quick timings must describe the executed options and comparable, completed work."""
from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks import quick
from symq import Budget, Circuit, ResourceLimitExceeded


def test_simulation_uses_the_requested_python_backend_options(monkeypatch):
    made = []
    factory = quick.make_algebra

    def capture(*args, **kwargs):
        algebra = factory(*args, **kwargs)
        made.append(algebra)
        return algebra

    monkeypatch.setattr(quick, "make_algebra", capture)
    quick._run(Circuit(3).ccx(0, 1, 2), None, "simulate", "zdd", Budget(), {"cache_limit": 64})
    assert len(made) == 1 and made[0].cache_limit == 64


@pytest.mark.native
def test_simulation_uses_the_requested_native_backend_options(monkeypatch):
    made = []
    factory = quick.make_algebra

    def capture(*args, **kwargs):
        algebra = factory(*args, **kwargs)
        made.append(algebra)
        return algebra

    monkeypatch.setattr(quick, "make_algebra", capture)
    quick._run(Circuit(3).ccx(0, 1, 2), None, "simulate", "zdd-native", Budget(),
               {"collect_every": 200, "cache_limit": 64})
    assert len(made) == 1
    assert made[0].collect_every == 200 and made[0]._cache_limit == 64


@pytest.mark.parametrize("workload", quick.WORKLOADS)
@pytest.mark.parametrize("options,error", [
    ({"definitely_invalid_option": True}, TypeError), ({"cache_limit": 0}, ValueError),
])
def test_all_workloads_reject_invalid_backend_options(workload, options, error):
    circuit = Circuit(3).ccx(0, 1, 2)
    other, _ = quick._pair("toffoli", circuit, workload)
    with pytest.raises(error):
        quick._run(circuit, other, workload, "zdd", Budget(), options)


@pytest.fixture
def result(monkeypatch):
    monkeypatch.setattr(quick, "circuits", lambda split: [("toffoli", Circuit(3).ccx(0, 1, 2))])
    monkeypatch.setattr(quick, "WORKLOADS", ("simulate",))
    value = quick.run("dev", ["zdd"], 3, 5.0, {"cache_limit": 64})
    # These are accounting fixtures, not performance measurements.
    value["rows"][0].update(seconds=[0.1, 0.2, 0.3], median_seconds=0.2)
    return value


def test_complete_successful_cells_can_compare_different_symq_sources(result):
    baseline = deepcopy(result)
    baseline["rows"][0].update(seconds=[0.2, 0.4, 0.6], median_seconds=0.4)
    baseline["receipt"]["source_sha256"] = "different-code-under-test"
    report = quick.report(result, baseline)
    assert "3/3" in report and "ok" in report
    assert "over 1 cells: 0.500" in report


@pytest.mark.parametrize("failing", ["new", "baseline"])
def test_a_partial_resource_failure_is_visible_and_never_aggregated(result, failing):
    baseline = deepcopy(result)
    cell = (result if failing == "new" else baseline)["rows"][0]
    cell.update(status="limit:seconds", seconds=[0.1], median_seconds=0.1)
    report = quick.report(result, baseline)
    assert "limit:seconds" in report and f"{failing}: limit:seconds" in report
    assert "geometric mean" not in report
    if failing == "new":
        assert "1/3" in report


@pytest.mark.parametrize("completed", [0, 1])
def test_resource_failure_keeps_any_completed_timings_and_requested_count(result, monkeypatch,
                                                                       completed):
    calls = 0

    def succeed_then_fail(*args):
        nonlocal calls
        calls += 1
        if calls == completed + 1:
            raise ResourceLimitExceeded("seconds", 5.0, 5.1)

    monkeypatch.setattr(quick, "_run", succeed_then_fail)
    measured = quick.run("dev", ["zdd"], 3, 5.0, {})
    row = measured["rows"][0]
    assert calls == completed + 1 and row["status"] == "limit:seconds"
    assert len(row["seconds"]) == completed
    assert row["median_seconds"] == (row["seconds"][0] if completed else None)
    assert row["repetitions_requested"] == 3
    assert f"{completed}/3" in quick.report_row(row) and "limit:seconds" in quick.report_row(row)
    assert "geometric mean" not in quick.report(measured, result)


def test_slow_cell_early_stop_remains_visible_without_a_partial_ratio(result):
    baseline = deepcopy(result)
    result["rows"][0].update(seconds=[1.1], median_seconds=1.1)
    report = quick.report(result, baseline)
    assert "1/3" in report and "incomplete repetitions" in report
    assert "geometric mean" not in report


@pytest.mark.parametrize("field,value", [
    ("split", "holdout"), ("repetitions", 4), ("timeout_seconds", 7.0),
    ("slow_stop_seconds", 2.0), ("schema_version", 1), ("kind", "another_benchmark"),
])
def test_incompatible_protocols_are_not_aggregated(result, field, value):
    baseline = deepcopy(result)
    baseline[field] = value
    report = quick.report(result, baseline)
    assert "geometric mean" not in report


@pytest.mark.parametrize("field,value", [
    ("input_sha256", "different-input"), ("backend_options", {"cache_limit": 128}),
])
def test_same_name_with_different_inputs_or_options_is_not_comparable(result, field, value):
    baseline = deepcopy(result)
    baseline["rows"][0][field] = value
    report = quick.report(result, baseline)
    assert field in report and "geometric mean" not in report


def test_input_identity_includes_the_actual_generated_pair(monkeypatch):
    circuit = Circuit(3).ccx(0, 1, 2)
    monkeypatch.setattr(quick, "circuits", lambda split: [("same-name", circuit)])
    monkeypatch.setattr(quick, "WORKLOADS", ("equiv",))
    first = quick.run("dev", ["sparse"], 1, 5.0, {})
    monkeypatch.setattr(quick, "_pair", lambda *args: (circuit, True))
    second = quick.run("dev", ["sparse"], 1, 5.0, {})
    assert first["rows"][0]["input_sha256"] != second["rows"][0]["input_sha256"]
    assert "input_sha256" in quick.report(second, first)


def test_legacy_records_remain_readable_without_claiming_comparability(result):
    baseline = deepcopy(result)
    baseline["schema_version"] = 1
    del baseline["rows"][0]["input_sha256"]
    assert "incompatible record schema" in quick.report(result, baseline)
    assert "geometric mean" not in quick.report(result, baseline)
    assert "toffoli" in quick.report(baseline, None)


def test_changed_interpreter_or_cpu_class_is_not_aggregated(result):
    baseline = deepcopy(result)
    baseline["environment"]["cpu_model"] = "another CPU"
    assert "environment.cpu_model" in quick.report(result, baseline)
    assert "geometric mean" not in quick.report(result, baseline)


def test_only_successful_comparable_cells_contribute_to_the_mean(result):
    baseline = deepcopy(result)
    baseline["rows"][0].update(seconds=[0.2, 0.4, 0.6], median_seconds=0.4)
    failed = dict(result["rows"][0], circuit="failure", status="limit:seconds")
    result["rows"].append(failed)
    baseline["rows"].append(dict(failed, status="ok"))
    report = quick.report(result, baseline)
    assert "limit:seconds" in report and "over 1 cells: 0.500" in report


@pytest.mark.parametrize("median", [0, -1, float("nan"), float("inf")])
def test_nonpositive_or_nonfinite_medians_are_not_aggregated(result, median):
    baseline = deepcopy(result)
    result["rows"][0]["median_seconds"] = median
    assert "invalid median" in quick.report(result, baseline)
    assert "geometric mean" not in quick.report(result, baseline)
