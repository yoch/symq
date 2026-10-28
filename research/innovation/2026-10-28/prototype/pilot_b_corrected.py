"""Pilot B, corrected: the miter measured in time, memory and construction cost.

The first version reported node counts only, which cannot distinguish a strategy that halves
nodes and doubles time from one that improves both. It also never measured the case the
observation is supposed to help with beyond a textually shared prefix.

Protocol, fixed before running:

* every arm gets a **fresh manager** (no shared caches); construction of the composed circuit is
  timed and charged to the miter arm;
* ``separate``: simulate ``L`` and ``R``, compare wire by wire;
* ``miter``: simulate ``L ; R^{-1}`` and test for the identity;
* three families: *prefix* (a long common gate prefix then a short divergence -- the case the
  mechanism predicts), *same structure* (``R`` is a semantics-preserving rewrite of ``L`` with no
  textual prefix: the realistic case), and *arithmetic* (adders of 12-20 bits against their
  inverse);
* report wall time, peak nodes, RSS growth and correctness for both arms, and refuse to conclude
  if the two arms disagree on the *function*.
"""
from __future__ import annotations

import importlib.util
import json
import random
import resource
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

from symq import Circuit, make_algebra, simulate
from symq.generators import equivalent_variant, random_circuit
from symq.resources import Budget, ResourceLimitExceeded

MAX_NODES = 4_000_000
MAX_SECONDS = 30.0


def load_adders():
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("engineering_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["engineering_adders"] = module
    spec.loader.exec_module(module)
    return module


def budget():
    return Budget(max_nodes=MAX_NODES, max_seconds=MAX_SECONDS)


def separate(left, right) -> dict:
    started = time.perf_counter()
    algebra = make_algebra("zdd-native", left.width, budget())
    try:
        outputs_left = simulate(left, algebra)
        outputs_right = simulate(right, algebra)
        equivalent = all(algebra.equal(a, b) for a, b in zip(outputs_left, outputs_right))
        return {"status": "ok", "seconds": time.perf_counter() - started,
                "nodes": algebra.node_count, "equivalent": equivalent}
    except ResourceLimitExceeded as error:
        return {"status": "budget", "detail": f"{error.resource} limit exceeded",
                "seconds": time.perf_counter() - started}


def miter(left, right) -> dict:
    started = time.perf_counter()
    composed = Circuit(left.width, [*left.gates, *right.inverse().gates])
    construction = time.perf_counter() - started
    algebra = make_algebra("zdd-native", left.width, budget())
    try:
        outputs = simulate(composed, algebra)
        identity = all(algebra.equal(value, algebra.variable(index))
                       for index, value in enumerate(outputs))
        return {"status": "ok", "seconds": time.perf_counter() - started,
                "construction_seconds": construction, "nodes": algebra.node_count,
                "equivalent": identity}
    except ResourceLimitExceeded as error:
        return {"status": "budget", "detail": f"{error.resource} limit exceeded",
                "seconds": time.perf_counter() - started,
                "construction_seconds": construction}


def families():
    adders = load_adders()
    rng = random.Random(20261028)
    prefix, structure, arithmetic = [], [], []
    for width, gates in ((10, 60), (12, 80), (14, 100)):
        common = random_circuit(width, gates, rng)
        left = Circuit(width, [*common.gates, *random_circuit(width, 6, rng).gates])
        right = Circuit(width, [*common.gates, *random_circuit(width, 6, rng).gates])
        prefix.append((f"prefix_{width}x{gates}", left, right))
        base = random_circuit(width, gates, rng)
        structure.append((f"rewrite_{width}x{gates}", base,
                          equivalent_variant(base, rng, steps=gates)))
    for bits in (12, 16, 20):
        adder = adders.adder(bits)
        arithmetic.append((f"adder_{bits}_vs_inverse", adder, adder.inverse()))
    return {"prefix": prefix, "structure": structure, "arithmetic": arithmetic}


def main() -> int:
    groups = families()
    rows = []
    for group, cases in groups.items():
        for name, left, right in cases:
            record = {"family": group, "case": name, "width": left.width,
                      "gates_left": len(left.gates), "gates_right": len(right.gates)}
            before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            record["separate"] = separate(left, right)
            record["separate"]["rss_delta_kib"] = (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before)
            before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            record["miter"] = miter(left, right)
            record["miter"]["rss_delta_kib"] = (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before)
            if record["separate"].get("status") == "ok" and record["miter"].get("status") == "ok":
                record["agree"] = (record["separate"]["equivalent"]
                                   == record["miter"]["equivalent"])
            rows.append(record)
            print(f"{name:26s} sep={record['separate'].get('seconds', float('nan')):7.3f}s "
                  f"{record['separate'].get('nodes', 0):8d}n  "
                  f"mit={record['miter'].get('seconds', float('nan')):7.3f}s "
                  f"{record['miter'].get('nodes', 0):8d}n  "
                  f"build={record['miter'].get('construction_seconds', 0):6.3f}s  "
                  f"agree={record.get('agree')}", flush=True)
    out = HERE.parent / "RESULTS_B_CORRECTED.json"
    out.write_text(json.dumps({"rows": rows}, indent=2) + "\n")
    for group in groups:
        selected = [r for r in rows if r["family"] == group]
        both = [r for r in selected if r.get("agree") is not None]
        worse = [r["case"] for r in both
                 if r["miter"]["seconds"] > r["separate"]["seconds"]]
        better = [r["case"] for r in both
                  if r["miter"]["seconds"] < 0.8 * r["separate"]["seconds"]]
        print(f"\n{group}: {len(both)} decided pairs, miter faster on {len(better)}, "
              f"slower on {len(worse)}")
        print(f"  faster: {better}")
        print(f"  slower: {worse}")
        print(f"  disagreements on the function: "
              f"{[r['case'] for r in both if not r['agree']]}")
        if both:
            ratios = sorted(r["miter"]["seconds"] / r["separate"]["seconds"] for r in both)
            print(f"  miter/separate seconds: min={ratios[0]:.2f} median={ratios[len(ratios)//2]:.2f} max={ratios[-1]:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
