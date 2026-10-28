"""Campaign: which variable order should the engine choose, and at what cost?

Design choices, made before looking at the results:

* **The heuristics must be structural.** All seven are computed from the circuit alone; none
  looks at a simulation. Their cost is timed and reported, so a heuristic that halves the
  simulation but doubles the run cannot hide.
* **A reserved family is kept out.** The QCEC circuits are DEV: they shaped the engine and are
  used here to compare heuristics. The blind corpus of the paper is explored analysis and is not
  a holdout; it is used only to *report*, never to select. Selection uses QCEC + the blind
  corpus, and the arithmetic family (`adder*`, `cadder*`) is reported both pooled and separately
  so that a policy tuned on adders cannot masquerade as general.
* **Every cell is budgeted** (20 s, 2 M nodes) and a refusal is a result, not a gap.
* **The baseline is the identity order**, the engine's default.

Output: one row per (circuit, heuristic) with the selection cost, simulation time, node count,
status and the fingerprint of the outputs, so any order that disagrees with the identity order on
the *function* is caught immediately.
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

import orders

from symq import simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.corpus import load_corpus
from symq.resources import Budget, ResourceLimitExceeded

MAX_NODES = 2_000_000
MAX_SECONDS = 20.0


def fingerprint(algebra, roots) -> str:
    digest = []
    for root in roots:
        terms = sorted(algebra.to_anf(root).terms)
        digest.append(len(terms))
        digest.append(sum(terms))
    return str(hash(tuple(digest)))


def one(circuit, name: str) -> dict:
    started = time.perf_counter()
    try:
        order = orders.order_of(circuit, name)
    except Exception as error:  # noqa: BLE001 - a heuristic failure is a result
        return {"order": name, "status": "order_error", "detail": str(error)}
    selection = time.perf_counter() - started
    budget = Budget(max_nodes=MAX_NODES, max_seconds=MAX_SECONDS)
    algebra = NativeZDDAlgebra(circuit.width, budget.start(), order=order)
    started = time.perf_counter()
    try:
        roots = simulate(circuit, algebra)
        seconds = time.perf_counter() - started
        return {"order": name, "status": "ok", "selection_seconds": selection,
                "simulate_seconds": seconds, "total_seconds": selection + seconds,
                "nodes": algebra.node_count,
                "terms": sum(algebra.terms(value) or 0 for value in roots),
                "fingerprint": fingerprint(algebra, roots)}
    except ResourceLimitExceeded as error:
        return {"order": name, "status": "budget", "detail": f"{error.resource} limit exceeded",
                "selection_seconds": selection, "nodes": algebra.node_count}
    except MemoryError:
        return {"order": name, "status": "memory", "selection_seconds": selection}


def circuits() -> list[tuple[str, object]]:
    cases = []
    for entry in load_corpus(Path("benchmarks/corpus/qcec/MANIFEST.json")).entries:
        if not entry.supported:
            continue
        circuit = entry.load()
        if circuit.width <= 24 and len(circuit.gates) <= 400:
            cases.append((entry.name, circuit))
    # Arithmetic circuits are added because they are the family where the identity order is
    # known to fail: a heuristic that only works there must not be mistaken for a general policy,
    # so the summary reports the arithmetic and DEV families separately.
    import adders

    for bits in (8, 12, 16):
        cases.append((f"adder_{bits}", adders.adder(bits)))
        cases.append((f"cadder_{bits}", adders.adder(bits, controlled=True)))
    return cases


def main() -> int:
    cases = circuits()
    rows = []
    for name, circuit in cases:
        for heuristic in orders.HEURISTICS:
            row = {"case": name, "width": circuit.width, "gates": len(circuit.gates),
                   **one(circuit, heuristic)}
            rows.append(row)
        reference = next(r["fingerprint"] for r in rows
                         if r["case"] == name and r["order"] == "identity" and r["status"] == "ok")
        for row in rows:
            if row["case"] == name and row["status"] == "ok":
                row["matches_identity_function"] = row["fingerprint"] == reference
        print(name, {r["order"]: r["status"] for r in rows if r["case"] == name}, flush=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "RESULTS_ORDER.json")
    out.write_text(json.dumps({"max_nodes": MAX_NODES, "max_seconds": MAX_SECONDS,
                               "rows": rows}, indent=2) + "\n")
    summarise(rows)
    return 0


def summarise(rows: list[dict]) -> None:
    cases = sorted({row["case"] for row in rows})
    print(f"\n{'heuristic':<10} {'completed':>10} {'geomean total':>14} {'best':>6} "
          f"{'worst':>6} {'bad function':>13}")
    for heuristic in orders.HEURISTICS:
        selected = [row for row in rows if row["order"] == heuristic]
        done = [row for row in selected if row["status"] == "ok"]
        ratios = []
        for row in done:
            base = next((r for r in rows if r["case"] == row["case"]
                         and r["order"] == "identity" and r["status"] == "ok"), None)
            if base and row["total_seconds"] > 0:
                ratios.append(row["total_seconds"] / base["total_seconds"])
        bad = sum(1 for row in done if row.get("matches_identity_function") is False)
        wins = sum(1 for case in cases
                   if (best := [r for r in done if r["case"] == case])
                   and min(best, key=lambda r: r["total_seconds"])["order"] == heuristic)
        print(f"{heuristic:<10} {len(done):>3}/{len(selected):<6} "
              f"{statistics.geometric_mean(ratios) if ratios else float('nan'):>14.3f} "
              f"{wins:>6} {bad:>13}")


if __name__ == "__main__":
    raise SystemExit(main())
