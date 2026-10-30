"""Pilot C5: peak memory as a function of rebuild frequency.

Pilot C4 established two facts:

* the live set is tiny (147-1 378 nodes) while the created set explodes (millions);
* transferring the live roots into a fresh manager costs only 14 000-27 000 nodes.

Yet the peak *created* count stayed at 11.2 M because the threshold was only checked at chunk
boundaries: with eight fragments, each fragment creates ~2.5 M nodes before anything can happen.

So the question is not "does a collector help" but "how often must it run". This pilot measures
peak created nodes against the number of fragments, with a transfer at every boundary where the
table exceeds a threshold. The answer is the rebuild frequency a production collector needs.
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
sys.path.insert(0, str(HERE.parent))

import continuous
import pilot_c_corrected as base

from symq.anf import ANF
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded


def outputs(algebra: NativeZDDAlgebra, roots) -> tuple[ANF, ...]:
    return tuple(algebra.to_anf(value) for value in roots)


def run(circuit, chunks: int, threshold: int, budget_nodes: int) -> dict:
    budget = Budget(max_nodes=budget_nodes, max_seconds=180.0)
    algebra = NativeZDDAlgebra(circuit.width, budget.start())
    parts = continuous.chunks(circuit, chunks)
    state = continuous.initial_state(algebra)
    peak_created = 0
    transfer_seconds = 0.0
    rebuilds = 0
    started = time.perf_counter()
    try:
        for index, fragment in enumerate(parts):
            state = continuous.apply_fragment(algebra, state, fragment)
            peak_created = max(peak_created, algebra.node_count)
            if not parts[index + 1:] or algebra.node_count < threshold:
                continue
            mark = time.perf_counter()
            algebra, moved = base.transfer_by_terms(algebra, state, budget)
            transfer_seconds += time.perf_counter() - mark
            rebuilds += 1
            state = tuple(moved)
    except (ResourceLimitExceeded, MemoryError) as error:
        return {"status": "budget" if isinstance(error, ResourceLimitExceeded) else "memory",
                "detail": str(error), "seconds": time.perf_counter() - started,
                "peak_created": peak_created, "rebuilds": rebuilds}
    return {"status": "ok", "seconds": time.perf_counter() - started,
            "chunks": chunks, "chunk_size": len(circuit.gates) / max(len(parts), 1),
            "peak_created": peak_created, "rebuilds": rebuilds,
            "transfer_seconds": transfer_seconds,
            "outputs": outputs(algebra, state)}


def main() -> int:
    width, gates, seed = 13, 170, 7
    rng = random.Random(seed)
    circuit = random_circuit(width, gates, rng)
    budget_nodes = 30_000_000
    rows = []
    reference = None
    for chunks in (1, 2, 4, 8, 16, 32, 64, 170):
        row = run(circuit, chunks, threshold=400_000, budget_nodes=budget_nodes)
        if "outputs" in row:
            if reference is None:
                reference = row["outputs"]
                row["corresponds_to_baseline"] = True
            else:
                row["corresponds_to_baseline"] = row["outputs"] == reference
            row.pop("outputs")
        rows.append({"chunks": chunks, **row})
        print(f"chunks={chunks:4d}  peak_created={row.get('peak_created', 0):9d}  "
              f"rebuilds={row.get('rebuilds', 0):4d}  {row['seconds']:6.2f}s  "
              f"transfer={row.get('transfer_seconds', 0):5.2f}s  {row['status']}  "
              f"eq={row.get('corresponds_to_baseline')}", flush=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "RESULTS_C5.json")
    out.write_text(json.dumps({"width": width, "gates": gates, "threshold": 400_000,
                               "rows": rows}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
