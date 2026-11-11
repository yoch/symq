"""Reproducible, bounded development qualification of bilinear phase synthesis.

Reports exact structural counts and coverage, not a runtime speedup. Outcomes
with exhausted budgets remain inconclusive. Outputs must be new. No private
fixtures or external repositories are needed.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import random
import resource
import subprocess
import sys
import time
from pathlib import Path

from symq.labs.bilinear_phase_fusion.checker import Inconclusive, Rejected, check_outcome
from symq.labs.bilinear_phase_fusion.compiler import compile_bank, digest
from symq.labs.bilinear_phase_fusion.preparation import emit_source, to_symq
from symq.labs.bilinear_phase_fusion.runtime import check_source_certificate, preparation_document


def run(*, quick=False):
    """Rebuild all programs and branch checks; no imported verdicts or timings."""
    if not __debug__:
        raise RuntimeError("qualification requires assertions")
    began, cpu = time.monotonic(), time.process_time()
    rows, passed = [], True
    cases = (
        [(2, 7, 2), (3, 11, 3)]
        if quick
        else [
            (2, 7, 3),
            (3, 11, 3),
            (4, 19, 2),
            (12, 0x1053, 1),
            (12, 0x1053, 2),
            (12, 0x1053, 4),
            (12, 0x1053, 8),
            (12, 0x1053, 69),
        ]
    )
    rng = random.Random(20261112)
    for m, modulus, bank in cases:
        compile_trials = []
        for _ in range(3):
            start = time.monotonic()
            p = compile_bank(m, modulus, bank)
            compile_trials.append(time.monotonic() - start)
        if m < 12 or bank == 1:
            outcomes = [list(s) for s in itertools.product(range(1 << m), repeat=bank)]
            coverage = "exhaustive classical outcomes, exact identity on every quantum input"
        else:
            outcomes = [[0] * bank]
            outcomes += [
                [value if j == i else 0 for j in range(bank)]
                for i in range(bank)
                for value in (1, 4095)
            ]
            outcomes += [[1] * bank, [4095] * bank]
            outcomes += [[rng.randrange(4096) for _ in range(bank)] for _ in range(64)]
            coverage = "seeded development sample plus every pivot position, not exhaustive"
        checks = []
        for s in outcomes:
            try:
                r = check_outcome(p, s)
                assert r["ccz"] == r["bilinear_rank"] == (m if any(s) else 0)
                checks.append({"status": "proved", **r})
            except Inconclusive as error:
                passed = False
                checks.append({"status": "inconclusive", "outcomes": s, "reason": str(error)})
            except Rejected as error:
                passed = False
                checks.append({"status": "rejected", "outcomes": s, "reason": str(error)})
        rows.append(
            {
                "field": p["field"],
                "bank": bank,
                "program_sha256": digest(p),
                "coverage": coverage,
                "outcomes_checked": len(checks),
                "checks": checks,
                "quantum_width": p["width"],
                "new_quantum_ancillas": 0,
                "extra_hmr": 0,
                "boolean_nodes": len(p["classical"]),
                "quantum_slots": len(p["quantum"]),
                "separate_rank_phase_ccz_max": m * bank,
                "shared_and_cache_ccx": m,
                "shared_and_cache_extra_qubits_and_hmr": m,
                "compile_wall_seconds_3_trials": compile_trials,
                "limits": {"branch_seconds": 30, "m_max": 16, "bank_max": 128},
            }
        )
    p = compile_bank(3, 11, 2)
    source = to_symq(emit_source(3, 11, 2))
    cert = {
        "schema": "bilinear-phase-erasure-branch-v1",
        "preparation_sha256": digest(preparation_document(source, p)),
        "program_sha256": digest(p),
        "outcomes": [1, 7],
    }
    source_replay = check_source_certificate(source, p, cert)
    root = Path(__file__).resolve().parents[1]
    files = [Path(__file__), *sorted((root / "src/symq/labs/bilinear_phase_fusion").glob("*.py"))]
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {
        "schema": "bilinear-phase-qualification-v1",
        "passed": passed,
        "rows": rows,
        "prepared_source_replay": source_replay,
        "provenance": {
            "commit": commit,
            "command": sys.argv,
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "sources": {
                str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
            },
            "sample_seed": 20261112,
            "cohort": "constructed development, no untouched holdout claims",
            "peak_process_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "wall_seconds": time.monotonic() - began,
            "cpu_seconds": time.process_time() - cpu,
        },
        "limits": {
            "application_site_qualified": False,
            "formal_verification": False,
            "runtime_performance_advantage_claimed": False,
            "classical_adaptivity_in_phase_ir": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    result = run(quick=args.quick)
    with (args.out / "qualification.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "branches": sum(r["outcomes_checked"] for r in result["rows"]),
                "wall_seconds": result["provenance"]["wall_seconds"],
            }
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
