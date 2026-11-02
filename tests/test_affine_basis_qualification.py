from __future__ import annotations

import json
import subprocess
import sys

import pytest

from benchmarks import affine_basis as campaign


@pytest.mark.checkout
def test_provenance_records_lineage_but_requires_exact_module_bytes(monkeypatch):
    # Squash/rebase merges and shallow clones lose the pinned commit, not the bytes.
    monkeypatch.setattr(campaign, "PINNED_HEAD", "0" * 40)
    result = campaign.provenance()
    assert result["baseline_lineage"] == "pinned commit unavailable in this history"
    assert result["module_sha256"] == campaign.PINNED_MODULE_SHA256
    monkeypatch.setattr(campaign, "PINNED_MODULE_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="published baseline identity changed"):
        campaign.provenance()


@pytest.mark.checkout
def test_provenance_refuses_a_module_imported_from_elsewhere(monkeypatch, tmp_path):
    copy = tmp_path / "affine_phase.py"
    copy.write_bytes((campaign.ROOT / "src/symq/labs/affine_phase.py").read_bytes())
    monkeypatch.setattr(campaign.core, "__file__", str(copy))
    with pytest.raises(ValueError, match="outside the authenticated checkout"):
        campaign.provenance()


@pytest.mark.checkout
def test_provenance_records_an_absent_optional_tool_without_refusing(monkeypatch):
    # An install with only the ``test`` extra has no ruff; the source checks still apply.
    real = campaign.importlib.metadata.version

    def without_ruff(name):
        if name == "ruff":
            raise campaign.importlib.metadata.PackageNotFoundError(name)
        return real(name)

    monkeypatch.setattr(campaign.importlib.metadata, "version", without_ruff)
    result = campaign.provenance()
    assert result["versions"]["ruff"] is None and result["versions"]["pytest"]
    assert result["module_sha256"] == campaign.PINNED_MODULE_SHA256


def test_setup_refusal_is_written_before_exit_one(monkeypatch, tmp_path):
    def unavailable():
        raise ValueError("published baseline ancestry unavailable")

    monkeypatch.setattr(campaign, "provenance", unavailable)
    target = tmp_path / "setup-failure.json"
    assert campaign.main(["--cases", "tiny_reference", "--methods", "canonical_cache",
                          "--repetitions", "1", "--output", str(target)]) == 1
    document = json.loads(target.read_text())
    assert not document["qualified"] and document["trials"] == []
    assert document["setup_error"] == "ValueError: published baseline ancestry unavailable"


def test_positive_requires_receipt_and_fresh_replay(monkeypatch):
    monkeypatch.setattr(campaign.prototype, "run", lambda *args, **kwargs: {
        "status": "equivalent", "receipt": None, "witness": None, "metrics": {}})
    result = campaign.trial(campaign.cases()[0], "canonical_cache")
    assert not result["qualified"] and not result["source_binding_valid"]


def test_replay_exception_is_preserved(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("injected replay failure")

    monkeypatch.setattr(campaign.core, "replay_affine_phase", broken)
    result = campaign.trial(campaign.cases()[0], "canonical_cache")
    assert not result["qualified"]
    assert result["replay_error"] == "RuntimeError: injected replay failure"
    assert result["result"]["status"] == "equivalent"
    assert result["proof_and_replay_seconds"] >= result["proof_outer_seconds"]


@pytest.mark.checkout
def test_main_continues_and_writes_failed_trials_before_return_one(monkeypatch, tmp_path):
    calls = []

    def failed(case, method):
        calls.append((case["id"], method))
        return {"case_id": case["id"], "method": method, "qualified": len(calls) > 1,
                "worker_source_hashes": campaign.source_hashes(),
                "result": {"status": "error" if len(calls) == 1 else "equivalent"}}

    monkeypatch.setattr(campaign, "isolated_trial", failed)
    target = tmp_path / "failure.json"
    result = campaign.main(["--cases", "tiny_reference", "--methods", "canonical_cache", "published",
                            "--repetitions", "2", "--output", str(target)])
    document = json.loads(target.read_text())
    assert result == 1 and not document["qualified"] and len(document["trials"]) == 4
    assert [row["qualified"] for row in document["trials"]] == [False, True, True, True]
    assert {row["repetition"] for row in document["trials"]} == {0, 1}


@pytest.mark.checkout
def test_summary_cli_accepts_a_single_selected_method(tmp_path):
    target, summary = tmp_path / "single-method.json", tmp_path / "summary.json"
    assert campaign.main(["--cases", "tiny_reference", "--methods", "canonical_cache",
                          "--repetitions", "1", "--output", str(target)]) == 0
    result = subprocess.run([sys.executable, "-m", "benchmarks.affine_basis_summary", str(target),
                             "--output", str(summary)], cwd=campaign.ROOT, text=True,
                            capture_output=True, check=False, timeout=20)
    assert result.returncode == 0, result.stderr
    document = json.loads(summary.read_text())
    assert document["qualified"] and document["trials"] == 1
    assert document["paired_ratios"] == {}
    assert list(document["cases"][0]["methods"]) == ["canonical_cache"]
    assert "| Case | Cache | Status |" in result.stdout


@pytest.mark.checkout
def test_real_cli_writes_json_before_exit_one_on_cap(tmp_path):
    target = tmp_path / "term-cap.json"
    result = subprocess.run([sys.executable, "-m", "benchmarks.affine_basis",
                             "--cases", "dense_expansion_term_cap", "--methods", "canonical_cache",
                             "--repetitions", "1", "--require-decision", "--output", str(target)],
                            cwd=campaign.ROOT, text=True, capture_output=True, check=False, timeout=20)
    document = json.loads(target.read_text())
    assert result.returncode == 1 and not document["qualified"]
    assert len(document["trials"]) == 1
    assert document["trials"][0]["result"]["status"] == "inconclusive"


@pytest.mark.checkout
def test_summary_pairs_reuse_methods_with_published_and_the_lru_control(tmp_path):
    target, summary = tmp_path / "reuse.json", tmp_path / "reuse-summary.json"
    methods = ["published", "canonical_cache", "canonical_split"]
    assert campaign.main(["--cases", "tiny_reference", "early_negative_large_k", "--methods",
                          *methods, "--repetitions", "1", "--output", str(target)]) == 0
    result = subprocess.run([sys.executable, "-m", "benchmarks.affine_basis_summary", str(target),
                             "--output", str(summary)], cwd=campaign.ROOT, text=True,
                            capture_output=True, check=False, timeout=20)
    assert result.returncode == 0, result.stderr
    document = json.loads(summary.read_text())
    ratios = document["paired_ratios"]
    assert ratios["canonical_split/published:equivalent"]["pairs"] == 1
    assert ratios["canonical_split/published:equivalent"]["proof_only_pairs"] == 0
    assert ratios["canonical_split/canonical_cache:not_proved"]["proof_only_pairs"] == 1
    assert set(document["case_ratios"]["canonical_split/canonical_cache"]) == {
        "tiny_reference", "early_negative_large_k"}
    assert document["cases"][0]["methods"]["canonical_split"]["lifts_computed"] is not None
    assert "| Split |" in result.stdout


def test_generated_variations_are_labelled_and_keep_the_original_fixtures():
    specs = {case["id"]: case["spec"] for case in campaign.cases()}
    variations = [name for name in specs if name.startswith("variation_")]
    assert len(variations) == 7 and len(specs) == 30
    assert all("scale" not in spec for name, spec in specs.items() if name not in variations)


def test_operation_counts_agree_across_methods(tmp_path):
    from benchmarks import affine_basis_operations as operations

    target = tmp_path / "operations.json"
    assert operations.main(["--cases", "tiny_reference", "perturbed_small", "--factorized",
                            "--output", str(target)]) == 0
    document = json.loads(target.read_text())
    assert document["consistent"]
    rows = {(row["case_id"], row["method"]): row for row in document["rows"]}
    assert rows["tiny_reference", "published"]["lifts"] == rows["tiny_reference", "canonical"]["lifts"]
    assert rows["tiny_reference", "canonical_split"]["lifts"] < rows["tiny_reference", "canonical"]["lifts"]
    assert rows["tiny_reference", "factorized_analysis"]["status"] == "computed"
