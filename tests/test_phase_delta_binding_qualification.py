"""The program phase qualification keeps every failure visible and checks it against the oracle."""
from __future__ import annotations

import json
from dataclasses import replace

from benchmarks import phase_delta_binding as qualification
from symq.errors import InternalInconsistency


def test_public_qualification_cases_and_scalar_evidence():
    evidence = qualification.run(repetitions=1)
    assert evidence["passed"] is True and evidence["failed_trials"] == 0
    assert evidence["fixture"]["commit"] == "638777fac4379bc62e2a1e4a52cf1a1753895d48"
    assert evidence["fixture"]["license"] == "Apache-2.0"
    rows = {row["id"]: row for row in evidence["cases"]}
    assert [row["outcome"] for row in evidence["cases"]] == [
        "proved", "not_proved", "not_proved", "proved", "not_proved", "not_proved",
        "not_proved", "inconclusive",
    ]
    public = rows["public_programs"]
    assert public["oracle"] == {"inputs": 256, "output_mismatches": 0,
                                "phase_turns": ["7/8"], "global_turn": "7/8"}
    assert public["receipt"]["constant"] == 14 and public["receipt"]["k"] == 4
    assert public["receipt"]["expected_constant"] == 14
    assert rows["stale_delta_for_other_right"]["receipt"]["obligation"] == "phase_difference"
    assert rows["different_outputs"]["receipt"]["obligation"] == "outputs"
    assert rows["missing_last_ccx"]["receipt"]["obligation"] == "prefix_phase"
    exhausted = rows["budget_exhausted"]
    assert exhausted["receipt"]["obligation"] == "resources"
    assert exhausted["trials"][0]["replay"]["status"] == "refused"
    for row in evidence["cases"]:
        assert row["receipt"]["candidate_authorized"] is False
        assert row["receipt"]["controlled_use_authorized"] is False
        if row["outcome"] != "inconclusive":
            assert row["trials"][0]["replay"]["status"] == "matched"


def test_first_wrong_verdict_then_correct_still_fails_and_writes_json(tmp_path, monkeypatch):
    actual = qualification.check_program_phase_difference
    calls = 0

    def first_wrong(*args, **kwargs):
        nonlocal calls
        calls += 1
        proof = actual(*args, **kwargs)
        if calls == 1:
            return replace(proof, outcome="not_proved", constant=None,
                           reason="injected early incorrect verdict")
        return proof

    monkeypatch.setattr(qualification, "check_program_phase_difference", first_wrong)
    output = tmp_path / "failed-qualification.json"
    assert qualification.main(["--repetitions", "2", "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert report["passed"] is False and report["failed_trials"] == 1
    public = report["cases"][0]
    assert public["passed"] is False and public["outcome"] == "mixed"
    assert public["receipt"] is None
    first, second = public["trials"]
    assert first["receipt"]["reason"] == "injected early incorrect verdict"
    assert {f["stage"] for f in first["failures"]} >= {"expected_outcome", "replay"}
    assert "scalar_oracle" not in {f["stage"] for f in first["failures"]}
    assert second["passed"] is True and second["replay"]["status"] == "matched"
    assert all(row["passed"] for row in report["cases"][1:])


def test_early_crash_is_preserved_after_later_success(tmp_path, monkeypatch):
    actual = qualification.check_program_phase_difference
    calls = 0

    def first_crash(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InternalInconsistency("injected")
        return actual(*args, **kwargs)

    monkeypatch.setattr(qualification, "check_program_phase_difference", first_crash)
    output = tmp_path / "crash.json"
    assert qualification.main(["--repetitions", "2", "--output", str(output)]) == 1
    first, second = json.loads(output.read_text())["cases"][0]["trials"]
    assert first["outcome"] == "error" and first["receipt"] is None
    assert first["replay"]["status"] == "not_run"
    assert first["failures"][0] == {"stage": "verification", "type": "InternalInconsistency",
                                    "detail": "injected"}
    assert second["passed"] is True


def test_wrong_proved_constant_fails_the_scalar_oracle(tmp_path, monkeypatch):
    import symq.labs.phase_delta_binding as module

    actual = module.check_program_phase_difference

    def shifted(*args, **kwargs):
        proof = actual(*args, **kwargs)
        if proof.outcome == "proved":
            return replace(proof, constant=(proof.constant + 3) % (1 << proof.k))
        return proof

    monkeypatch.setattr(qualification, "check_program_phase_difference", shifted)
    output = tmp_path / "wrong-constant.json"
    assert qualification.main(["--repetitions", "1", "--output", str(output)]) == 1
    public = json.loads(output.read_text())["cases"][0]
    assert public["outcome"] == "proved" and public["passed"] is False
    assert {f["stage"] for f in public["failures"]} == {"scalar_oracle", "replay"}


def test_fixture_whose_truth_is_mislabelled_is_flagged():
    case = qualification.cases()[0][0]
    oracle = qualification._oracle(case)
    trial = qualification._trial(replace(case, claim_true=False), oracle, 1)
    assert "fixture_truth" in {f["stage"] for f in trial["failures"]}


def test_accepted_inconclusive_replay_is_a_failure(monkeypatch):
    case = next(c for c in qualification.cases()[0] if c.expected == "inconclusive")
    monkeypatch.setattr(qualification, "replay_program_phase_difference",
                        lambda *args, **kwargs: qualification.check_program_phase_difference(
                            case.prefix, case.left, case.right, case.certificate,
                            initial_constants=case.constants,
                            expected_constant=case.expected_constant,
                            budget=qualification.Budget(**dict(case.limits))))
    trial = qualification._trial(case, qualification._oracle(case), 1)
    assert trial["passed"] is False and "replay" in {f["stage"] for f in trial["failures"]}
