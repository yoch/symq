"""Campaign 4: the order policy, re-run with the corrected adder and a real holdout.

Two defects invalidated the previous order campaigns, both found by the audit:

* ``adders.py`` did not compute addition, so 13 of the 19 circuits in campaign 3 were not
  adders. They are rebuilt here from the corrected generator, and the arithmetic is checked
  exhaustively by ``tests/test_adders.py`` before any order is compared;
* the function fingerprints hashed ``(count, sum of masks)``, which collides. They are SHA-256
  digests of the whole monomial sets now, so "no wrong function" means something.

Campaign 3 also selected ``reversed`` after seeing the results. This campaign therefore (a) reports
every heuristic on the corrected circuits, and (b) validates whatever wins on a **holdout** built
from sizes and topologies that no previous campaign used.
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))

import bench_order
import orders

from symq import simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.circuit import Circuit
from symq.generators import random_circuit
from symq.resources import Budget, ResourceLimitExceeded


def load_adders():
    path = HERE.parent / "adders.py"
    spec = importlib.util.spec_from_file_location("campaign_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["campaign_adders"] = module
    spec.loader.exec_module(module)
    return module


ADDERS = load_adders()
MAX_NODES = 3_000_000
MAX_SECONDS = 30.0


def one(circuit, name: str) -> dict:
    import time

    started = time.perf_counter()
    order = orders.order_of(circuit, name)
    selection = time.perf_counter() - started
    algebra = NativeZDDAlgebra(circuit.width,
                               Budget(max_nodes=MAX_NODES, max_seconds=MAX_SECONDS).start(),
                               order=order)
    started = time.perf_counter()
    try:
        roots = simulate(circuit, algebra)
        seconds = time.perf_counter() - started
        return {"order": name, "status": "ok", "selection_seconds": selection,
                "total_seconds": selection + seconds, "nodes": algebra.node_count,
                "fingerprint": bench_order.fingerprint(algebra, roots)}
    except ResourceLimitExceeded as error:
        return {"order": name, "status": "budget", "detail": f"{error.resource} limit exceeded",
                "selection_seconds": selection, "nodes": algebra.node_count}


def incrementer(bits: int) -> Circuit:
    circuit = Circuit(bits)
    for index in range(bits - 1, -1, -1):
        if index == 0:
            circuit.x(0)
        else:
            circuit.mcx(*range(index), index)
    return circuit


def mcx_chain(bits: int) -> Circuit:
    circuit = Circuit(bits)
    for index in range(1, bits):
        circuit.mcx(*range(index), index)
    return circuit


def selection_family():
    """Circuits used to see which heuristics are worth carrying forward."""
    cases = []
    for bits in (8, 12, 16):
        cases.append((f"adder_{bits}", ADDERS.adder(bits)))
        cases.append((f"cadder_{bits}", ADDERS.adder(bits, controlled=True)))
    rng = random.Random(11)
    for width, gates in ((10, 100), (12, 140)):
        cases.append((f"rand{width}x{gates}", random_circuit(width, gates, rng)))
    return cases


def holdout_family():
    """Sizes and topologies that no earlier campaign used, after the heuristics are frozen."""
    cases = []
    for bits in (9, 11, 13, 15, 17, 19):
        cases.append((f"holdout_adder_{bits}", ADDERS.adder(bits)))
    for bits in (9, 11, 13, 15):
        cases.append((f"holdout_cadder_{bits}", ADDERS.adder(bits, controlled=True)))
    for bits in (12, 16, 20):
        cases.append((f"holdout_incr_{bits}", incrementer(bits)))
        cases.append((f"holdout_mcxchain_{bits}", mcx_chain(bits)))
    return cases


def run_group(label: str, cases, heuristics) -> list[dict]:
    rows = []
    for name, circuit in cases:
        for heuristic in heuristics:
            rows.append({"group": label, "case": name, "width": circuit.width,
                         "gates": len(circuit.gates), **one(circuit, heuristic)})
        reference = next((r["fingerprint"] for r in rows
                          if r["case"] == name and r["order"] == "identity"
                          and r["status"] == "ok"), None)
        for row in rows:
            if row["case"] == name and row["status"] == "ok" and reference:
                row["matches_identity_function"] = row["fingerprint"] == reference
        print(f"{label}/{name}", {r["order"]: r["status"] for r in rows
                                  if r["case"] == name}, flush=True)
    return rows


def summarise(rows, group, heuristics):
    print(f"\n== {group}")
    out = {}
    for heuristic in heuristics:
        selected = [r for r in rows if r["group"] == group and r["order"] == heuristic]
        done = [r for r in selected if r["status"] == "ok"]
        ratios = []
        for row in done:
            base = next((r for r in rows if r["case"] == row["case"]
                         and r["order"] == "identity" and r["status"] == "ok"), None)
            if base and row["total_seconds"] > 0:
                ratios.append(row["total_seconds"] / base["total_seconds"])
        bad = sum(1 for row in done if row.get("matches_identity_function") is False)
        geomean = statistics.geometric_mean(ratios) if ratios else float("nan")
        out[heuristic] = {"completed": len(done), "of": len(selected), "geomean": geomean,
                          "wrong_function": bad}
        print(f"  {heuristic:<10} {len(done)}/{len(selected)} ok  geomean={geomean:8.3f}  "
              f"worse-than-1={sum(1 for r in ratios if r > 1.0)}/{len(ratios)}  "
              f"bad function={bad}")
    return out


def main() -> int:
    heuristics = tuple(orders.HEURISTICS)
    selection = run_group("selection", selection_family(), heuristics)
    selection_summary = summarise(selection, "selection", heuristics)
    best = min((h for h in heuristics if selection_summary[h]["completed"]),
               key=lambda h: selection_summary[h]["geomean"])
    print(f"\nfrozen policy after the selection runs: {best}")

    finalists = ("identity", best)
    holdout = run_group("holdout", holdout_family(), finalists)
    holdout_summary = summarise(holdout, "holdout", finalists)

    by_family: dict[str, list[float]] = {}
    for row in holdout:
        if row["order"] != best or row["status"] != "ok":
            continue
        base = next((r for r in holdout if r["case"] == row["case"]
                     and r["order"] == "identity" and r["status"] == "ok"), None)
        if base and row["total_seconds"] > 0:
            family = row["case"].split("_")[1]
            by_family.setdefault(family, []).append(row["total_seconds"]
                                                    / base["total_seconds"])
    print("\nby family on the holdout:")
    for family, ratios in sorted(by_family.items()):
        print(f"  {family:<10} n={len(ratios)} geomean={statistics.geometric_mean(ratios):6.3f}")

    payload = {"max_nodes": MAX_NODES, "max_seconds": MAX_SECONDS, "frozen_policy": best,
               "selection": selection_summary, "holdout": holdout_summary,
               "holdout_by_family": {k: statistics.geometric_mean(v)
                                     for k, v in by_family.items()},
               "rows": selection + holdout}
    (HERE.parent / "RESULTS_ORDER_CORRECTED.json").write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
