"""The qualification must retain adverse cases, early failures and source pins."""
import json
from pathlib import Path

from testkit.scalar_channel import coherence_image as independent_phase_image

from benchmarks import backward_ancilla as bench
from symq.experimental.hybrid import HybridProgram, coherence_image
from symq.labs.backward_ancilla import AncillaResult, check_clean_ancilla
from symq.labs.qualtran import load_qualtran_fixture


def test_public_corpus_pins_and_contract_distinctions():
    cases, sources = bench._public_cases()
    assert len(sources) == 2 and len(cases) == 12
    assert {p["git_blob_sha1"] for p in sources} == set(bench.PINS.values())
    assert all(p["upstream"]["license"] == "Apache-2.0" for p in sources)
    for case in cases:
        assert check_clean_ancilla(case.program, case.target).status == case.expected
        if "missing-phase" in case.name:
            assert case.expected == "clean"
        if "missing-cleanup" in case.name:
            assert case.expected == "not_clean"


def test_fixture_lowering_matches_independent_sign_hmr_kraus_oracle():
    for degree in (1, 2):
        fixture = load_qualtran_fixture(
            bench.ROOT / f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json")
        _, phase = fixture.programs()
        hybrid = bench._hybrid(phase)
        for x in range(1 << phase.data):
            for y in range(1 << phase.data):
                assert coherence_image(hybrid, x, y) == independent_phase_image(
                    phase, x, y, trace_ancillas=False)


def test_all_development_cases_are_qualified_and_adverse_costs_retained():
    report = bench.run(repetitions=1)
    assert report["qualification_passed"]
    assert len(report["trials"]) == 23
    statuses = {trial["backward"]["status"] for trial in report["trials"]}
    assert statuses == {"clean", "not_clean", "inconclusive"}
    capped = next(t for t in report["trials"] if t["case"] == "controlled-expansion-work-cap")
    assert capped["backward"]["certificate"] is None
    # The work done up to the cap is reported (it used to be None), never zero work.
    assert capped["backward"]["pauli_products"] == 1001
    assert capped["backward"]["wall_seconds"] > 0
    assert capped["oracle"]["status"] == "unsupported"
    for trial in report["trials"]:
        assert trial["backward"]["wall_seconds"] >= 0
        assert trial["backward"]["peak_python_bytes"] > 0
        if trial["backward"]["status"] == "clean":
            assert trial["replay"]["status"] == "clean"


def test_early_failure_cannot_be_hidden_by_later_success(monkeypatch, tmp_path):
    sample = bench.Case("single", HybridProgram(1, 1), 1, "clean")
    monkeypatch.setattr(bench, "cases", lambda: ([sample], []))
    original, calls = bench.check_clean_ancilla, [0]

    def fails_once(*args, **kwargs):
        calls[0] += 1
        return AncillaResult("inconclusive") if calls[0] == 1 else original(*args, **kwargs)

    monkeypatch.setattr(bench, "check_clean_ancilla", fails_once)
    path = tmp_path / "failure.json"
    assert bench.main(["--repetitions", "3", "--output", str(path)]) == 1
    report = json.loads(path.read_text())
    assert [t["passed"] for t in report["trials"]] == [False, True, True]
    assert not report["qualification_passed"]


def test_timed_exception_retains_error_cost_and_later_trials(monkeypatch, tmp_path):
    sample = bench.Case("single", HybridProgram(1, 1), 1, "clean")
    monkeypatch.setattr(bench, "cases", lambda: ([sample], []))
    original, calls = bench._check, [0]

    def throws_once(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("injected qualification failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(bench, "_check", throws_once)
    path = tmp_path / "exception.json"
    assert bench.main(["--repetitions", "2", "--output", str(path)]) == 1
    report = json.loads(path.read_text())
    first, second = report["trials"]
    assert first["backward"]["status"] == "error"
    assert "injected" in first["backward"]["error"]
    assert first["backward"]["wall_seconds"] >= 0
    assert first["oracle"]["status"] == "clean"
    assert not first["passed"] and second["passed"]


def test_failed_fresh_replay_fails_qualification(monkeypatch):
    sample = bench.Case("single", HybridProgram(1, 1), 1, "clean")
    monkeypatch.setattr(bench, "cases", lambda: ([sample], []))
    monkeypatch.setattr(bench, "replay_clean_ancilla", lambda *a, **k: AncillaResult("not_proved"))
    assert not bench.run(repetitions=1)["qualification_passed"]


def test_source_authentication_failure_is_saved_before_exit(monkeypatch, tmp_path):
    source = bench.ROOT / "benchmarks/corpus/qualtran/gf2mul_mbuc_m1.json"
    local = tmp_path / source.relative_to(bench.ROOT)
    local.parent.mkdir(parents=True)
    # A whitespace-only edit preserves the JSON and its self-reported hashes.
    local.write_bytes(source.read_bytes() + b"\n")
    monkeypatch.setattr(bench, "ROOT", Path(tmp_path))
    output = tmp_path / "source-error.json"
    assert bench.main(["--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert "pinned Git blob" in report["setup_error"]
    assert not report["qualification_passed"] and report["trials"] == []


def test_bare_statuses_without_receipt_or_witness_fail(monkeypatch):
    clean = bench.Case("clean-no-receipt", HybridProgram(1, 1), 1, "clean")
    dirty = bench.Case("dirty-no-witness", HybridProgram(1, 1).cx(0, 1), 1, "not_clean")
    monkeypatch.setattr(bench, "cases", lambda: ([clean, dirty], []))
    monkeypatch.setattr(bench, "check_clean_ancilla", lambda program, target, **kwargs:
                        AncillaResult("clean" if not program.ops else "not_clean"))
    report = bench.run(repetitions=1)
    assert [t["passed"] for t in report["trials"]] == [False, False]
    assert not report["qualification_passed"]


def test_wide_witness_without_an_independent_check_fails(monkeypatch):
    from fractions import Fraction

    from symq.labs.backward_ancilla import AncillaWitness

    wide = HybridProgram(7, 1).cx(6, 7)
    monkeypatch.setattr(bench, "cases", lambda: ([bench.Case(
        "wide-dirty", wide, 7, "not_clean", oracle_expected="unsupported")], []))
    monkeypatch.setattr(bench, "check_clean_ancilla", lambda *a, **k: AncillaResult(
        "not_clean", witness=AncillaWitness(0, Fraction(7, 3))))
    report = bench.run(repetitions=1)
    trial = report["trials"][0]
    assert trial["witness_replayed"] is None and not trial["passed"]
    assert not report["qualification_passed"]


def test_replay_is_pinned_to_the_case_target(monkeypatch):
    sample = bench.Case("single", HybridProgram(1, 1), 1, "clean")
    monkeypatch.setattr(bench, "cases", lambda: ([sample], []))
    seen = []
    original = bench.replay_clean_ancilla

    def spy(*args, **kwargs):
        seen.append(kwargs.get("target"))
        return original(*args, **kwargs)

    monkeypatch.setattr(bench, "replay_clean_ancilla", spy)
    assert bench.run(repetitions=1)["qualification_passed"]
    assert seen == [1]
