"""Cost of the two-block composition against a monolithic miter, on the worked example.

Not a benchmark campaign: one structured example, both sides encoded in the same engine, the same
solver and the same wall-clock budget, with the interface width reported because that is the quantity
that decides whether composition is worth stating at all.

What is measured:

* the monolithic miter of the two concatenated circuits (what the checker does today);
* the composition: four SAT queries, of which the prefix and composition ones are the expensive
  pair;
* the size of the interface, in wires and in expression nodes.

``unsupported`` and ``inconclusive`` are reported separately and never folded into a time.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_composition import (
    WIDTH,
    block_a,
    block_a_with_scratch_junk,
    block_b,
    guarantee,
)

from symq import Budget, Circuit
from symq.sat import check_sat_equivalence
from symq.sat.assumptions import Const, Eq, Var, depth, variables
from symq.sat.composition import (
    Interface,
    check_composition,
)

REPEATS = 5
MAX_SECONDS = 30.0


def monolithic(left: Circuit, right: Circuit) -> dict:
    times = []
    last = None
    for _ in range(REPEATS):
        started = time.perf_counter()
        last = check_sat_equivalence(left, right, budget=Budget(max_seconds=MAX_SECONDS))
        times.append(time.perf_counter() - started)
    return {"status": "ok" if last.outcome != "inconclusive" else "inconclusive",
            "median_seconds": statistics.median(times),
            "clauses": last.clauses, "variables": last.variables}


def compositional() -> dict:
    times = []
    last = None
    interface = Interface(WIDTH, Const(True), Eq(Var("u.2"), Var("v.2")))
    for _ in range(REPEATS):
        started = time.perf_counter()
        last = check_composition(
            prefix_left=block_a(), prefix_right=block_a_with_scratch_junk(),
            suffix_left=block_b(), suffix_right=block_b(),
            interface=interface, guarantee=guarantee(),
            budget=Budget(max_seconds=MAX_SECONDS))
        times.append(time.perf_counter() - started)
    total_clauses = sum(item.clauses for item in last.obligations)
    return {"accepted": last.accepted,
            "median_seconds": statistics.median(times),
            "total_clauses": total_clauses,
            "obligations": {item.name: {"clauses": item.clauses,
                                        "variables": item.variables,
                                        "satisfiable": item.satisfiable}
                            for item in last.obligations}}


def main() -> int:
    left = Circuit(WIDTH, [*block_a().gates, *block_b().gates])
    right = Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *block_b().gates])
    interface = Interface(WIDTH, Const(True), Eq(Var("u.2"), Var("v.2")))
    payload = {
        "example": "block_a;block_b vs block_a_with_scratch_junk;block_b, width 4",
        "monolithic": monolithic(left, right),
        "composition": compositional(),
        "interface": {
            "wires": WIDTH,
            "relation_variables": len(variables(interface.relation)),
            "relation_depth": depth(interface.relation),
            "precondition_variables": len(variables(interface.precondition)),
        },
        "limits": {"max_seconds": MAX_SECONDS, "repeats": REPEATS},
    }
    (HERE.parent / "RESULTS" / "composition_pilot.json").write_text(
        json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
