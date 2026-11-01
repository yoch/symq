"""Reproducible GF(2^24) factor/circuit cost report, not a timing benchmark.

No private fixtures, external downloads or official competition metrics.
Exact multiplication-tensor certification is performed in the generator;
this report records only the three declared physical gate-count proxies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

from symq.generators.bilinear_optimization import certify_decomposition
from symq.labs.gf24_choice import choose_gf24
from symq.labs.gf24_tower import GF24_MODULUS, gf24_tower_factors


def report() -> dict:
    terms = gf24_tower_factors()
    certify_decomposition(24, terms, GF24_MODULUS)
    raw = ";".join(f"{t.left:x},{t.right:x},{t.into:x}" for t in terms).encode("ascii")
    selected = choose_gf24(ccx_weight=32, cx_weight=1)
    cases = [
        {"name": cost.name, "ccx": cost.ccx, "cx": cost.cx,
         "proxy_weighted_cost_ccx32_cx1": cost.weighted}
        for cost in selected.alternatives
    ]
    return {
        "schema": "symq-gf24-tower-qualification-v1",
        "status": "experimental tensor upper bound and gate counts only",
        "field": {"width": 24, "modulus": hex(GF24_MODULUS)},
        "rank_one_products": len(terms),
        "factor_sha256": hashlib.sha256(raw).hexdigest(),
        "source": {
            "method": "GF16 subfield / degree-six interpolation; 11 samples times 9 products",
            "polytof_upstream_commit": "0dcac107d15adc34dc646242d222f21ae7d32699",
            "reference": "https://github.com/ZIB-IOL/polytof",
            "license": "MIT",
            "public_kaggle_is_not_gf24_holdout": True,
        },
        "gate_proxy": {"ccx_weight": 32, "cx_weight": 1,
                       "chosen": selected.method, "alternatives": cases},
        "sampled_basis_inputs_only": True,
        "not_official_quantum_competition_score": True,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    payload = (json.dumps(report(), sort_keys=True, indent=2) + "\n").encode("utf-8")
    options.output.write_bytes(payload)
    options.output.with_name(options.output.name + ".sha256").write_text(
        hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii"
    )
    print("GF24 tensor certified; report saved:", options.output)


if __name__ == "__main__":
    main()
