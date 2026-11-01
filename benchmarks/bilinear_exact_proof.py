"""Reproducible GF24 whole-unitary substitution receipt (no SAT needed).

The source and replacement are strictly phase-free, reversible CX/CCX
bilinear multipliers on a dirty accumulator, embedded in a nontrivial
78-wire context. These are public/synthetic development fixtures,
not an independent Kaggle/Qant competition workload or sealed holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

from symq import Budget, Circuit
from symq.circuit import Gate
from symq.generators import gf2n
from symq.labs.bilinear_exact_substitution import (
    BilinearWeights,
    optimize_gf24_substitution,
)


def report() -> dict:
    width = 78
    mapping = tuple(range(2, 74))
    source_local = gf2n.emit(24, gf2n.karatsuba(24), strategy="pivot-scheduled").circuit
    source_block = Circuit(
        width, [Gate(g.name, tuple(mapping[i] for i in g.qubits))
                for g in source_local.gates],
    )
    prefix = Circuit(width).cx(0, mapping[0]).ccx(mapping[1], 1, 77)
    suffix = Circuit(width).cx(mapping[-1], 0).mcx(2, 3, 74, 77)
    source = Circuit(width, prefix.gates + source_block.gates + suffix.gates)
    span = (len(prefix.gates), len(prefix.gates) + len(source_block.gates))
    weights = BilinearWeights(ccx=32, cx=1)
    method, applied = optimize_gf24_substitution(
        source, span, wires=mapping, weights=weights, budget=Budget(max_seconds=30)
    )
    proof = applied.proof
    assert method == "tower-99-pivot-scheduled"
    assert proof.equivalent and proof.weighted_delta == -1122
    payload = asdict(proof)
    return {
        "schema": "symq-bilinear-exact-substitution-v1",
        "source": {
            "kind": "synthetic GF24 Karatsuba block, independent GF24 tensor check",
            "field_modulus": "0x100001b",
            "reference": "https://github.com/ZIB-IOL/polytof",
            "reference_commit": "0dcac107d15adc34dc646242d222f21ae7d32699",
            "reference_license": "MIT",
            "uses_public_kaggle_fixtures": False,
            "uses_private_project_fixtures": False,
        },
        "selected_method": method,
        "proof": payload,
        "assumptions": {
            "input_domain": "ALL computational basis states, dirty A/B/Z",
            "common_context": "same prefix and suffix, no phase/measurement/reset",
            "unitary_scope": "phase-free reversible CX/CCX/MCX only",
            "no_sat_solver_required": True,
            "no_hmr_or_general_qasm_claim": True,
            "no_independent_proof_certificate_claim": True,
            "no_official_kaggle_score_claim": True,
        },
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = (json.dumps(report(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.output.write_bytes(payload)
    args.output.with_name(args.output.name + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print("GF24 exact full-unitary substitution certified:", args.output)


if __name__ == "__main__":
    main()
