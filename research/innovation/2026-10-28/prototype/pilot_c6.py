"""Pilot C6: the 14x200 rebuild case, sealed with an independent truth-table oracle.

The audit's remaining objection to pilot C was traceability and verification:

* the 14x200 per-gate measurement that produced "38.1 s, 1.44 M peak nodes" was not in any tracked
  file;
* the difficult circuit was only cross-checked against a *different rebuild schedule*, not against
  an independent oracle, because the monolithic run exceeds the node budget;
* RSS was compared across arms in one process, where ``ru_maxrss`` is a running maximum and cannot
  attribute memory to an arm.

This script fixes all three. At 14 wires a truth table has 16 384 entries, so the circuit's action
can be computed exhaustively by concrete execution in a fraction of a second -- an oracle that
shares nothing with the symbolic machinery. Each arm is checked against it entry by entry, and each
arm runs in its **own subprocess** so ``ru_maxrss`` is that arm's peak.

Run: ``python pilot_c6.py`` writes ``RESULTS_C6.json`` next to this file.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

WIDTH = 14
GATES = 200
SEED = 7
BUDGET_NODES = 40_000_000


def truth_table(circuit) -> list[int]:
    """The circuit's permutation, by concrete execution on every input."""
    return [circuit.run(x) for x in range(1 << circuit.width)]


def arm(chunks: int, threshold: int) -> dict:
    """One strategy, run in this process (the caller isolates it)."""
    import resource

    sys.path.insert(0, str(HERE.parent))
    import continuous
    import pilot_c_corrected as base

    from symq.backends.zdd_native import NativeZDDAlgebra
    from symq.generators import random_circuit
    from symq.resources import Budget, ResourceLimitExceeded

    circuit = random_circuit(WIDTH, GATES, random.Random(SEED))
    expected = truth_table(circuit)
    budget = Budget(max_nodes=BUDGET_NODES, max_seconds=600.0)
    algebra = NativeZDDAlgebra(WIDTH, budget.start())
    parts = continuous.chunks(circuit, chunks)
    state = continuous.initial_state(algebra)
    peak_created = 0
    rebuilds = 0
    transfer_seconds = 0.0
    started = time.perf_counter()
    try:
        for index, fragment in enumerate(parts):
            state = continuous.apply_fragment(algebra, state, fragment)
            peak_created = max(peak_created, algebra.node_count)
            if parts[index + 1:] and algebra.node_count >= threshold:
                mark = time.perf_counter()
                algebra, moved = base.transfer_by_terms(algebra, state, budget)
                transfer_seconds += time.perf_counter() - mark
                rebuilds += 1
                state = tuple(moved)
    except (ResourceLimitExceeded, MemoryError) as error:
        return {"chunks": chunks, "threshold": threshold,
                "status": "budget" if isinstance(error, ResourceLimitExceeded) else "memory",
                "detail": str(error), "peak_created": peak_created, "rebuilds": rebuilds,
                "seconds": time.perf_counter() - started,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}

    # Verify the symbolic result against the truth table, wire by wire, on every input.
    outputs = [algebra.to_anf(value) for value in state]
    mismatches = 0
    for x in range(1 << WIDTH):
        symbolic = 0
        for wire, polynomial in enumerate(outputs):
            symbolic |= polynomial.evaluate(x) << wire
        if symbolic != expected[x]:
            mismatches += 1
    return {"chunks": chunks, "threshold": threshold, "status": "ok",
            "seconds": time.perf_counter() - started,
            "peak_created": peak_created, "final_created": algebra.node_count,
            "rebuilds": rebuilds, "transfer_seconds": transfer_seconds,
            "truth_table_mismatches": mismatches, "truth_table_size": 1 << WIDTH,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--arm":
        chunks, threshold = int(sys.argv[2]), int(sys.argv[3])
        payload = arm(chunks, threshold)
        print(json.dumps(payload))
        return 0

    arms = [(1, BUDGET_NODES), (8, 1_000_000), (200, 1_000_000), (200, 400_000)]
    rows = []
    for chunks, threshold in arms:
        result = subprocess.run(
            [sys.executable, str(HERE), "--arm", str(chunks), str(threshold)],
            capture_output=True, text=True, check=False)
        line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "{}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = {"chunks": chunks, "threshold": threshold, "status": "crash",
                   "stderr": result.stderr[-400:]}
        rows.append(row)
        print(f"chunks={chunks:3d} thr={threshold:8d} {row.get('status'):6s} "
              f"peak={row.get('peak_created', 0):9d} "
              f"rss={row.get('peak_rss_kib', 0) // 1024:6d} MiB "
              f"{row.get('seconds', 0):7.2f}s rebuilds={row.get('rebuilds', 0):3d} "
              f"mismatches={row.get('truth_table_mismatches')}", flush=True)
    payload = {"width": WIDTH, "gates": GATES, "seed": SEED, "budget_nodes": BUDGET_NODES,
               "oracle": "concrete truth table of 2**14 entries, computed in-process",
               "isolation": "one subprocess per arm, so ru_maxrss is that arm's peak",
               "rows": rows}
    (HERE.parent.parent / "RESULTS_C6.json").write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
