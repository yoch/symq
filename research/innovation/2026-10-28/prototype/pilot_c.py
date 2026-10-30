"""Pilot C: before any GC, measure whether the nodes are dead at all.

Issue #56 asks for a decision between "dead nodes dominate" (build a collector) and "live nodes
dominate" (stop: the explosion is structural). This pilot answers that with instrumentation
only -- no GC, no rebuild, no change to the engine.

At each sampling point it records:

* ``nodes_created``: internal nodes in the unique table, what memory currently holds;
* ``reachable``: nodes reachable from the live roots (the ``width`` wire values), computed with
  the native DAG walk ``manager.size``;
* ``dead``: ``nodes_created - reachable``: an **upper bound** on what a collector could reclaim
  (shared nodes counted conservatively per root, so ``dead`` is if anything overestimated);
* ``cache_entries`` / ``cache_misses`` from ``cache_info()``, and peak RSS.

The roots are the outputs of one ``simulate`` call, which is exactly the set that must survive
across a verification step, so this is the population a real collector would see.
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

from symq import Circuit
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded


def reachable(algebra: NativeZDDAlgebra, roots) -> int:
    """Nodes reachable from ``roots``; ``size`` walks one DAG, so summing over roots is an
    over-count of shared nodes, hence a lower bound on the dead population."""
    return sum(algebra.manager.size(root) for root in roots)


def one(width: int, gates: int, seed: int, marks: int = 5) -> dict:
    rng = random.Random(seed)
    circuit = random_circuit(width, gates, rng)
    chunk = max(1, len(circuit.gates) // marks)
    budget = Budget(max_nodes=3_000_000, max_seconds=30.0)
    algebra = NativeZDDAlgebra(width, budget.start())
    samples = []
    for start in range(0, len(circuit.gates), chunk):
        part = Circuit(width, circuit.gates[start:start + chunk])
        roots = algebra.simulate(part)
        created = algebra.node_count
        live = reachable(algebra, roots)
        samples.append({
            "gates_done": min(start + chunk, len(circuit.gates)),
            "nodes_created": created,
            "reachable": live,
            "dead_upper_bound": created - live,
            "dead_fraction": (created - live) / created if created else 0.0,
            "cache": algebra.cache_info(),
            "rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        })
    return {"width": width, "gates": gates, "seed": seed, "samples": samples,
            "final_nodes": algebra.node_count,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main() -> int:
    rows = []
    for width, gates, seed in ((14, 200, 1), (16, 300, 2), (18, 400, 3)):
        started = time.perf_counter()
        try:
            row = one(width, gates, seed)
            row["seconds"] = time.perf_counter() - started
        except ResourceLimitExceeded as error:
            row = {"width": width, "gates": gates, "seed": seed, "status": "budget",
                   "detail": f"{error.resource} limit exceeded"}
        except MemoryError:
            row = {"width": width, "gates": gates, "seed": seed, "status": "memory"}
        rows.append(row)
        if "samples" in row:
            last = row["samples"][-1]
            print(f"w={width:2d} g={gates:4d}  nodes={last['nodes_created']:7d} "
                  f"reachable={last['reachable']:7d} dead<= {last['dead_upper_bound']:7d} "
                  f"({100 * last['dead_fraction']:5.1f}%)  "
                  f"misses={last['cache']['misses']:7d}")
        else:
            print(row)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "PILOT_C.json")
    out.write_text(json.dumps({"rows": rows}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
