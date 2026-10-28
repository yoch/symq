"""Pilot B: verify equivalence by simulating the composed circuit instead of both outputs.

The observation. Every gate of the accepted fragment is its own inverse, so ``L ; R^{-1}`` is a
circuit of ``|L| + |R|`` gates, and ``L ~ R`` iff ``L ; R^{-1}`` is the identity permutation.
That much is a miter, and miters are standard in SAT-based equivalence checking.

What is specific to the ANF/ZDD setting is *why* the composition is cheap. Comparing outputs
requires materialising ``f_L`` and ``f_R`` -- two polynomials that can each be enormous -- and
then comparing them. Simulating the composition instead keeps every intermediate polynomial on
the *difference*, which cancels as soon as the circuits agree. When ``L`` and ``R`` differ in
only a few gates, the work is proportional to the difference, not to the common part.

The experiment separates the two effects:

* ``separate``: simulate ``L`` and ``R`` with two managers, compare wire by wire (the current
  checker);
* ``miter``: simulate ``L ; R^{-1}`` with one manager and test for the identity.

Both are exact and must agree on every instance; the question is which one finishes inside the
budget, and at what node cost.
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

from symq import Circuit, make_algebra
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.resources import Budget, ResourceLimitExceeded


def separate(left: Circuit, right: Circuit, budget: Budget) -> dict:
    started = time.perf_counter()
    algebra = make_algebra("zdd", left.width, budget)
    outputs_left = algebra.simulate(left)
    nodes_left = algebra.node_count
    outputs_right = algebra.simulate(right)
    nodes_right = algebra.node_count - nodes_left
    if len(outputs_left) != len(outputs_right):
        raise AssertionError("width mismatch")
    equivalent = all(algebra.equal(a, b) for a, b in zip(outputs_left, outputs_right))
    return {"equivalent": equivalent, "seconds": time.perf_counter() - started,
            "nodes": algebra.node_count, "nodes_left": nodes_left,
            "nodes_right": nodes_right,
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
    if {"status"} - {k for k in row["separate"]} and {"status"} - {k for k in row["miter"]}:
        pass
    if "equivalent" in row["separate"] and "equivalent" in row["miter"]:
        row["agree"] = row["separate"]["equivalent"] == row["miter"]["equivalent"]
    return row


def instances(seed: int = 20261028) -> list[tuple[str, Circuit, Circuit]]:
    rng = random.Random(seed)
    cases: list[tuple[str, Circuit, Circuit]] = []
    for width, gates in ((12, 80), (16, 120), (20, 160), (24, 200)):
        base = random_circuit(width, gates, rng)
        cases.append((f"rand{width}_equiv_small_edits", base,
                      equivalent_variant(base, rng, steps=6)))
        cases.append((f"rand{width}_nonequiv_one_gate", base, mutate(base, rng, "insert")[0]))
        # A long common prefix with a short divergence is the case the miter should win.
        common = random_circuit(width, gates, rng)
        tail_left = random_circuit(width, 6, rng)
        tail_right = random_circuit(width, 6, rng)
        cases.append((f"rand{width}_common_prefix_differing_tail",
                      Circuit(width, [*common.gates, *tail_left.gates]),
                      Circuit(width, [*common.gates, *tail_right.gates])))
    return cases


def main() -> int:
    budget = Budget(max_nodes=2_000_000, max_seconds=30.0)
    rows = []
    for name, left, right in instances():
        row = {"case": name, **run_one(left, right, budget)}
        rows.append(row)
        summary = (f"{name:38s} separate={row['separate'].get('seconds', float('nan')):7.3f}s "
                   f"{row['separate'].get('nodes', 0):8d}n  "
                   f"miter={row['miter'].get('seconds', float('nan')):7.3f}s "
                   f"{row['miter'].get('nodes', 0):8d}n  agree={row.get('agree')}")
        print(summary)
    payload = {"budget": {"max_nodes": 2_000_000, "max_seconds": 30.0}, "rows": rows}
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "PILOT_B.json")
    out.write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
