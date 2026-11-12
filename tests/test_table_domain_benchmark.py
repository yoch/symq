"""The paired domain benchmark runs, records both constructions and keeps its failures."""
from __future__ import annotations

import json

from benchmarks import table_domain as bench


def test_a_small_isolated_run_records_both_constructions(tmp_path):
    report = bench.run(repetitions=1, widths=(6,), seeds=(0,), mutants=(None, "missing_phase"))
    assert report["qualification_passed"] and not report["failures"]
    assert len(report["runs"]) == 2 * 2 * 2  # cells x styles, one repetition
    assert {run["execution"] for run in report["runs"]} == {"completed"}
    for cell in report["cells"]:
        assert cell["statuses"] == {"shannon": [cell["expected"]], "minterms": [cell["expected"]]}
        for style in bench.STYLES:
            assert cell[style]["verify_seconds"]["n"] == 1
            assert cell[style]["conversion_seconds"]["median"] >= 0
    assert report["settings"]["schedule_seed"] == bench.SCHEDULE_SEED
    assert "no claim beyond" in report["scope"]
    json.dumps(report)


def test_a_wrong_verdict_fails_and_is_kept(monkeypatch):
    real = bench.job

    def wrong(width, seed, mutant, backend, style):
        value = real(width, seed, mutant, backend, style)
        if style == "minterms":
            value["status"] = "equivalent" if value["expected"] != "equivalent" else "not_proved"
        return value

    monkeypatch.setattr(bench, "job", wrong)
    report = bench.run(repetitions=2, widths=(6,), seeds=(0,), mutants=(None,), isolated=False)
    assert not report["qualification_passed"]
    assert len(report["failures"]) == 2 and all(
        {r["style"] for r in failure["runs"]} == {"minterms"} for failure in report["failures"])


def test_an_inconclusive_reference_is_not_a_failure(monkeypatch):
    real = bench.job

    def stopped(width, seed, mutant, backend, style):
        value = real(width, seed, mutant, backend, style)
        if style == "minterms":
            value["status"] = "inconclusive"
        return value

    monkeypatch.setattr(bench, "job", stopped)
    report = bench.run(repetitions=1, widths=(6,), seeds=(0,), mutants=(None,), isolated=False)
    assert report["qualification_passed"]
    assert all("minterms" not in cell for cell in report["cells"])
