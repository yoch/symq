"""Public HMR qualification protocol tests, independent of its timing data."""
from pathlib import Path

import pytest

from benchmarks import hmr_qualification as campaign


def test_frozen_public_manifest_is_licensed_and_is_not_a_holdout():
    manifest = campaign.load_manifest()
    assert len(manifest["cases"]) == 9
    assert manifest["default_repetitions"] == 15
    assert manifest["partition"] == "previously_explored_public_qualification"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["backends"] == ["zdd", "zdd-native"]
    assert manifest["limits"]["memory_bytes"] == 2 * 1024**3


@pytest.mark.parametrize("case", campaign.load_manifest()["cases"], ids=lambda c: c["id"])
def test_all_public_case_labels_are_checked_on_every_coherence(case):
    decision = campaign.oracle_case(case)
    assert decision["expected_label_verified"]
    assert decision["all_coherences_checked"] == 1 << (4 * case["degree"])
    if case["mutation"] == "missing_correction":
        assert decision["diagonals_equal"]
        x, y = decision["first_witness"]
        assert x != y


def test_theorem_and_width_matrix_stays_explicit():
    matrix = campaign.semantic_matrix()
    assert all(r["strict_O1_O2"]["equivalent"] for r in matrix["restricted_branch"])
    assert all(r["result"]["equivalent"] for r in matrix["derived_instruments"])
    assert all(r["unprepared_cleanup_counterexample"]["outcome"] == "different"
               for r in matrix["missing_preparation"])
    boundary = {(r["data"], r["backend"]): r["inspection"]
                for r in matrix["static_connected_width_controls"]}
    assert not boundary[36, "zdd-native"]["static_admissible"]
    assert boundary[36, "zdd-native-wide"]["static_admissible"]
    assert not boundary[36, "zdd-native-blocks"]["static_admissible"]
    assert boundary[64, "zdd-native-wide"]["static_admissible"]
    assert not boundary[65, "zdd-native-wide"]["static_admissible"]
    proof = matrix["public_gadget_connected_composition"]
    assert proof["proof"]["global_width"] == 65
    assert proof["proof"]["slots"] == 2
    assert set(proof["mutants_rejected"]) == {"dirty_clean_ancilla_claim", "missing_local_feedback"}
    records = matrix["channel_not_instrument"]
    assert records["forgotten_channel"]["equivalent"]
    assert not records["observed_instrument"]["equivalent"]
    trace = matrix["reduced_not_full"]
    assert trace["full"]["outcome"] == "different"
    assert trace["reduced"]["outcome"] == "equivalent"
    branch = matrix["channel_not_strict_branch"]
    assert branch["channel"]["outcome"] == "equivalent"
    assert not branch["strict_branch"]["equivalent"]
    assert branch["strict_branch"]["violations"]


def test_source_manifest_rejects_forged_fixture_bytes(tmp_path, monkeypatch):
    manifest = campaign.load_manifest()
    root = tmp_path / "forged"
    for name in manifest["fixture_sha256"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((campaign.ROOT / name).read_bytes())
    selected = next(iter(manifest["fixture_sha256"]))
    (root / selected).write_bytes(b"changed source")
    monkeypatch.setattr(campaign, "ROOT", root)
    with pytest.raises(ValueError, match="fixture changed"):
        campaign.load_manifest(Path(campaign.MANIFEST))


@pytest.mark.parametrize("field", ("head", "native_sha256", "sources"))
def test_worker_rejects_changed_source_or_binary_before_verification(field, monkeypatch):
    from copy import deepcopy

    from symq import experimental
    from symq.backends import has_native

    if not has_native():
        pytest.skip("native provenance checks require the optional extension")
    frozen = deepcopy(campaign.snapshot())
    frozen[field] = {"forged": "source"} if field == "sources" else "forged"

    def never_run(*args, **kwargs):
        raise AssertionError("verification started after a provenance mismatch")

    monkeypatch.setattr(experimental, "verify", never_run)
    with pytest.raises(RuntimeError, match="provenance mismatch"):
        campaign._trial(campaign.load_manifest()["cases"][0], "zdd", frozen)
