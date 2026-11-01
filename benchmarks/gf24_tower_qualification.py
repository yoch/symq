"""Exact GF(2^24) multiplier report: factor fingerprint, gate counts and whole-circuit proofs.

The 99-product factorization is certified against the full multiplication tensor and its pinned
fingerprint. Each of the three multipliers is then proved equal to the schoolbook circuit on all
2^72 inputs with the packed degree-two engine (theorem ``classical_total``), and the schoolbook
circuit's output polynomials are compared with the field tensor. The gate weights are a declared
proxy, not a hardware cost. Exit code 1 when any check fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.environment import machine, receipt
from symq import ANF, make_algebra, simulate
from symq.generators.bilinear_optimization import certify_decomposition
from symq.generators.gf2n import emit, karatsuba, schoolbook, tensor
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.gf24_choice import choose_gf24
from symq.labs.gf24_order import PINNED_FACTOR_SHA256, pinned_gf24_circuit
from symq.labs.gf24_tower import GF24_MODULUS, gf24_tower_factors

N = 24


def _schoolbook_matches_tensor(circuit) -> bool:
    algebra = make_algebra("packed", 3 * N)
    outputs = [algebra.to_anf(value) for value in simulate(circuit, algebra)]
    table = tensor(N)
    for k in range(N):
        monomials = {1 << (2 * N + k)} | {(1 << i) | (1 << (N + j)) for i in range(N)
                                          for j in range(N) if table[i][j] >> k & 1}
        if outputs[2 * N + k] != ANF(frozenset(monomials)):
            return False
    return all(outputs[w] == ANF(frozenset({1 << w})) for w in range(2 * N))


def report() -> dict:
    terms = gf24_tower_factors()
    certify_decomposition(N, terms, GF24_MODULUS)
    raw = ";".join(f"{t.left:x},{t.right:x},{t.into:x}" for t in terms).encode("ascii")
    fingerprint = hashlib.sha256(raw).hexdigest()
    circuits = {
        "schoolbook-incidence": emit(N, schoolbook(N)).circuit,
        "karatsuba-pivot-scheduled": emit(N, karatsuba(N), strategy="pivot-scheduled").circuit,
        "tower-99-pinned-order": pinned_gf24_circuit(),
    }
    base = circuits["schoolbook-incidence"]
    selected = choose_gf24(ccx_weight=32, cx_weight=1)
    cases = []
    for cost in selected.alternatives:
        circuit = circuits[cost.name]
        proof = check_substitution(base, (0, len(base.gates)), circuit,
                                   contract=SubstitutionContract(), engine="packed")
        cases.append({"name": cost.name, "ccx": cost.ccx, "cx": cost.cx,
                      "weighted_cost_ccx32_cx1": cost.weighted,
                      "proved_equal_to_schoolbook": proof.equivalent,
                      "theorem": proof.theorem, "outcome": proof.outcome})
    return {
        "schema": "symq-gf24-tower-qualification-v2",
        "field": {"width": N, "modulus": hex(GF24_MODULUS)},
        "rank_one_products": len(terms),
        "factor_sha256": fingerprint,
        "factor_sha256_matches_pin": fingerprint == PINNED_FACTOR_SHA256,
        "schoolbook_outputs_equal_field_tensor": _schoolbook_matches_tensor(base),
        "source": {
            "method": "GF16 subfield / degree-six interpolation; 11 samples times 9 products",
            "polytof_upstream_commit": "0dcac107d15adc34dc646242d222f21ae7d32699",
            "reference": "https://github.com/ZIB-IOL/polytof",
            "license": "MIT",
            "bilinear_kmb_corpus_is_not_a_gf24_holdout": True,
        },
        "gate_proxy": {"ccx_weight": 32, "cx_weight": 1,
                       "chosen": selected.method, "alternatives": cases},
        "environment": machine(), "receipt": receipt(),
    }


def passed(result: dict) -> bool:
    return (result["factor_sha256_matches_pin"]
            and result["schoolbook_outputs_equal_field_tensor"]
            and all(case["proved_equal_to_schoolbook"]
                    for case in result["gate_proxy"]["alternatives"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    result = report()
    payload = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8")
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_bytes(payload)
    options.output.with_name(options.output.name + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "  " + options.output.name + "\n", encoding="ascii"
    )
    for case in result["gate_proxy"]["alternatives"]:
        print(f"{case['name']:<28} {case['ccx']:>5} CCX {case['cx']:>5} CX  {case['outcome']}")
    if not passed(result):
        print("GF24 qualification FAILED:", options.output)
        return 1
    print("GF24 tensor certified and every circuit proved; report saved:", options.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
