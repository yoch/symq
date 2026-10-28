"""Pilot C3: does a rebuild actually save a circuit the plain engine cannot finish?

``pilot_c_corrected.py`` shows the rebuild caps peak nodes (879 255 against 2 189 160 at
12x140) and is *faster* than the plain run, because a smaller unique table keeps the hash probes
in cache. That is a good sign but not the decision criterion, which is:

    the collector must save circuits genuinely blocked by memory, or cut peak memory sharply at
    an acceptable cost.

So this pilot takes circuits where the plain run exceeds a node budget, and asks whether the
rebuild finishes the same circuit under the same budget. Three arms, same circuit, same budget:

* ``plain`` -- one manager, monolithic;
* ``rebuild`` -- continuous, rebuild at a fixed threshold;
* ``rebuild_adaptive`` -- continuous, threshold at half the budget so at most one rebuild is
  needed to stay under it.

Correctness is checked against the native monolithic run when that run fits the budget, and
otherwise against the *same circuit simulated by the rebuild with a much smaller chunk size*,
which exercises a different rebuild schedule: two different schedules agreeing monomial for
monomial is evidence the rebuild preserves the function, and the schedule independence is itself
tested in ``tests/test_pilot_c.py`` for the widths where the reference is affordable.
"""
from __future__ import annotations

import json
import random
import resource
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

import continuous
import pilot_c_corrected as base

from symq.anf import ANF
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded

BUDGET_NODES = 600_000


def outputs_of(algebra: NativeZDDAlgebra, roots) -> tuple[ANF, ...]:
    return tuple(algebra.to_anf(value) for value in roots)


def run(width: int, gates: int, seed: int, chunks: int, threshold: int) -> dict:
    rng = random.Random(seed)
    circuit = random_circuit(width, gates, rng)
    budget = Budget(max_nodes=BUDGET_NODES, max_seconds=30.0)
    record = {"width": width, "gates": gates, "budget_nodes": BUDGET_NODES,
              "threshold": threshold}

    # Arm 1: plain, monolithic.
    started = time.perf_counter()
    try:
        algebra = NativeZDDAlgebra(width, budget.start())
        roots = continuous.simulate_in_chunks(algebra, circuit, 1)
        record["plain"] = {"status": "ok", "seconds": time.perf_counter() - started,
                           "peak_nodes": algebra.node_count,
                           "outputs": outputs_of(algebra, roots)}
    except ResourceLimitExceeded as error:
        record["plain"] = {"status": "budget", "detail": f"{error.resource} limit exceeded"}

    # Arm 2: rebuild at a fixed threshold, then continue in the new manager.
    started = time.perf_counter()
    try:
        algebra = NativeZDDAlgebra(width, budget.start())
        parts = continuous.chunks(circuit, chunks)
        state = continuous.initial_state(algebra)
        peak = 0
        rebuilds = 0
        rebuild_seconds = 0.0
        for index, fragment in enumerate(parts):
            state = continuous.apply_fragment(algebra, state, fragment)
            peak = max(peak, algebra.node_count)
            if parts[index + 1:] and algebra.node_count >= threshold:
                mark = time.perf_counter()
                algebra, moved = base.transfer_by_terms(algebra, state, budget)
                rebuild_seconds += time.perf_counter() - mark
                rebuilds += 1
                state = tuple(moved)
        record["rebuild"] = {"status": "ok", "seconds": time.perf_counter() - started,
                             "peak_nodes": peak, "rebuilds": rebuilds,
                             "rebuild_seconds": rebuild_seconds,
                             "outputs": outputs_of(algebra, state)}
    except ResourceLimitExceeded as error:
        record["rebuild"] = {"status": "budget", "detail": f"{error.resource} limit exceeded"}

    # Arm 3: the same circuit with a much smaller chunk, i.e. a different rebuild schedule.
    started = time.perf_counter()
    try:
        algebra = NativeZDDAlgebra(width, budget.start())
        parts = continuous.chunks(circuit, max(chunks * 3, chunks + 1))
        state = continuous.initial_state(algebra)
        peak = 0
        rebuilds = 0
        for index, fragment in enumerate(parts):
            state = continuous.apply_fragment(algebra, state, fragment)
            peak = max(peak, algebra.node_count)
            if parts[index + 1:] and algebra.node_count >= threshold:
                algebra, moved = base.transfer_by_terms(algebra, state, budget)
                rebuilds += 1
                state = tuple(moved)
        record["rebuild_other_schedule"] = {
            "status": "ok", "seconds": time.perf_counter() - started,
            "peak_nodes": peak, "rebuilds": rebuilds, "outputs": outputs_of(algebra, state)}
    except ResourceLimitExceeded as error:
        record["rebuild_other_schedule"] = {"status": "budget",
                                            "detail": f"{error.resource} limit exceeded"}

    if record["rebuild"].get("status") == "ok":
        other = record["rebuild_other_schedule"]
        record["rebuild"]["agrees_with_other_schedule"] = (
            other.get("status") == "ok" and other["outputs"] == record["rebuild"]["outputs"])
        plain = record["plain"]
        record["rebuild"]["agrees_with_plain"] = (
            plain.get("status") == "ok" and plain["outputs"] == record["rebuild"]["outputs"])
    for key in ("plain", "rebuild", "rebuild_other_schedule"):
        record[key].pop("outputs", None)
    record["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return record


def main() -> int:
    rows = []
    for width, gates, chunks in ((13, 170, 6), (14, 200, 6), (14, 240, 8), (15, 260, 8)):
        for threshold in (BUDGET_NODES // 2, BUDGET_NODES * 3 // 4):
            row = run(width, gates, 7, chunks, threshold)
            rows.append(row)
            plain = row["plain"]
            rebuilt = row["rebuild"]
            print(f"w={width} g={gates} thr={threshold:6d}  plain={plain['status']:6s}  "
                  f"rebuild={rebuilt['status']:6s} peak={rebuilt.get('peak_nodes', 0):7d}  "
                  f"{rebuilt.get('seconds', 0):6.2f}s  gc={rebuilt.get('rebuilds', 0)}  "
                  f"agree={rebuilt.get('agrees_with_other_schedule')}", flush=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "RESULTS_C3.json")
    out.write_text(json.dumps({"budget_nodes": BUDGET_NODES, "rows": rows}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
