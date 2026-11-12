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
        for name in ("pauli", "shift_diagonal"):
            if trial[name]["status"] == "not_clean":
                check = trial["witness_checks"][name]
                assert check["status"] == "verified"
                wide = trial["data"] + trial["ancillas"] > 6
                assert check["oracle"] == ("sparse_branch" if wide else "density")
    adverse = next(t for t in report["trials"] if t["case"] == "parity-hmr-8-cap64")
    assert adverse["pauli"]["status"] == "not_clean"
    assert adverse["shift_diagonal"]["status"] == "inconclusive"
    # The work done before the cap is reported, with the cap that stopped it.
    assert adverse["shift_diagonal"]["resource"] == "terms"
    assert adverse["shift_diagonal"]["limit"] == 64
    assert adverse["shift_diagonal"]["observed"] > 64
    assert type(adverse["shift_diagonal"]["peak_terms"]) is int
    assert type(adverse["shift_diagonal"]["products"]) is int
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


def _wide_dirty(monkeypatch):
    wide = HybridProgram(7, 1).cx(6, 7)  # width 8 > dense cap; true witness is input 64
    case = bench.Case("wide-dirty", "test", wide, 7, "not_clean", shift_expected="not_clean")
    monkeypatch.setattr(bench, "cases", lambda: ([case], []))
    return case


def test_wide_witness_is_checked_by_the_sparse_oracle(monkeypatch):
    _wide_dirty(monkeypatch)
    trial = bench.run(repetitions=1)["trials"][0]
    check = trial["witness_checks"]["shift_diagonal"]
    assert check == {**check, "status": "verified", "oracle": "sparse_branch", "probability": "1"}
    assert trial["density"]["status"] == "unsupported"


def test_false_wide_witness_fails_qualification(monkeypatch):
    from fractions import Fraction

    from symq.labs import shift_diagonal_ancilla as module

    _wide_dirty(monkeypatch)
    real = module.check_shift_diagonal

    def lying(*args, **kwargs):
        from dataclasses import replace

        return replace(real(*args, **kwargs), assignment=0, probability=Fraction(7, 3))

    monkeypatch.setattr(bench, "check_shift_diagonal", lying)
    report = bench.run(repetitions=1)
    assert report["trials"][0]["witness_checks"]["shift_diagonal"]["status"] == "rejected"
    assert not report["qualification_passed"]


def test_unverifiable_wide_witness_fails_qualification(monkeypatch):
    _wide_dirty(monkeypatch)
    monkeypatch.setattr(bench, "SPARSE_LIMITS", {"max_branches": 0, "max_amplitudes": 0})
    report = bench.run(repetitions=1)
    assert report["trials"][0]["witness_checks"]["shift_diagonal"]["status"] == "unsupported"
    assert not report["qualification_passed"]


def test_sparse_oracle_agrees_with_the_density_oracle_on_small_programs():
    import random
    import time

    from tests.testkit.sparse_branch_oracle import error_probability

    rng = random.Random(150)
    kinds = ("x", "cx", "ccx", "swap", "z", "cz", "hmr", "measure_z", "reset")
    checked = 0
    for _ in range(60):
        data, ancillas = rng.randint(1, 3), rng.randint(1, 2)
        width = data + ancillas
        program = HybridProgram(data, ancillas)
        slots = 0
        for _ in range(rng.randint(1, 6)):
            kind = rng.choice(kinds)
            arity = {"x": 1, "z": 1, "hmr": 1, "measure_z": 1, "reset": 1,
                     "cx": 2, "swap": 2, "cz": 2, "ccx": 3}[kind]
            if arity > width:
                continue
            wires = rng.sample(range(width), arity)
            if kind in ("hmr", "measure_z"):
                getattr(program, kind)(*wires, f"b{slots}")
                slots += 1
            else:
                getattr(program, kind)(*wires)
        target = data + ancillas - 1
        case = bench.Case("probe", "test", program, target, "clean")
        for x in range(1 << data):
            dense = bench._probability(case, x, time.perf_counter() + 30)
            assert error_probability(program, target, x) == dense
            checked += 1
    assert checked > 100
