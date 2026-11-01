"""The Qualtran coherent rewrites, qualified through ``symq rewrite`` and ``symq replay``."""
from __future__ import annotations

import filecmp

import pytest

from benchmarks import rewrite_qualtran_hmr as qualtran
from benchmarks.rewrite_cli import INPUTS


def test_the_versioned_case_files_are_a_fresh_export_of_the_authenticated_fixtures(tmp_path):
    qualtran.export(tmp_path)
    for degree, mutant in qualtran.CASES:
        name = qualtran.identifier(degree, mutant)
        for file in INPUTS:
            assert filecmp.cmp(tmp_path / name / file, qualtran.CORPUS / name / file,
                               shallow=False), f"{name}/{file}"
    assert filecmp.cmp(tmp_path / "MANIFEST.json", qualtran.CORPUS / "MANIFEST.json",
                       shallow=False)


def test_two_valid_rewrites_are_proved_and_two_missing_corrections_refused(tmp_path):
    result = qualtran.run(tmp_path)
    assert (result["accepted"], result["refused"]) == (2, 2)
    rows = {row["id"]: row for row in result["cases"]}
    for degree, coherences, wrong in ((1, 16, 6), (2, 256, 96)):
        good, bad = rows[f"m{degree}-full-none"], rows[f"m{degree}-full-missing_correction"]
        assert (good["rewrite_exit_code"], good["replay_exit_code"]) == (0, 0)
        assert good["candidate_exported"] and good["replay"]["reverified"]
        assert good["independent_oracle"] == {"coherences_checked": coherences,
                                              "differing": 0, "diagonal_differs": False}
        assert (bad["rewrite_exit_code"], bad["replay_exit_code"]) == (2, 2)
        assert not bad["candidate_exported"] and bad["application"] == "not_proved"
        assert bad["independent_oracle"]["differing"] == wrong
        assert not bad["independent_oracle"]["diagonal_differs"]
        for row in (good, bad):
            assert row["inputs_deleted_before_replay"]
            assert row["execution"]["status"] == "completed"
    # Toffolis are priced 12 under the declared proxy: both valid rewrites are cheaper.
    assert rows["m1-full-none"]["cost"]["weighted_delta"] == -10
    assert rows["m2-full-none"]["cost"]["weighted_delta"] == -40
    assert (tmp_path / "m1-full-none" / "report.json").exists()
    assert not result["receipt"]["symq_location"].startswith("/")  # no absolute path


def test_any_departure_from_the_preregistered_outcome_is_an_error(tmp_path):
    row = next(r for r in qualtran.run(tmp_path)["cases"] if r["mutant"])
    for change in ({"candidate_exported": True}, {"rewrite_exit_code": 0},
                   {"replay": {"reverified": False}},
                   {"independent_oracle": {**row["independent_oracle"],
                                           "diagonal_differs": True}}):
        with pytest.raises(AssertionError):
            qualtran.check({**row, **change})
