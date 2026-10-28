"""Pilot C2: what would a rebuild cost, and what would it reclaim?

``pilot_c.py`` shows 99.6-99.8 % of the unique table is unreachable from the live roots, so the
memory is there to be reclaimed. Whether reclaiming it is worth anything is a different question:
a rebuild must re-create the live roots, and that work is charged to the verification.

The decisive ratio is measured here:

    rebuild_cost(k) / simulation_cost(k)

for ``k`` chunks of a dense circuit, where the rebuild is implemented the most expensive way
possible -- every live root is expanded to explicit monomials and re-imported into a fresh
manager. Any incremental or in-place collector can only be cheaper, so a ratio below 1 here is a
sufficient condition for a collector to be affordable; a ratio above 1 refutes it for this
workload.

What is *not* measured: the memory actually saved (that needs instrumentation inside the C
allocator), and the effect on a workload that would have died of memory exhaustion. Both are
named as limits in ``PILOT_C.md``.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))

from symq import Circuit
from symq.anf import ANF
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded


def rebuild_cost(algebra: NativeZDDAlgebra, roots) -> tuple[float, int]:
    """Cost of moving ``roots`` into a fresh manager, and the node count left behind."""
    started = time.perf_counter()
    fresh = NativeZDDAlgebra(algebra.width, Budget(max_nodes=3_000_000,
                                                   max_seconds=30.0).start())
    for root in roots:
        fresh.from_anf(ANF(frozenset(algebra.manager.anf(root))))
    return time.perf_counter() - started, fresh.node_count


def run(width: int, gates: int, seed: int, chunks: int) -> dict:
    rng = random.Random(seed)
    circuit = random_circuit(width, gates, rng)
    chunk = max(1, len(circuit.gates) // chunks)
    algebra = NativeZDDAlgebra(width, Budget(max_nodes=3_000_000, max_seconds=30.0).start())
    samples = []
    simulation = 0.0
    rebuilding = 0.0
    for start in range(0, len(circuit.gates), chunk):
        part = Circuit(width, circuit.gates[start:start + chunk])
        mark = time.perf_counter()
        roots = algebra.simulate(part)
        simulation += time.perf_counter() - mark
        cost, fresh_nodes = rebuild_cost(algebra, roots)
        rebuilding += cost
        samples.append({
            "gates_done": min(start + chunk, len(circuit.gates)),
            "nodes": algebra.node_count,
            "live_after_rebuild": fresh_nodes,
            "simulation_seconds": simulation,
            "rebuild_seconds": rebuilding,
            "ratio": rebuilding / simulation if simulation else None,
        })
    return {"width": width, "gates": gates, "seed": seed, "chunks": len(samples),
            "samples": samples, "simulation_seconds": simulation,
            "rebuild_seconds": rebuilding,
            "ratio": rebuilding / simulation if simulation else None}


def main() -> int:
    rows = []
    for width, gates in ((12, 150), (14, 200), (16, 300)):
        try:
            row = run(width, gates, 7, 5)
        except (ResourceLimitExceeded, MemoryError) as error:
            row = {"width": width, "gates": gates, "status": type(error).__name__}
        rows.append(row)
        if "ratio" in row:
            print(f"w={width:2d} g={gates:4d}  simulate={row['simulation_seconds']:7.3f}s  "
                  f"rebuild={row['rebuild_seconds']:7.3f}s  ratio={row['ratio']:6.2f}  "
                  f"nodes_at_end={row['samples'][-1]['nodes']}", flush=True)
        else:
            print(row, flush=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "PILOT_C2.json")
    out.write_text(json.dumps({"rows": rows}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
