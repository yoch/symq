"""Short paired campaign for the final documentation, with the protocol the audit specified.

Not a publication benchmark: the confirmatory campaigns belong to #44/#46. This is the minimum
needed to know whether the documented numbers describe the code as it ships.

Protocol, fixed before running:

* **one call per measurement** -- ``check_sat_equivalence`` once, ``check_equivalence`` once; the
  previous pilot built the CNF twice (once to time encoding, once inside the call) and the strategy
  pilot timed the solver alone, so neither produced comparable totals;
* **same predicate** -- same circuits, same widths, full functional equivalence (no contract);
* **external timing** of the whole call, not of an internal phase;
* **explicit budgets** -- one wall-clock budget applies to every engine; the symbolic engine also
  gets a node budget, which is stated separately because the SAT engine has no equivalent;
* **provenance** -- git SHA, solver version, worktree cleanliness, machine, limits.
"""
from __future__ import annotations

import importlib.util
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from symq import Budget, check_equivalence
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.resources import ResourceLimitExceeded

MAX_SECONDS = 30.0
MAX_NODES = 4_000_000
REPEATS = 3


def load_adders():
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("paired_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["paired_adders"] = module
    spec.loader.exec_module(module)
    return module


ADDERS = load_adders()


def timed_symbolic(left, right, *, collect: int | None) -> dict:
    options = {} if collect is None else {"collect_every": collect}
    budget = Budget(max_seconds=MAX_SECONDS, max_nodes=MAX_NODES)
    started = time.perf_counter()
    try:
        result = check_equivalence(left, right, backend="zdd-native", budget=budget,
                                   backend_options=options)
    except ResourceLimitExceeded:
        return {"status": "budget", "seconds": time.perf_counter() - started}
    return {"status": "ok", "equivalent": result.equivalent,
            "seconds": time.perf_counter() - started}


def timed_sat(left, right) -> dict:
    try:
        from symq.sat import check_sat_equivalence
    except Exception:  # noqa: BLE001
        return {"status": "unavailable"}
    started = time.perf_counter()
    try:
        verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=MAX_SECONDS))
    except Exception as error:  # noqa: BLE001
        return {"status": "error", "detail": f"{type(error).__name__}: {error}"}
    elapsed = time.perf_counter() - started
    if verdict.outcome == "inconclusive":
        return {"status": "budget", "seconds": elapsed, "detail": verdict.detail}
    return {"status": "ok", "equivalent": verdict.outcome == "equivalent",
            "seconds": elapsed, "solver": verdict.solver}


def tasks():
    """Eight tasks: arithmetic, dense, and one pair per family where the engines disagree."""
    rng = random.Random(20261028)
    out = []
    for bits in (12, 16):
        adder = ADDERS.adder(bits)
        out.append((f"adder_{bits}", adder, type(adder)(adder.width, list(adder.gates))))
    for width, gates in ((12, 140), (14, 160)):
        base = random_circuit(width, gates, rng)
        out.append((f"rand{width}x{gates}_diff", base, mutate(base, rng, "insert")[0]))
        out.append((f"rand{width}x{gates}_equiv", base,
                    equivalent_variant(base, rng, steps=4)))
    return out


def provenance() -> dict:
    def run(*args):
        return subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()

    try:
        from symq.sat import versions

        solver = versions()
    except Exception:  # noqa: BLE001
        solver = {}
    return {"git_head": run("git", "-C", str(ROOT), "rev-parse", "HEAD"),
            "worktree_dirty": bool(run("git", "-C", str(ROOT), "status", "--porcelain",
                                       "--untracked-files=no")),
            "python": sys.version.split()[0],
            "solver": solver,
            "limits": {"max_seconds_all_engines": MAX_SECONDS,
                       "max_nodes_symbolic_only": MAX_NODES,
                       "note": "the SAT engine has no node budget; its only bound is wall clock"},
            "repeats": REPEATS}


def main() -> int:
    rows = []
    for name, left, right in tasks():
        record = {"task": name, "width": left.width, "gates": len(left.gates)}
        engines = (("zdd", None), ("zdd_gc", 400_000), ("sat", "sat"))
        for engine, setting in engines:
            samples = []
            status = "ok"
            last = {}
            for _ in range(REPEATS):
                if engine == "sat":
                    last = timed_sat(left, right)
                else:
                    last = timed_symbolic(left, right, collect=setting)
                status = last["status"]
                if status != "ok":
                    samples = []
                    break
                samples.append(last["seconds"])
            record[engine] = {"status": status,
                              "seconds": statistics.median(samples) if samples else None}
            for field in ("equivalent", "solver", "detail"):
                if field in last:
                    record[engine][field] = last[field]
        decided = [record[e]["equivalent"] for e in ("zdd", "zdd_gc", "sat")
                   if record[e]["status"] == "ok"]
        record["agree"] = len(set(decided)) <= 1
        rows.append(record)
        print(f"{name:22s} zdd={record['zdd']['status']:6s} "
              f"gc={record['zdd_gc']['status']:6s} sat={record['sat']['status']:6s} "
              f"agree={record['agree']}", flush=True)

    def total(engine):
        values = [r[engine]["seconds"] for r in rows if r[engine]["status"] == "ok"]
        return round(sum(values), 4) if values else None

    summary = {engine: {"decided": sum(1 for r in rows if r[engine]["status"] == "ok"),
                        "of": len(rows), "total_seconds": total(engine)}
               for engine in ("zdd", "zdd_gc", "sat")}
    payload = {"provenance": provenance(), "summary": summary, "rows": rows,
               "disagreements": [r["task"] for r in rows if not r["agree"]]}
    (HERE.parent / "RESULTS" / "paired_final.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(summary, indent=1))
    print("disagreements:", payload["disagreements"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
