"""Qualification-campaign checks shipped together with the evidence module."""
import json
from pathlib import Path

from benchmarks.roadmap_campaign import PINNED_MANIFEST_SHA256, _digest, _fixture
from symq.experimental.api import verify
from symq.experimental.contracts import VerificationContract
from symq.experimental.serialization import program_from_dict


def test_frozen_campaign_families_have_expected_public_verdicts_and_disjoint_sources():
    manifest = json.loads((Path(__file__).parents[1] / "benchmarks/roadmap_manifest.json").read_text())
    assert _digest(manifest) == PINNED_MANIFEST_SHA256
    partitions = {"development": set(), "holdout": set()}
    for case in manifest["cases"]:
        left, right, document = _fixture(case)
        partitions[case["partition"]].update((_digest(left), _digest(right)))
        result = verify(program_from_dict(left), program_from_dict(right),
                        VerificationContract.from_dict(document))
        assert result.outcome == case["expected"], (case["id"], result)
    assert not partitions["development"] & partitions["holdout"]
