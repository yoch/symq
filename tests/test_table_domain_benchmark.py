"""The domain benchmark pairs its runs, measures the wide widths and keeps its failures."""
from __future__ import annotations

import json

from benchmarks import table_domain as bench


def test_a_small_isolated_run_pairs_both_constructions():
    report = bench.run(repetitions=2, paired_widths=(6,), wide_widths=(13,), seeds=(0,),
                       mutants=(None,))
    assert report["qualification_passed"] and not report["failures"]
    assert {r["execution"] for r in report["runs"]} == {"completed"}
    paired, wide = (next(c for c in report["verification"] if c["width"] == w and
                         c["backend"] == "anf") for w in (6, 13))
    assert paired["paired"] and paired["paired_ratio_minterms_over_shannon"]["n"] == 2
    assert paired["shannon"]["statuses"] == paired["minterms"]["statuses"] == ["equivalent"]
    assert not wide["paired"] and "minterms" not in wide
    assert wide["shannon"]["verify_seconds"]["n"] == 2
    # Within a pair, each member ran once and the order was drawn, not fixed.
    pairs = {}
    for r in report["runs"]:
        if r["kind"] == "verify" and r["width"] == 6:
            pairs.setdefault((r["backend"], r["repetition"]), []).append(r["method"])
    assert all(sorted(p) == sorted(bench.STYLES) for p in pairs.values())
    conversion = {c["width"]: c for c in report["conversion"]}
    assert conversion[13]["paired_ratio_per_word_over_bitsets"]["n"] == 2
    assert conversion[13]["admitted"] > 1 << 12
    json.dumps(report)


def _patched(monkeypatch, status_for_minterms):
    real = bench.verify_job

    def patched(width, seed, mutant, backend, style):
        value = real(width, seed, mutant, backend, style)
        if style == "minterms":
            value["status"] = status_for_minterms(value["expected"])
        return value

    monkeypatch.setattr(bench, "verify_job", patched)


def test_a_wrong_verdict_fails_and_is_kept(monkeypatch):
    _patched(monkeypatch, lambda expected: "not_proved" if expected == "equivalent"
             else "equivalent")
    report = bench.run(repetitions=2, paired_widths=(6,), wide_widths=(), seeds=(0,),
                       mutants=(None,), isolated=False)
    assert not report["qualification_passed"]
    cells = [f for f in report["failures"] if "cell" in f]
    assert len(cells) == 2 and all({r["method"] for r in f["runs"]} == {"minterms"}
                                   for f in cells)


def test_a_stopped_reference_is_kept_with_its_time_and_is_not_a_failure(monkeypatch):
    _patched(monkeypatch, lambda expected: "inconclusive")
    report = bench.run(repetitions=1, paired_widths=(6,), wide_widths=(), seeds=(0,),
                       mutants=(None,), isolated=False)
    assert report["qualification_passed"]
    for cell in report["verification"]:
        assert cell["minterms"]["stopped"]["n"] == 1
        assert cell["minterms"]["stopped"]["verify_seconds"]["n"] == 1
        assert cell["paired_ratio_minterms_over_shannon"] is None


def test_both_conversions_admit_the_same_words():
    for width in (6, 10):
        fast, slow = (bench.domain_job(width, 1, m) for m in ("bitsets", "per_word"))
        assert (fast["admitted"], fast["checksum"]) == (slow["admitted"], slow["checksum"])
