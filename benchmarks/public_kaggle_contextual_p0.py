"""End-to-end P0 demonstration on one *byte-pinned public* GF16 KMB source.

Original circuit: James Barlow's exposed VQCC bilinear agent-evaluation
dataset, Apache-2.0 declared, gf16-07.kmb (not a blind holdout).
The converter uses the independent strict KMB decoder in SymQ's
benchmarks and checks full classical semantics against its interpreter.
No upstream evaluator code is copied or executed here.

Outputs: imported 13-wire source JSON, 13-wire replacement JSON,
explicit contextual cut contract/request JSON, full proof/cost
receipt JSON + SHA-256 sidecar, and a provenance summary JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.kaggle_bilinear_eval import (
    DATASET_URL,
    independent_product,
    manifest,
    source_starts,
)
from benchmarks.kaggle_bilinear_kmb import parse, simulate
from symq._io import atomic_write_text
from symq.circuit import Circuit
from symq.generators import gf2n
from symq.labs.substitution_workflow import _read_report, replay_report
from symq.labs.substitution_workflow import main as workflow_main

PUBLIC_ID = "gf16-07"
N = 4
MODULUS = 0x13
EXTRA_WIRE = 12


def _json_file(path: Path, value: dict) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _as_json(circuit: Circuit) -> dict:
    return {"kind": "classical_reversible", "width": circuit.width,
            "gates": [[g.name, list(g.qubits)] for g in circuit.gates]}


def _source_circuit() -> tuple[Circuit, str]:
    row = next((r for r in manifest() if r["id"] == PUBLIC_ID), None)
    if row is None or row["width"] != N or row["modulus"] != MODULUS:
        raise ValueError("public KMB corpus manifest is unexpected")
    raw = source_starts()[row["kmb"]]
    digest = hashlib.sha256(raw).hexdigest()
    if digest != row["sha256"]:
        raise ValueError("public source KMB SHA-256 differs from its original manifest")
    width, operations = parse(raw)
    if width != 3 * N:
        raise ValueError("unexpected KMB register layout")
    extracted = Circuit(width)
    for op, left, right, target in operations:
        if op == 33:
            extracted.cx(left, right)
        elif op == 34:
            extracted.cx(left, right).cx(right, left).cx(left, right)
        elif op == 49:
            extracted.ccx(left, right, target)
        else:
            raise ValueError("KMB contains an unsupported gate")
    # Fully check the lossless lowering of the original independently of
    # the candidate compiler, including every dirty output value.
    for x in range(1 << width):
        expected = simulate(operations, x)
        product = independent_product(x & 15, (x >> 4) & 15, N, MODULUS)
        from_arithmetic = (x & 255) | ((((x >> 8) ^ product) & 15) << 8)
        if extracted.run(x) != expected or expected != from_arithmetic:
            raise ValueError("public KMB original has unexpected arithmetic semantics")
    return extracted, digest


def run(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    original, original_sha = _source_circuit()
    replacement = gf2n.tower_multiplier(N, modulus=MODULUS)
    prefix = Circuit(13).cx(0, EXTRA_WIRE).cx(0, EXTRA_WIRE).cx(1, 7)
    suffix = Circuit(13).cx(11, 0).cx(10, 2)
    source = Circuit(13, prefix.gates + original.gates + suffix.gates)
    candidate = Circuit(13, list(replacement.gates))
    span = [len(prefix.gates), len(prefix.gates) + len(original.gates)]
    request = {
        "schema_version": 1,
        "kind": "symq_contextual_substitution_request",
        "source": "source.json",
        "replacement": "replacement.json",
        "span": span,
        "contract": {
            "initial_constants": [[EXTRA_WIRE, 0]],
            "clean_at_cut": [EXTRA_WIRE],
            "restored_at_cut": [],
            "cut_assumption": None,
        },
        "weights": {"x": 1, "cx": 1, "ccx": 32, "mcx": 32},
    }
    _json_file(destination / "source.json", _as_json(source))
    _json_file(destination / "replacement.json", _as_json(candidate))
    _json_file(destination / "request.json", request)
    receipt = destination / "contextual-proof.json"
    if workflow_main(["verify", str(destination / "request.json"),
                      "--report", str(receipt), "--timeout", "30"]) != 0:
        raise ValueError("real public GF16 contextual workflow was not proved")
    artifact = _read_report(receipt)
    if artifact["result"]["outcome"] != "equivalent" or artifact["candidate"] is None:
        raise ValueError("public contextual substitution had no proved candidate")
    if workflow_main(["replay", str(receipt), "--timeout", "30"]) != 0:
        raise ValueError("self-contained report failed a fresh SAT replay")
    replayed = replay_report(artifact)
    if replayed["candidate"] != artifact["candidate"]:
        raise ValueError("the replayed public candidate differs from saved result")
    summary = {
        "schema_version": 1,
        "dataset_url": DATASET_URL,
        "id": PUBLIC_ID,
        "source_author": "James Barlow",
        "source_license": "Apache-2.0 declared in original public README",
        "source_kmb_sha256": original_sha,
        "source_kind": "exposed public development case, NOT an untouched holdout",
        "modulus": hex(MODULUS),
        "original_gates": len(original.gates),
        "replacement_gates": len(replacement.gates),
        "context_width": 13,
        "span": span,
        "result": artifact["result"]["outcome"],
        "weighted_delta_proxy": artifact["result"]["cost"]["weighted_delta"],
        "semantic_sha256": artifact["semantic_sha256"],
        "candidate_sha256": artifact["result"]["candidate_sha256"],
        "not_coherent_hmr_theorem": True,
        "not_official_kaggle_competition_score": True,
    }
    if summary["weighted_delta_proxy"] >= 0:
        raise ValueError("public P0 demo has no cost improvement under pinned weights")
    _json_file(destination / "provenance.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.output_dir)
    print("Public GF16 P0 contextual workflow qualified:", summary["source_kmb_sha256"])


if __name__ == "__main__":
    main()
