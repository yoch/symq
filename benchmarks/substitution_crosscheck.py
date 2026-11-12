"""Matched *full-unitary permutation* baselines on the same GF(2^n) pairs.

Only X/CX/CCX/MCX reversible circuits are compared. For these functions,
classical all-input equality and unitary equality up to global phase are the
same theorem. No HMR channel/instrument or restricted input-domain comparison
is claimed. MQT QCEC uses the existing exact alternating checker adapter.

Run with the external optional dependencies:
    python -m benchmarks.substitution_crosscheck --output /tmp/crosscheck.json

Each SAT/QCEC cell uses a separate spawned process with fixed resource limits;
the full public call (including conversion) is timed. Results are descriptive
and are NOT an independent compiler-corpus or broad performance ranking.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .environment import machine, receipt
from .substitution_qualification import (
    _arithmetic_pair,
    _digest,
    _harness_fingerprints,
    load_manifest,
)


def _trial(case: dict, engine: str, timeout: float) -> dict:
    """Trusted worker: build exact identical full global circuits for both engines."""
    from symq import Budget
    from symq.labs.classical_transcript import Program, digest

    preparation_started = time.perf_counter()
    (n, method_a, method_b, mutant, reference, replacement,
     _prefix, _suffix, left, right) = _arithmetic_pair(case["scenario"])
    left_sha, right_sha = digest(Program.freeze(left)), digest(Program.freeze(right))
    preparation_wall = time.perf_counter() - preparation_started

    # Import costs are tracked but not charged to one verifier public call:
    # otherwise QCEC's heavy module startup biases an end-to-end comparison.
    import_started, import_cpu = time.perf_counter(), time.process_time()
    if engine == "sat":
        from symq.sat import check_sat_equivalence
    elif engine == "qcec":
        from symq.external.qcec import qcec_check
    else:
        raise ValueError("only explicit sat and qcec full-function baselines are supported")
    import_wall = time.perf_counter() - import_started
    import_cpu = time.process_time() - import_cpu

    started, cpu_started = time.perf_counter(), time.process_time()
    if engine == "sat":
        verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=timeout))
        if verdict.outcome == "equivalent":
            outcome = "equivalent"
        elif verdict.outcome == "different" and verdict.witness_checked:
            outcome = "different"
        else:
            outcome = "inconclusive"
        detail = {"solver": verdict.solver, "solver_outcome": verdict.outcome,
                  "witness_checked": bool(verdict.witness_checked)}
    elif engine == "qcec":
        verdict = qcec_check(left, right, timeout=timeout)
        outcome = ("equivalent" if verdict.equivalent is True else
                   "different" if verdict.equivalent is False else "inconclusive")
        detail = {"qcec_verdict": verdict.verdict,
                  "qcec_check_seconds": verdict.check_seconds,
                  "qcec_preprocessing_seconds": verdict.preprocessing_seconds}
    wall, cpu = time.perf_counter()-started, time.process_time()-cpu_started
    return {"outcome": outcome, "reference_sha256": left_sha,
            "candidate_sha256": right_sha, "degree": n,
            "reference_method": method_a, "candidate_method": method_b,
            "mutant": mutant, "reference_gates": len(reference.gates),
            "candidate_gates": len(replacement.gates),
            "global_width": left.width,
            "preparation_wall_seconds": preparation_wall,
            "engine_import_wall_seconds": import_wall,
            "engine_import_cpu_seconds": import_cpu,
            "verification_wall_seconds": wall, "verification_cpu_seconds": cpu,
            "detail": detail}


def run_campaign(*, repetitions: int = 1, wall_seconds: float = 20.0) -> dict:
    from symq.experimental.execution import HardLimits, run_isolated

    from .substitution_worker import external_decision_trial

    manifest = load_manifest()
    cases = [c for c in manifest["cases"] if c["family"] == "arithmetic"]
    if len(cases) != 6:
        raise ValueError("the declared arithmetic baseline corpus must contain six cases")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be positive")
    limits = HardLimits(wall_seconds=wall_seconds, cpu_seconds=wall_seconds,
                        memory_bytes=2 * 1024**3)
    before, files_before = receipt(), _harness_fingerprints()
    rng = random.Random(20261102)
    trials = [(case, rep, engine) for case in cases for rep in range(repetitions)
              for engine in ("sat", "qcec")]
    rng.shuffle(trials)
    rows = []
    for case, rep, engine in trials:
        result = run_isolated(external_decision_trial, case, engine,
                              min(wall_seconds, 10.0), limits=limits)
        value = result.value if result.status == "completed" else None
        actual = value["outcome"] if value is not None else result.status
        expected = "equivalent" if case["expected"] == "proved" else "different"
        category = ("matched" if actual == expected else
                    "inconclusive" if actual in {"inconclusive", "unsupported"} else "mismatch")
        rows.append({
            "case_id": case["id"], "repetition": rep, "engine": engine,
            "expected": expected, "actual": actual, "qualification": category,
            "worker_status": result.status, "worker_reason": result.reason,
            "worker_exitcode": result.exitcode, "worker_wall_seconds": result.wall_seconds,
            "worker_cpu_seconds": result.cpu_seconds,
            "worker_peak_rss_bytes": result.peak_rss_bytes,
            "value": value,
        })
    # Each engine must have compared precisely the same circuit pair. A different
    # source/candidate stream cannot be counted as matched, even if labels agree.
    for case in cases:
        records = [r for r in rows if r["case_id"] == case["id"] and r["value"]]
        fingerprints = {
            (r["value"]["reference_sha256"], r["value"]["candidate_sha256"])
            for r in records
        }
        if len(fingerprints) > 1:
            raise RuntimeError("SAT/QCEC received nonidentical circuit pairs")
    after, files_after = receipt(), _harness_fingerprints()
    return {
        "schema_version": 1,
        "created_utc": datetime.now(UTC).isoformat(),
        "source_before": before, "source_after": after,
        "source_unchanged": before == after and files_before == files_after,
        "source_fingerprints_before": files_before, "source_fingerprints_after": files_after,
        "manifest_sha256": _digest(manifest), "repetitions": repetitions,
        "environment": machine(), "cases": len(cases), "rows": rows,
        "qualification_counts": dict(Counter(r["qualification"] for r in rows)),
        "budgets": {"worker_wall_seconds": wall_seconds,
                    "worker_cpu_seconds": wall_seconds,
                    "worker_memory_bytes": limits.memory_bytes},
        "notes": [
            "Only full reversible Boolean permutation/unitary equivalence is compared.",
            "SAT and QCEC timings cover only their public verification calls, including conversion.",
            "Circuit synthesis and engine imports are separately timed; first pilot included MQT import and is not a valid speed comparator.",
            "QCEC alternating checker is configured to disable probabilistic simulations.",
            "The circuits are distinct decompositions from one SymQ generator codebase.",
            "Every case has a separate exhaustive integer oracle in the main qualification matrix.",
            "Inconclusive and unsupported cells are counted, never classified as wrong proof.",
            "One repetition is a coverage smoke, not a performance comparison.",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repetitions", type=int, default=1)
    p.add_argument("--wall-seconds", type=float, default=20.0)
    args = p.parse_args()
    result = run_campaign(repetitions=args.repetitions, wall_seconds=args.wall_seconds)
    if not result["source_unchanged"]:
        raise SystemExit("source or harness changed during campaign")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    contents = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.write_text(contents, encoding="utf-8")
    sha = hashlib.sha256(contents.encode()).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        sha + "  " + args.output.name + "\n", encoding="utf-8"
    )
    mismatch = result["qualification_counts"].get("mismatch", 0)
    print(f"{len(result['rows'])} SAT/QCEC cells; {mismatch} mismatches")
    return 1 if mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
