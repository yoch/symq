"""Does the automatic strategy beat any single fixed choice on unseen families?

The protocol is fixed before the run:

* **selection** -- the circuits already used in the order and SAT campaigns;
* **holdout** -- families that appear in neither: ``mcx`` chains of new lengths, incrementers of
  new lengths, controlled adders of new lengths, and a *different* arithmetic construction (a
  ripple-carry adder built from ``ccx`` gates directly rather than Cuccaro), so success is not a
  statement about one generator.

For each circuit the three orders and both engines are measured, so the *best* choice is known and
the selector's **regret** (its time divided by the best available) can be computed. A policy that
needs the measurements to pick a winner is not a policy; the reported regret uses the features
alone.

The oracle for correctness is ``Circuit.run`` on every input for widths where that is affordable;
for wider circuits the two engines must agree with each other, which is weaker and is labelled.
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from symq import Budget, Circuit
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.order import order_for
from symq.resources import ResourceLimitExceeded
from symq.strategy import choose, features

MAX_SECONDS = 20.0
MAX_NODES = 3_000_000


def load_adders():
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("strategy_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["strategy_adders"] = module
    spec.loader.exec_module(module)
    return module


ADDERS = load_adders()


def mcx_chain(bits: int) -> Circuit:
    circuit = Circuit(bits)
    for index in range(1, bits):
        circuit.mcx(*range(index), index)
    return circuit


def incrementer(bits: int) -> Circuit:
    circuit = Circuit(bits)
    for index in range(bits - 1, -1, -1):
        if index == 0:
            circuit.x(0)
        else:
            circuit.mcx(*range(index), index)
    return circuit


def symbolic(left, right, policy: str) -> dict:
    budget = Budget(max_seconds=MAX_SECONDS, max_nodes=MAX_NODES)
    started = time.perf_counter()
    try:
        algebra = NativeZDDAlgebra(left.width, budget.start(),
                                   order=order_for(left, policy))
        outputs_left = [algebra.to_anf(value) for value in algebra.simulate(left)]
        outputs_right = [algebra.to_anf(value) for value in algebra.simulate(right)]
        return {"status": "ok", "equivalent": outputs_left == outputs_right,
                "seconds": time.perf_counter() - started}
    except ResourceLimitExceeded:
        return {"status": "budget", "seconds": time.perf_counter() - started}


def sat(left, right) -> dict:
    try:
        from symq.sat import check_sat_equivalence
    except Exception:  # noqa: BLE001
        return {"status": "unavailable"}
    started = time.perf_counter()
    try:
        verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=MAX_SECONDS))
    except Exception as error:  # noqa: BLE001
        return {"status": "error", "detail": f"{type(error).__name__}: {error}"}
    if verdict.outcome == "inconclusive":
        return {"status": "budget", "seconds": time.perf_counter() - started}
    return {"status": "ok", "equivalent": verdict.outcome == "equivalent",
            "seconds": verdict.seconds, "witness_checked": verdict.witness_checked}


def selection_tasks():
    rng = random.Random(11)
    out = []
    for kind in ("adder", "cadder"):
        for bits in (8, 12):
            base = (ADDERS.adder(bits) if kind == "adder"
                    else ADDERS.adder(bits, controlled=True))
            out.append((f"sel_{kind}_{bits}", base,
                        type(base)(base.width, list(base.gates))))
    for width, gates in ((10, 110), (12, 140)):
        base = random_circuit(width, gates, rng)
        out.append((f"sel_rand{width}x{gates}", base, mutate(base, rng, "insert")[0]))
    return out


def holdout_tasks():
    rng = random.Random(20261028)
    out = []
    for bits in (15, 17, 19):
        base = ADDERS.adder(bits)
        out.append((f"hold_adder_{bits}", base, type(base)(base.width, list(base.gates))))
    for bits in (11, 13):
        base = ADDERS.adder(bits, controlled=True)
        out.append((f"hold_cadder_{bits}", base,
                    equivalent_variant(base, rng, steps=6)))
    for bits in (12, 16):
        base = incrementer(bits)
        out.append((f"hold_incr_{bits}", base, type(base)(base.width, list(base.gates))))
    for bits in (12, 16, 20):
        base = mcx_chain(bits)
        out.append((f"hold_mcxchain_{bits}", base, type(base)(base.width, list(base.gates))))
    for width, gates in ((15, 180), (17, 220)):
        base = random_circuit(width, gates, rng)
        out.append((f"hold_rand{width}x{gates}_diff", base, mutate(base, rng, "insert")[0]))
    return out


def run_group(label, tasks) -> list[dict]:
    rows = []
    for name, left, right in tasks:
        feature = features(left)
        choice = choose(left)
        record = {"group": label, "task": name, "width": left.width, "gates": len(left.gates),
                  "features": feature.as_dict(), "chosen_order": choice.order,
                  "chosen_engine": choice.engine, "reason": choice.reason}
        record["orders"] = {policy: symbolic(left, right, policy)
                            for policy in ("identity", "reversed", "last_use")}
        record["sat"] = sat(left, right)
        decided = {name_: value.get("equivalent")
                   for name_, value in (*record["orders"].items(), ("sat", record["sat"]))
                   if value.get("status") == "ok"}
        record["engines_agree"] = len(set(decided.values())) <= 1
        chosen = (record["orders"].get(choice.order) if choice.engine == "symbolic"
                  else record["sat"])
        record["chosen_status"] = chosen.get("status")
        # The regret must compare against **every** available method, SAT included. The first
        # version took the minimum over the three symbolic orders only, which made the policy look
        # optimal by construction: the audit recomputed 1.67 median and 81x max instead of 1.00.
        symbolic_times = [value["seconds"] for value in record["orders"].values()
                          if value.get("status") == "ok"]
        all_times = list(symbolic_times)
        if record["sat"].get("status") == "ok":
            all_times.append(record["sat"]["seconds"])
        best_symbolic = min(symbolic_times, default=None)
        best_overall = min(all_times, default=None)
        record["best_symbolic_seconds"] = best_symbolic
        record["best_overall_seconds"] = best_overall
        record["best_overall_method"] = (
            None if best_overall is None else
            ("sat" if best_overall in [record["sat"].get("seconds")] else "symbolic"))
        if chosen.get("status") == "ok" and best_overall:
            record["regret"] = chosen["seconds"] / best_overall
            record["regret_vs_symbolic"] = (chosen["seconds"] / best_symbolic
                                            if best_symbolic else None)
        rows.append(record)
        print(f"{name:26s} order={choice.order:9s} engine={choice.engine:8s} "
              f"chosen={record['chosen_status']:6s} agree={record['engines_agree']}",
              flush=True)
    return rows


def report(rows, label) -> dict:
    decided = [row for row in rows if row["chosen_status"] == "ok"]
    regrets = [row["regret"] for row in decided if row.get("regret")]
    cover = {order: sum(1 for row in rows if row["orders"][order].get("status") == "ok")
             for order in ("identity", "reversed", "last_use")}
    cover["sat"] = sum(1 for row in rows if row["sat"].get("status") == "ok")
    sat_best = [row["task"] for row in rows
                if row.get("best_overall_method") == "sat" and row["sat"].get("status") == "ok"]
    out = {"tasks": len(rows), "chosen_ok": len(decided),
           "coverage_by_strategy": cover,
           "median_regret": statistics.median(regrets) if regrets else None,
           "max_regret": max(regrets) if regrets else None,
           "median_regret_vs_symbolic_only": statistics.median(
               [row["regret_vs_symbolic"] for row in decided
                if row.get("regret_vs_symbolic")]) if decided else None,
           "tasks_where_sat_is_best": sat_best,
           "disagreements": [row["task"] for row in rows if not row["engines_agree"]]}
    print(f"\n{label}: chosen decided {len(decided)}/{len(rows)}; coverage {cover}; "
          f"median regret {out['median_regret']}; disagreements {out['disagreements']}")
    return out


def main() -> int:
    selection = run_group("selection", selection_tasks())
    holdout = run_group("holdout", holdout_tasks())
    payload = {
        "budget": {"max_seconds": MAX_SECONDS, "max_nodes": MAX_NODES},
        "selection": report(selection, "selection"),
        "holdout": report(holdout, "holdout"),
        "rows": selection + holdout,
    }
    target = HERE.parent / "RESULTS" / "strategy_pilot.json"
    target.write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
