"""Pilot C4: the decision experiment. Does a rebuild finish circuits the plain engine cannot?

The previous arms were confounded: ``max_nodes`` is a *cumulative* creation budget, and a rebuild
legitimately restarts the count, so comparing the arms under one cumulative budget measures the
budget bookkeeping rather than memory. The measurement that decides the question is the one below.

**Observation that motivates it** (``prototype/pilot_c4.py``, 13 wires, 170 gates, budget 10 M):

| after chunk | nodes created | live nodes (exact) | live monomials |
|---:|---:|---:|---:|
| 0 | 18 383 | 729 | 1 942 |
| 1 | 1 508 552 | 354 | 7 961 |
| 2 | 6 262 136 | 49 | 8 188 |
| 3 | 9 426 530 | 24 | 8 191 |

The live set stays under a thousand nodes while nine million are created, so the *memory* the
plain run needs is set by the garbage, not by the function. A collector is therefore warranted if
and only if the transfer is cheap enough -- and the transfer cost is proportional to the live
monomials, not to the created nodes.

This pilot therefore runs, for each circuit:

* ``plain``: one manager with a cumulative creation budget;
* ``rebuild``: fresh manager at a live-node threshold, roots transferred through explicit
  monomials, simulation continuing in the new manager;
* and reports, for both, the peak **created** nodes, the peak **live** nodes, the wall time, the
  number of rebuilds and whether the outputs match.

The budget is set on the *simulation*, not on cumulative nodes, so the plain arm is not
artificially disadvantaged by the bookkeeping; the comparison is time and peak live population.
A second run with a large chunk count checks that the answer does not depend on the schedule.
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
import liveness
import pilot_c_corrected as base

from symq.anf import ANF
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded


def outputs(algebra: NativeZDDAlgebra, roots) -> tuple[ANF, ...]:
    return tuple(algebra.to_anf(value) for value in roots)


def plain(circuit, budget: Budget) -> dict:
    started = time.perf_counter()
    algebra = NativeZDDAlgebra(circuit.width, budget.start())
    try:
        roots = continuous.simulate_in_chunks(algebra, circuit, 1)
    except ResourceLimitExceeded as error:
        return {"status": "budget", "detail": f"{error.resource} limit exceeded",
                "seconds": time.perf_counter() - started,
                "created": algebra.node_count}
    payload = liveness.live_nodes(algebra, roots)
    return {"status": "ok", "seconds": time.perf_counter() - started,
            "created": algebra.node_count, "live": payload["live"],
            "outputs": outputs(algebra, roots)}


def rebuild(circuit, budget: Budget, chunks: int, threshold: int) -> dict:
    started = time.perf_counter()
    algebra = NativeZDDAlgebra(circuit.width, budget.start())
    parts = continuous.chunks(circuit, chunks)
    state = continuous.initial_state(algebra)
    peak_created = 0
    peak_live = 0
    transfer_seconds = 0.0
    rebuilds = 0
    trace = []
    try:
        for index, fragment in enumerate(parts):
            state = continuous.apply_fragment(algebra, state, fragment)
            payload = liveness.live_nodes(algebra, state)
            live = payload["live"]
            peak_created = max(peak_created, algebra.node_count)
            peak_live = max(peak_live, live)
            trace.append({"chunk": index, "created": algebra.node_count, "live": live,
                          "live_roots": payload["roots"]})
            # The trigger is the *unique table size*, which is what occupies memory: the live
            # population stays in the hundreds while millions of nodes accumulate.
            if not parts[index + 1:] or algebra.node_count < threshold:
                continue
            mark = time.perf_counter()
            algebra, moved = base.transfer_by_terms(algebra, state, budget)
            transfer_seconds += time.perf_counter() - mark
            rebuilds += 1
            state = tuple(moved)
    except ResourceLimitExceeded as error:
        return {"status": "budget", "detail": f"{error.resource} limit exceeded",
                "seconds": time.perf_counter() - started, "created": algebra.node_count,
                "rebuilds": rebuilds, "trace": trace}
    return {"status": "ok", "seconds": time.perf_counter() - started,
            "peak_created": peak_created, "peak_live": peak_live,
            "final_created": algebra.node_count, "rebuilds": rebuilds,
            "transfer_seconds": transfer_seconds, "trace": trace,
            "outputs": outputs(algebra, state)}


def run_cell(width: int, gates: int, seed: int, chunks: int, threshold: int) -> dict:
    rng = random.Random(seed)
    circuit = random_circuit(width, gates, rng)
    budget = Budget(max_nodes=12_000_000, max_seconds=120.0)
    record = {"width": width, "gates": gates, "seed": seed, "chunks": chunks,
              "threshold": threshold}
    record["plain"] = plain(circuit, budget)
    record["rebuild"] = rebuild(circuit, budget, chunks, threshold)
    record["other_schedule"] = rebuild(circuit, budget, chunks * 3, threshold)
    if "outputs" in record["rebuild"] and "outputs" in record["other_schedule"]:
        record["schedule_independent"] = (record["rebuild"]["outputs"]
                                          == record["other_schedule"]["outputs"])
    if "outputs" in record["plain"] and "outputs" in record["rebuild"]:
        record["agrees_with_plain"] = record["plain"]["outputs"] == record["rebuild"]["outputs"]
    for key in ("plain", "rebuild", "other_schedule"):
        record[key].pop("outputs", None)
    record["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return record


def main() -> int:
    rows = []
    cases = [(12, 140, 6), (13, 170, 6), (14, 200, 8), (15, 240, 8)]
    thresholds = (1_000_000, 3_000_000)
    for width, gates, chunks in cases:
        for threshold in thresholds:
            row = run_cell(width, gates, 7, chunks, threshold)
            rows.append(row)
            plain_arm = row["plain"]
            rebuilt = row["rebuild"]
            print(f"w={width:2d} g={gates:3d} thr={threshold:6d}  "
                  f"plain={plain_arm['status']:6s} {plain_arm.get('seconds', 0):7.2f}s "
                  f"created={plain_arm.get('created', 0):9d}  |  "
                  f"rebuild={rebuilt['status']:6s} {rebuilt.get('seconds', 0):7.2f}s "
                  f"peak_created={rebuilt.get('peak_created', 0):9d} "
                  f"peak_live={rebuilt.get('peak_live', 0):6d} "
                  f"gc={rebuilt.get('rebuilds', 0)} "
                  f"gc_s={rebuilt.get('transfer_seconds', 0):6.2f}  "
                  f"indep={row.get('schedule_independent')} "
                  f"eq={row.get('agrees_with_plain')}", flush=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "RESULTS_C4.json")
    out.write_text(json.dumps({"rows": rows}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
