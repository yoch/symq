"""Pilot SAT: does the decision engine cover circuits the symbolic engine cannot?

The question is not "is SAT faster". It is: under a **fixed budget**, how many equivalence tasks
can each engine decide, and on which families? Three engines, the same tasks, the same limits:

``zdd``
    symbolic simulation of both circuits and wire-by-wire comparison (``check_equivalence``),
    with the native backend and its default settings;
``zdd_gc``
    the same with ``collect_every`` enabled, since the collector is the memory arm;
``sat``
    the Tseitin miter, which never materialises a polynomial.

Every SAT witness is replayed by the engine itself before it is counted, so a ``different`` verdict
cannot be a false positive. Every symbolic verdict is exact by construction. The comparison counts
**tasks decided**, then time on the tasks both engines decided, which is the only paired quantity
that is not selection-biased.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from symq import Budget, Circuit, check_equivalence
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.resources import ResourceLimitExceeded

MAX_SECONDS = 30.0
MAX_NODES = 4_000_000


def load_adders():
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("pilot_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pilot_adders"] = module
    spec.loader.exec_module(module)
    return module


ADDERS = load_adders()


def symbolic(left, right, *, collect: int | None) -> dict:
    budget = Budget(max_seconds=MAX_SECONDS, max_nodes=MAX_NODES)
    started = time.perf_counter()
    if collect is None:
        try:
            result = check_equivalence(left, right, backend="zdd-native", budget=budget)
            return {"status": "ok", "equivalent": result.equivalent,
                    "seconds": time.perf_counter() - started}
        except ResourceLimitExceeded as error:
            return {"status": "budget", "detail": str(error),
                    "seconds": time.perf_counter() - started}
    from symq.backends.zdd_native import NativeZDDAlgebra

    # ``collect_every`` is a one-shot contract: collection invalidates node ids, so each circuit
    # needs its own manager and the two output tuples are compared while both are pinned.
    try:
        left_algebra = NativeZDDAlgebra(left.width, budget.start(), collect_every=collect)
        right_algebra = NativeZDDAlgebra(right.width, budget.start(), collect_every=collect)
        left_outputs = left_algebra.simulate(left)
        right_outputs = right_algebra.simulate(right)
        left_forms = [left_algebra.to_anf(value) for value in left_outputs]
        right_forms = [right_algebra.to_anf(value) for value in right_outputs]
        equivalent = left_forms == right_forms
        return {"status": "ok", "equivalent": equivalent,
                "seconds": time.perf_counter() - started,
                "collections": left_algebra.collections + right_algebra.collections}
    except ResourceLimitExceeded as error:
        return {"status": "budget", "detail": str(error),
                "seconds": time.perf_counter() - started}


def sat(left, right) -> dict:
    try:
        from symq.sat import check_sat_equivalence
    except Exception as error:  # noqa: BLE001
        return {"status": "unavailable", "detail": str(error)}
    budget = Budget(max_seconds=MAX_SECONDS)
    try:
        verdict = check_sat_equivalence(left, right, budget=budget)
    except Exception as error:  # noqa: BLE001 - an encoder or solver failure is data
        return {"status": "error", "detail": f"{type(error).__name__}: {error}"}
    if verdict.outcome == "inconclusive":
        return {"status": "budget", "detail": verdict.detail, "seconds": verdict.seconds}
    return {"status": "ok", "equivalent": verdict.outcome == "equivalent",
            "seconds": verdict.seconds, "witness_checked": verdict.witness_checked,
            "clauses": verdict.clauses}


def tasks():
    """Families chosen so that some favour symbolic expansion and some do not."""
    rng = random.Random(20261028)
    out: list[tuple[str, Circuit, Circuit]] = []
    for bits in (8, 12, 16, 20):
        adder = ADDERS.adder(bits)
        out.append((f"adder_{bits}_same", adder, type(adder)(adder.width, list(adder.gates))))
        out.append((f"adder_{bits}_mutant", adder, mutate(adder, rng, "insert")[0]))
    for width, gates in ((10, 80), (12, 120), (14, 160)):
        base = random_circuit(width, gates, rng)
        out.append((f"rand{width}x{gates}_equiv", base,
                    equivalent_variant(base, rng, steps=4)))
        out.append((f"rand{width}x{gates}_diff", base, mutate(base, rng, "insert")[0]))
    for width in (6, 8, 10):
        base = random_circuit(width, width * 6, rng)
        out.append((f"deep{width}_equiv", base,
                    Circuit(width, [*base.gates, *base.inverse().gates, *base.gates])))
    return out


def main() -> int:
    rows = []
    for name, left, right in tasks():
        record = {"task": name, "width": left.width, "gates": len(left.gates)}
        record["zdd"] = symbolic(left, right, collect=None)
        record["zdd_gc"] = symbolic(left, right, collect=400_000)
        record["sat"] = sat(left, right)
        decided = {engine: record[engine].get("equivalent")
                   for engine in ("zdd", "zdd_gc", "sat")
                   if record[engine].get("status") == "ok"}
        record["agree"] = len(set(decided.values())) <= 1
        rows.append(record)
        print(f"{name:22s} zdd={record['zdd'].get('status'):6s} "
              f"gc={record['zdd_gc'].get('status'):6s} sat={record['sat'].get('status'):6s} "
              f"agree={record['agree']}", flush=True)

    summary = {}
    for engine in ("zdd", "zdd_gc", "sat"):
        decided = [row for row in rows if row[engine].get("status") == "ok"]
        summary[engine] = {"decided": len(decided), "of": len(rows),
                           "total_seconds": sum(row[engine]["seconds"] for row in decided)}
    print("\n" + json.dumps(summary, indent=1))

    both: dict[str, list[float]] = {engine: [] for engine in ("zdd_gc", "sat")}
    for row in rows:
        if row["zdd"].get("status") != "ok":
            continue
        for engine, values in both.items():
            if row[engine].get("status") == "ok":
                values.append(row[engine]["seconds"] / row["zdd"]["seconds"])
    paired = {engine: (sorted(values)[len(values) // 2] if values else None)
              for engine, values in both.items()}
    print("median ratio vs zdd on commonly decided tasks:", paired)

    disagreements = [row["task"] for row in rows if not row["agree"]]
    payload = {"budget": {"max_seconds": MAX_SECONDS, "max_nodes": MAX_NODES},
               "summary": summary, "median_ratio_vs_zdd": paired,
               "disagreements": disagreements, "rows": rows}
    (HERE.parent / "RESULTS" / "sat_pilot.json").write_text(json.dumps(payload, indent=2) + "\n")
    print("disagreements:", disagreements)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
