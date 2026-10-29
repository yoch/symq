"""Cache benchmark, corrected: construction and simulation timed separately.

The audit found that the first version started its timer *after* building the manager:

    a = NativeZDDAlgebra(..., cache_limit=limit)
    t = time.perf_counter()          # <- the constructor was already paid
    simulate(circuit, a)

so the measurement could not see the very cost the fix was about, and the claimed gain could come
from anywhere. It also reported the best of five runs, which hides variance.

This version measures four phases separately, for every arm:

* ``construct`` -- building the algebra, including any cache allocation;
* ``simulate``  -- the symbolic computation;
* ``total``     -- the two together;
* and, for the lossy arms, the cache capacity the manager actually reached.

It reports **median** and interquartile range over ``repeats`` runs, not the minimum, and it pins
the two implementations it compares by their git SHA so the numbers cannot be attributed to the
wrong code.
"""
from __future__ import annotations

import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))

from symq import simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.corpus import load_corpus
from symq.generators import random_circuit
from symq.resources import Budget

MAX_NODES = 80_000_000
MAX_SECONDS = 150.0


def one_run(circuit, limit, repeats: int) -> dict:
    construct, simulation, total, capacities = [], [], [], []
    for _ in range(repeats):
        started = time.perf_counter()
        algebra = NativeZDDAlgebra(circuit.width,
                                   Budget(max_nodes=MAX_NODES, max_seconds=MAX_SECONDS).start(),
                                   cache_limit=limit)
        built = time.perf_counter()
        simulate(circuit, algebra)
        finished = time.perf_counter()
        construct.append(built - started)
        simulation.append(finished - built)
        total.append(finished - started)
        capacities.append(algebra.cache_info()["capacity"])

    def summary(values):
        ordered = sorted(values)
        return {"median": statistics.median(ordered),
                "q1": ordered[len(ordered) // 4],
                "q3": ordered[(3 * len(ordered)) // 4],
                "min": ordered[0], "max": ordered[-1]}

    return {"construct": summary(construct), "simulate": summary(simulation),
            "total": summary(total), "cache_capacity": capacities[-1],
            "nodes": algebra.node_count}


def cases():
    out = []
    for entry in load_corpus(Path("benchmarks/corpus/qcec/MANIFEST.json")).entries:
        if not entry.supported:
            continue
        circuit = entry.load()
        if circuit.width <= 24 and len(circuit.gates) <= 400:
            out.append((entry.name, circuit, 9))
    for width, gates in ((10, 100), (11, 120), (12, 140)):
        out.append((f"rand{width}x{gates}", random_circuit(width, gates, random.Random(11)), 3))
    return out


def main() -> int:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=False).stdout.strip()
    rows = []
    for name, circuit, repeats in cases():
        row = {"case": name, "width": circuit.width, "gates": len(circuit.gates),
               "repeats": repeats}
        row["lossless"] = one_run(circuit, None, repeats)
        row["bounded"] = one_run(circuit, 1 << 20, repeats)
        row["simulate_ratio"] = (row["bounded"]["simulate"]["median"]
                                 / row["lossless"]["simulate"]["median"])
        row["total_ratio"] = (row["bounded"]["total"]["median"]
                              / row["lossless"]["total"]["median"])
        rows.append(row)
        print(f"{name:<16} construct {1e6 * row['lossless']['construct']['median']:6.1f} vs "
              f"{1e6 * row['bounded']['construct']['median']:6.1f} us | "
              f"simulate {1e3 * row['lossless']['simulate']['median']:8.3f} vs "
              f"{1e3 * row['bounded']['simulate']['median']:8.3f} ms | "
              f"total ratio {row['total_ratio']:.2f} | cap {row['bounded']['cache_capacity']}",
              flush=True)
    payload = {"head": head, "repeats_note": "per-case repeats, medians reported", "rows": rows}
    out = HERE.parent / "RESULTS_CACHE_SEPARATED.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    by_kind = {"structured": [], "dense": []}
    for row in rows:
        kind = "dense" if row["case"].startswith("rand") else "structured"
        by_kind[kind].append(row["total_ratio"])
    for kind, ratios in by_kind.items():
        if ratios:
            print(f"{kind}: geometric mean of total ratio bounded/lossless = "
                  f"{statistics.geometric_mean(ratios):.3f} (n={len(ratios)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
