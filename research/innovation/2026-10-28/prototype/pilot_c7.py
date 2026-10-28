"""Pilot C7: does the rebuild gain hold on more than one circuit and one seed?

The audit's remaining reservations about pilot C were: a single generated circuit, a single seed,
and a wall-clock figure that mixed computation with verification. C6 fixed the timing (compute,
rebuild, export and oracle are now separate) and this script fixes the sampling: four circuits
across two widths and two seeds, each arm in its own subprocess, each verified against a truth
table.

The comparison that matters is against the schedule that *completes* -- the eight-fragment rebuild
-- because the monolithic run does not finish at this size.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

CASES = [(13, 170, 7), (13, 170, 21), (14, 200, 7), (14, 200, 21)]
BUDGET_NODES = 40_000_000


def arm(width: int, gates: int, seed: int, chunks: int, threshold: int) -> dict:
    import random
    import resource
    import time

    sys.path.insert(0, str(HERE.parent))
    import continuous
    import pilot_c_corrected as base

    from symq.backends.zdd_native import NativeZDDAlgebra
    from symq.generators import random_circuit
    from symq.resources import Budget, ResourceLimitExceeded

    circuit = random_circuit(width, gates, random.Random(seed))
    expected = [circuit.run(x) for x in range(1 << width)]
    budget = Budget(max_nodes=BUDGET_NODES, max_seconds=900.0)
    algebra = NativeZDDAlgebra(width, budget.start())
    parts = continuous.chunks(circuit, chunks)
    state = continuous.initial_state(algebra)
    peak_created = 0
    rebuilds = 0
    rebuild_seconds = 0.0
    started = time.perf_counter()
    try:
        for index, fragment in enumerate(parts):
            state = continuous.apply_fragment(algebra, state, fragment)
            peak_created = max(peak_created, algebra.node_count)
            if parts[index + 1:] and algebra.node_count >= threshold:
                mark = time.perf_counter()
                algebra, moved = base.transfer_by_terms(algebra, state, budget)
                rebuild_seconds += time.perf_counter() - mark
                rebuilds += 1
                state = tuple(moved)
    except (ResourceLimitExceeded, MemoryError) as error:
        return {"width": width, "gates": gates, "seed": seed, "chunks": chunks,
                "threshold": threshold,
                "status": "budget" if isinstance(error, ResourceLimitExceeded) else "memory",
                "detail": str(error), "peak_created": peak_created, "rebuilds": rebuilds,
                "compute_seconds": time.perf_counter() - started,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    compute_seconds = time.perf_counter() - started
    outputs = [algebra.to_anf(value) for value in state]
    mismatches = 0
    for x in range(1 << width):
        symbolic = 0
        for wire, polynomial in enumerate(outputs):
            symbolic |= polynomial.evaluate(x) << wire
        if symbolic != expected[x]:
            mismatches += 1
    return {"width": width, "gates": gates, "seed": seed, "chunks": chunks,
            "threshold": threshold, "status": "ok", "compute_seconds": compute_seconds,
            "rebuild_seconds": rebuild_seconds, "peak_created": peak_created,
            "rebuilds": rebuilds, "truth_table_mismatches": mismatches,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--arm":
        width, gates, seed, chunks, threshold = (int(value) for value in sys.argv[2:7])
        print(json.dumps(arm(width, gates, seed, chunks, threshold)))
        return 0

    rows = []
    for width, gates, seed in CASES:
        for chunks, threshold in ((8, 1_000_000), (200, 400_000)):
            result = subprocess.run(
                [sys.executable, str(HERE), "--arm", str(width), str(gates), str(seed),
                 str(chunks), str(threshold)],
                capture_output=True, text=True, check=False)
            line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "{}"
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                row = {"width": width, "gates": gates, "seed": seed, "chunks": chunks,
                       "threshold": threshold, "status": "crash",
                       "stderr": result.stderr[-300:]}
            rows.append(row)
            print(f"{width}x{gates} seed={seed} chunks={chunks:3d} {row.get('status'):6s} "
                  f"compute={row.get('compute_seconds', 0):7.2f}s "
                  f"rss={row.get('peak_rss_kib', 0) // 1024:5d} MiB "
                  f"peak={row.get('peak_created', 0):9d} "
                  f"rebuilds={row.get('rebuilds', 0):3d} "
                  f"mismatches={row.get('truth_table_mismatches')}", flush=True)

    print("\nper circuit, per-gate against the eight-fragment schedule:")
    summary = []
    for width, gates, seed in CASES:
        pair = {row["chunks"]: row for row in rows
                if row["width"] == width and row["gates"] == gates and row["seed"] == seed}
        coarse, fine = pair.get(8), pair.get(200)
        if not coarse or not fine:
            continue
        if coarse.get("status") != "ok" or fine.get("status") != "ok":
            print(f"  {width}x{gates} seed={seed}: not comparable "
                  f"({coarse.get('status')}/{fine.get('status')})")
            continue
        entry = {"width": width, "gates": gates, "seed": seed,
                 "compute_ratio": fine["compute_seconds"] / coarse["compute_seconds"],
                 "rss_ratio": fine["peak_rss_kib"] / coarse["peak_rss_kib"],
                 "nodes_ratio": fine["peak_created"] / coarse["peak_created"]}
        summary.append(entry)
        print(f"  {width}x{gates} seed={seed}: compute x{entry['compute_ratio']:.2f}, "
              f"rss x{entry['rss_ratio']:.2f}, nodes x{entry['nodes_ratio']:.2f}")
    payload = {"budget_nodes": BUDGET_NODES, "rows": rows, "summary": summary,
               "oracle": "concrete truth table, computed in-process, one subprocess per arm"}
    (HERE.parent.parent / "RESULTS_C7.json").write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
