"""P0 public HMR benchmark: source-authenticated Qualtran coherent cleanup.

Uses the already-explored Apache-2.0 source-pinned GF2Multiplication /
GF2MulMBUC m=1 and m=2 exact decompositions. No private Qant fixtures,
new holdout claim or general MQT/PyZX performance comparison.

Produces complete input JSON, explicit quantum contracts, verdicts,
cost reports, frozen candidates, independent exact Kraus oracle
receipts and SHA-256 sidecars. Negative cases remove conditional
phase feedback and MUST fail, even when classical diagonals agree.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.hmr_qualification import (
    hybrid,
    load_manifest,
    oracle_case,
    programs,
)
from symq._io import atomic_write_text
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.channel_composition import HybridFragment
from symq.labs.hmr_workflow import (
    _load_report,
    fragment_to_dict,
    main as workflow_main,
    replay_report,
)

DATASET_URL = "https://github.com/quantumlib/Qualtran"
UPSTREAM_COMMIT = "638777fac4379bc62e2a1e4a52cf1a1753895d48"


def _json_file(path: Path, value: dict) -> None:
    atomic_write_text(path, json.dumps(value, sort_keys=True, indent=2) + "\n")


def _one_case(outdir: Path, degree: int, mutation: str) -> dict:
    manifest = load_manifest()
    identifier = f"m{degree}-full-" + (
        "none" if mutation == "none" else "missing_correction"
    )
    case = next((x for x in manifest["cases"] if x["id"] == identifier), None)
    if case is None:
        raise ValueError(f"Qualtran source case {identifier!r} missing")
    # The independent exact Kraus/ket-channel oracle checks all coherences,
    # not just basis truth tables. Labels are authenticated before importing.
    oracle = oracle_case(case)
    if not oracle["expected_label_verified"]:
        raise AssertionError("independent public Qualtran coherent oracle disagrees")
    if mutation == "missing_correction" and (
        oracle["diagonals_equal"] is not True
        or oracle["first_witness"][0] == oracle["first_witness"][1]
    ):
        raise AssertionError("missing correction did not expose off-diagonal failure")

    reference, candidate = (hybrid(p) for p in programs(case))
    prefix = [HOp("cx", (0, 1))]
    suffix = [HOp("cx", (0, 1))]
    source = HybridProgram(reference.data, reference.ancillas,
                           prefix + list(reference.ops) + suffix)
    fragment = HybridFragment(reference.width, tuple(candidate.ops))
    span = [len(prefix), len(prefix) + len(reference.ops)]
    info = {
        "schema_version": 1,
        "kind": "symq_hmr_contextual_request",
        "source": "source.json",
        "replacement": "replacement.json",
        "contract": {
            "span": span, "wires": list(range(reference.width)),
            "clean": list(range(reference.data, reference.width)),
            "preserved": list(range(reference.data)),
            "discarded": [], "discarded_global": [], "observed_slots": [],
            "max_local_width": 6, "max_events": 8, "max_branches": 256,
            "weights": {
                "unit": "illustrative_integer_proxy_not_T_count",
                "by_kind": [["ccx", 12], ["hmr", 0], ["cz", 2]],
            },
            "require_saving": False,
        },
    }
    destination = outdir / identifier
    destination.mkdir(parents=True, exist_ok=True)
    _json_file(destination / "source.json", program_to_dict(source))
    _json_file(destination / "replacement.json", fragment_to_dict(fragment))
    _json_file(destination / "request.json", info)
    report_file = destination / "hmr-proof.json"
    status = workflow_main([
        "verify", str(destination / "request.json"),
        "--report", str(report_file), "--timeout", "45",
    ])
    expected = 0 if mutation == "none" else 1
    if status != expected:
        raise AssertionError(f"wrong HMR CLI classification: {identifier} {status}")
    artifact = _load_report(report_file)
    outcome = artifact["result"]["outcome"]
    if (outcome == "equivalent") != (mutation == "none"):
        raise AssertionError("coherent HMR theorem accepted a wrong correction")
    if (artifact["candidate"] is None) != (mutation != "none"):
        raise AssertionError("failed coherent proof leaked a candidate")
    fresh = replay_report(artifact, timeout_seconds=45)
    if fresh["semantic_sha256"] != artifact["semantic_sha256"]:
        raise AssertionError("saved HMR proof did not independently replay")

    public_name = f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json"
    report = {
        "schema_version": 1, "id": identifier, "degree": degree,
        "source": DATASET_URL, "upstream_commit": UPSTREAM_COMMIT,
        "license": "Apache-2.0",
        "fixture_sha256": manifest["fixture_sha256"][public_name],
        "source_status": "previously_explored_public_qualification_NOT_holdout",
        "input_coherences_exhaustively_checked": oracle["all_coherences_checked"],
        "independent_Kraus_first_difference": oracle["first_witness"],
        "offdiagonal_missing_correction": (
            mutation == "missing_correction" and oracle["diagonals_equal"]
        ),
        "expected": "equivalent" if mutation == "none" else "not_proved",
        "actual": outcome,
        "proven_application": artifact["candidate"] is not None,
        "operation_delta": artifact["result"]["cost"]["delta_ops"],
        "declared_weighted_delta": artifact["result"]["cost"]["weighted_delta"],
        "semantic_sha256": artifact["semantic_sha256"],
        "not_hardware_cost_or_official_competition_score": True,
    }
    _json_file(destination / "provenance.json", report)
    return report


def run(outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    rows = [
        _one_case(outdir, degree, mutation)
        for degree in (1, 2)
        for mutation in ("none", "missing_correction")
    ]
    summary = {
        "schema_version": 1, "source": DATASET_URL,
        "upstream_commit": UPSTREAM_COMMIT,
        "scope": "source-pinned public development HMR channel, not holdout/instrument",
        "positive_cases": sum(x["proven_application"] for x in rows),
        "correct_rejections": sum(x["actual"] == "not_proved" for x in rows),
        "cases": rows,
    }
    if summary["positive_cases"] != 2 or summary["correct_rejections"] != 2:
        raise AssertionError("HMR P0 cases failed their preregistered outcomes")
    _json_file(outdir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output_dir)
    print("Qualtran coherent HMR P0:", result["positive_cases"],
          "replayed positives,", result["correct_rejections"], "refused mutants")


if __name__ == "__main__":
    main()
