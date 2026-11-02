"""Qualification retains every repetition, adverse result and missing oracle receipt."""
import json

from benchmarks import shift_diagonal_ancilla as bench
from symq.experimental.hybrid import HybridProgram


def test_all_families_public_provenance_and_adverse_costs_are_retained():
    report = bench.run(repetitions=1)
    assert report["qualification_passed"]
    assert len(report["trials"]) == 39
    assert len({t["family"] for t in report["trials"]}) == 7
    assert len(report["public_sources"]) == 2
    assert all(s["upstream"]["license"] == "Apache-2.0" for s in report["public_sources"])
    for trial in report["trials"]:
        for method in bench.METHODS:
            assert trial[method]["wall_seconds"] >= 0
        if trial["shift_diagonal"]["status"] == "not_clean":
            expected = "verified" if trial["data"] + trial["ancillas"] <= 6 else "unsupported"
            assert trial["witness_checks"]["shift_diagonal"]["status"] == expected
    adverse = next(t for t in report["trials"] if t["case"] == "parity-hmr-8-cap64")
    assert adverse["pauli"]["status"] == "not_clean"
    assert adverse["shift_diagonal"]["status"] == "inconclusive"
    assert adverse["shift_diagonal"]["peak_terms"] is None
    assert adverse["shift_diagonal"]["products"] is None
    assert adverse["shift_diagonal"]["witness"] is None
    assert adverse["shift_diagonal"]["wall_seconds"] > 0
    assert adverse["density"]["status"] == "unsupported"
    assert "certificate" not in adverse["shift_diagonal"]
    assert report["shared_case_construction"]["wall_seconds"] > 0


def _single(monkeypatch, *, dirty=False):
    program = HybridProgram(1, 1)
    if dirty:
        program.cx(0, 1)
    case = bench.Case("single", "test", program, 1, "not_clean" if dirty else "clean")
    monkeypatch.setattr(bench, "cases", lambda: ([case], []))


def test_early_failure_survives_later_success_and_cli_writes_report(monkeypatch, tmp_path):
    _single(monkeypatch)
    original, calls = bench._check_shift, [0]

    def once(*args, **kwargs):
        calls[0] += 1
        return {"status": "inconclusive", "witness": None} if calls[0] == 1 else original(*args, **kwargs)

    monkeypatch.setattr(bench, "_check_shift", once)
    output = tmp_path / "failure.json"
    assert bench.main(["--repetitions", "3", "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert [t["passed"] for t in report["trials"]] == [False, True, True]
    assert len({tuple(t["order"]) for t in report["trials"]}) == 3
    assert not report["qualification_passed"]


def test_timed_exception_preserves_cost_and_other_methods(monkeypatch):
    _single(monkeypatch)

    def broken(*args, **kwargs):
        raise RuntimeError("injected timed failure")

    monkeypatch.setattr(bench, "_check_shift", broken)
    report = bench.run(repetitions=1)
    assert not report["qualification_passed"]
    trial = report["trials"][0]
    assert trial["shift_diagonal"]["status"] == "error"
    assert "injected" in trial["shift_diagonal"]["error"]
    assert trial["shift_diagonal"]["wall_seconds"] >= 0
    assert trial["pauli"]["status"] == trial["density"]["status"] == "clean"


def test_false_witness_or_wrong_source_hash_fails_qualification(monkeypatch):
    _single(monkeypatch, dirty=True)
    original = bench._check_shift

    def false_witness(*args, **kwargs):
        return {**original(*args, **kwargs), "witness": {"assignment": 0, "probability": "1"}}

    monkeypatch.setattr(bench, "_check_shift", false_witness)
    report = bench.run(repetitions=1)
    assert not report["qualification_passed"]
    assert report["trials"][0]["witness_checks"]["shift_diagonal"]["status"] == "rejected"
    monkeypatch.setattr(bench, "_check_shift", lambda *a, **k: {
        **original(*a, **k), "source_sha256": "0" * 64})
    assert not bench.run(repetitions=1)["qualification_passed"]


def test_private_dependency_pin_failure_is_saved_before_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "BASELINE_PINS", {
        **bench.BASELINE_PINS, "src/symq/labs/backward_ancilla.py": "0" * 64})
    output = tmp_path / "source-error.json"
    assert bench.main(["--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert "pinned baseline source changed" in report["setup_error"]
    assert report["trials"] == [] and not report["qualification_passed"]


def test_failed_baseline_replay_is_not_ignored(monkeypatch):
    _single(monkeypatch)
    monkeypatch.setattr(bench.pauli, "replay_clean_ancilla",
                        lambda *a, **k: bench.pauli.AncillaResult("not_proved"))
    report = bench.run(repetitions=1)
    assert not report["qualification_passed"]
    assert report["trials"][0]["pauli_fresh_replay"]["status"] == "not_proved"


def test_missing_baseline_certificate_fails_even_when_later_trials_replay(monkeypatch, tmp_path):
    _single(monkeypatch)
    original, calls = bench._check_pauli, [0]

    def once(*args, **kwargs):
        calls[0] += 1
        result = original(*args, **kwargs)
        return {**result, "certificate": None} if calls[0] == 1 else result

    monkeypatch.setattr(bench, "_check_pauli", once)
    output = tmp_path / "missing-baseline-certificate.json"
    assert bench.main(["--repetitions", "3", "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert not report["qualification_passed"]
    assert [t["passed"] for t in report["trials"]] == [False, True, True]
    assert report["trials"][0]["pauli_fresh_replay"]["status"] == "missing_certificate"
    assert all(t["pauli_fresh_replay"]["status"] == "clean" for t in report["trials"][1:])
