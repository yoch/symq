"""Pilot B2: miter vs separate simulation on the structured QCEC corpus.

The dense random circuits of ``pilot_b.py`` blow up for both methods, so they cannot separate
them. The structured circuits are the ones where equivalence checking is actually asked for:
arithmetic blocks and LUT-derived circuits, most of them with thousands of gates but a shallow
algebraic structure.

Each instance is a real circuit ``C`` and a variant built from semantics-preserving rewrites
(the same generator the paper used), so the answer is known independently: ``equiv`` variants
are equivalent, ``nonequiv`` variants insert one gate and are not.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
assert (ROOT / "benchmarks").is_dir(), ROOT
sys.path.insert(0, str(ROOT / "src"))

from symq import Circuit, make_algebra
from symq.corpus import load_corpus
from symq.generators import equivalent_variant, mutate
from symq.resources import Budget, ResourceLimitExceeded

MANIFEST = ROOT / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json"


def separate(left: Circuit, right: Circuit, budget: Budget) -> dict:
    started = time.perf_counter()
    algebra = make_algebra("zdd", left.width, budget)
    outputs_left = algebra.simulate(left)
    outputs_right = algebra.simulate(right)
    equivalent = all(algebra.equal(a, b) for a, b in zip(outputs_left, outputs_right))
    return {"equivalent": equivalent, "seconds": time.perf_counter() - started,
            "nodes": algebra.node_count,
            "terms": sum(algebra.terms(v) or 0 for v in (*outputs_left, *outputs_right))}


def miter(left: Circuit, right: Circuit, budget: Budget) -> dict:
    composed = Circuit(left.width, [*left.gates, *right.inverse().gates])
    started = time.perf_counter()
    algebra = make_algebra("zdd", left.width, budget)
    outputs = algebra.simulate(composed)
    identity = all(algebra.equal(value, algebra.variable(index))
                   for index, value in enumerate(outputs))
    return {"equivalent": identity, "seconds": time.perf_counter() - started,
            "nodes": algebra.node_count,
            "terms": sum(algebra.terms(v) or 0 for v in outputs)}


def run_one(left: Circuit, right: Circuit, budget: Budget) -> dict:
    row = {"width": left.width, "gates_left": len(left.gates),
           "gates_right": len(right.gates)}
    for name, function in (("separate", separate), ("miter", miter)):
        try:
            row[name] = function(left, right, budget)
        except ResourceLimitExceeded as error:
            row[name] = {"status": "budget", "detail": f"{error.resource} limit exceeded"}
        except MemoryError:
            row[name] = {"status": "memory"}
        except RecursionError:
            row[name] = {"status": "recursion"}
    if "equivalent" in row["separate"] and "equivalent" in row["miter"]:
        row["agree"] = row["separate"]["equivalent"] == row["miter"]["equivalent"]
    return row


def instances(seed: int = 20261028, limit: int | None = None):
    rng = random.Random(seed)
    corpus = load_corpus(MANIFEST)
    entries = [entry for entry in corpus.entries if entry.supported]
    for entry in entries[:limit]:
        circuit = entry.load()
        if circuit.width > 20 or len(circuit.gates) > 400:
            continue
        for workload in ("equiv", "nonequiv"):
            other = (equivalent_variant(circuit, rng, steps=len(circuit.gates))
                     if workload == "equiv" else mutate(circuit, rng, "insert")[0])
            yield f"{entry.name}_{workload}", circuit, other


def main() -> int:
    budget = Budget(max_nodes=4_000_000, max_seconds=30.0)
    rows = []
    for name, left, right in instances(limit=40):
        row = {"case": name, **run_one(left, right, budget)}
        rows.append(row)
        print(f"{name:24s} sep={row['separate'].get('seconds', float('nan')):6.2f}s "
              f"{row['separate'].get('nodes', 0):7d}n  "
              f"mit={row['miter'].get('seconds', float('nan')):6.2f}s "
              f"{row['miter'].get('nodes', 0):7d}n  "
              f"agree={row.get('agree')}", flush=True)
    payload = {"budget": {"max_nodes": 4_000_000, "max_seconds": 30.0}, "rows": rows}
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "PILOT_B2.json")
    out.write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
