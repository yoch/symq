"""Deterministic GF24 subfield/outer-basis sweep for exact emitted CX counts.

This grid is only the 4 Frobenius roots of x^4+x+1 in the pinned
GF(2^24) field, crossed with beta=x^k for k=1..24. It does NOT
prove globally optimal CX count among all field isomorphisms,
bilinear decompositions or reversible linear circuits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from symq.generators.gf2n import emit
from symq.labs.gf24_tower import (
    GF24_MODULUS,
    PINNED_OUTER_BETA,
    PINNED_SUBFIELD_ROOT,
    _power,
    gf24_tower_factors,
)


def subfield_roots() -> tuple[int, ...]:
    """Reconstruct the four Frobenius conjugates in the pinned polynomial basis."""
    p = GF24_MODULUS
    for seed in range(2, 128):
        generator = _power(seed, ((1 << 24) - 1) // 15, 24, p)
        if _power(generator, 5, 24, p) == 1 or _power(generator, 3, 24, p) == 1:
            continue
        for exponent in range(15):
            root = _power(generator, exponent, 24, p)
            if _power(root, 4, 24, p) ^ root ^ 1:
                continue
            conjugates = tuple(sorted({_power(root, 2 ** k, 24, p) for k in range(4)}))
            if len(conjugates) == 4:
                return conjugates
    raise ArithmeticError("failed to reconstruct GF16 roots in the fixed GF24 model")


def sweep() -> dict:
    roots = subfield_roots()
    rows = []
    for exponent in range(1, 25):
        beta = _power(2, exponent, 24, GF24_MODULUS)
        for root in roots:
            factors = gf24_tower_factors(root=root, beta=beta)
            emitted = emit(24, list(factors), strategy="pivot-scheduled")
            digest = hashlib.sha256(
                ";".join(f"{t.left:x},{t.right:x},{t.into:x}" for t in factors)
                .encode("ascii")
            ).hexdigest()
            rows.append({
                "root": root, "beta": beta, "beta_x_exponent": exponent,
                "rank": len(factors), "ccx": emitted.ccx, "cx": emitted.cx,
                "factor_sha256": digest,
            })
    rows.sort(key=lambda row: (row["cx"], row["ccx"], row["beta_x_exponent"], row["root"]))
    best = rows[0]
    if (len(rows) != 96 or best["cx"] != 2750 or best["ccx"] != 99
            or best["root"] != PINNED_SUBFIELD_ROOT or best["beta"] != PINNED_OUTER_BETA):
        raise RuntimeError("pinned GF24 basis-sweep evidence has drifted")
    return {
        "schema": "symq-gf24-basis-grid-v1",
        "scope": "4 conjugate roots x 24 monomial outer elements, not all field bases",
        "rank_upper_bound": 99,
        "modulus": hex(GF24_MODULUS),
        "candidates": len(rows),
        "best": best,
        "results": rows,
        "not_global_cx_optimality_proof": True,
        "not_quantum_competition_metric": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = (json.dumps(sweep(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    args.output.write_bytes(payload)
    args.output.with_name(args.output.name + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print("GF24 96-basis grid qualified:", args.output)


if __name__ == "__main__":
    main()
