"""Campaign 2: is a structural order better than the identity on *larger* circuits, too?

Campaign 1 (`RESULTS_ORDER.json`) shows `reverse` at 0.546 geometric mean over identity on 17
small circuits, and every other heuristic worse than `reverse`. That is a promising signal, but
the circuits are small enough that the fixed cost dominates, so the ordering effect could be a
constant factor in the wrong place.

This campaign uses circuits big enough for the diagram to matter, on **two disjoint families**:

* *reserved* -- Cuccaro adders of 20-28 bits and controlled adders of 16-20 bits, not used in
  campaign 1;
* *stress* -- dense random circuits at 12-14 wires, which are the hardest thing the engine
  handles at all.

The decision rule, fixed before the run: adopt the heuristic only if it is at least 1.2x faster
than identity in geometric mean on the **reserved** family and never worse than 1.0x on more than
a quarter of its instances. A heuristic that wins only on the stress family does not generalise.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

import random

import adders
import bench_order
import orders

from symq import simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded

MAX_NODES = 3_000_000
MAX_SECONDS = 30.0
CANDIDATES = ("identity", "reverse", "degree", "last_use")


def one(circuit, name: str) -> dict:
    started = time.perf_counter()
    order = orders.order_of(circuit, name)
    selection = time.perf_counter() - started
    algebra = NativeZDDAlgebra(circuit.width, Budget(max_nodes=MAX_NODES,
                                                     max_seconds=MAX_SECONDS).start(),
                               order=order)
    started = time.perf_counter()
    try:
        roots = simulate(circuit, algebra)
        seconds = time.perf_counter() - started
        return {"order": name, "status": "ok", "total_seconds": selection + seconds,
                "selection_seconds": selection, "simulate_seconds": seconds,
                "nodes": algebra.node_count,
                "fingerprint": bench_order.fingerprint(algebra, roots)}
    except ResourceLimitExceeded as error:
        return {"order": name, "status": "budget", "detail": f"{error.resource} limit exceeded",
                "selection_seconds": selection, "nodes": algebra.node_count}


def families():
    reserved = []
    for bits in (20, 24, 28):
        reserved.append((f"reserved_adder_{bits}", adders.adder(bits)))
    for bits in (16, 20):
        reserved.append((f"reserved_cadder_{bits}", adders.adder(bits, controlled=True)))
    stress = []
    for width, gates, seed in ((12, 120, 3), (12, 140, 11), (13, 150, 5)):
        stress.append((f"stress_{width}x{gates}_{seed}",
                       random_circuit(width, gates, random.Random(seed))))
    return reserved, stress


def main() -> int:
    reserved, stress = families()
    rows = []
    for label, group in (("reserved", reserved), ("stress", stress)):
        for name, circuit in group:
            for heuristic in CANDIDATES:
                row = {"family": label, "case": name, "width": circuit.width,
                       "gates": len(circuit.gates), **one(circuit, heuristic)}
                rows.append(row)
            reference = next((r["fingerprint"] for r in rows
                              if r["case"] == name and r["order"] == "identity"
                              and r["status"] == "ok"), None)
            for row in rows:
                if row["case"] == name and row["status"] == "ok" and reference:
                    row["matches_identity_function"] = row["fingerprint"] == reference
            print(name, {r["order"]: r["status"] for r in rows if r["case"] == name}, flush=True)
    for family in ("reserved", "stress"):
        print(f"\n== {family}")
        for heuristic in CANDIDATES:
            selected = [r for r in rows if r["family"] == family and r["order"] == heuristic]
            done = [r for r in selected if r["status"] == "ok"]
            ratios = []
            for row in done:
                base = next((r for r in rows if r["case"] == row["case"]
                             and r["order"] == "identity" and r["status"] == "ok"), None)
                if base and row["total_seconds"] > 0:
                    ratios.append(row["total_seconds"] / base["total_seconds"])
            bad = sum(1 for row in done if row.get("matches_identity_function") is False)
            print(f"  {heuristic:<10} {len(done)}/{len(selected)} ok  "
                  f"geomean={statistics.geometric_mean(ratios) if ratios else float('nan'):6.3f}  "
                  f"worse-than-1={sum(1 for r in ratios if r > 1.0)}/{len(ratios)}  "
                  f"bad function={bad}")
    out = HERE.parent / "RESULTS_ORDER2.json"
    out.write_text(json.dumps({"max_nodes": MAX_NODES, "max_seconds": MAX_SECONDS,
                               "rows": rows}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
