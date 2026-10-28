"""Cost of the two-block composition against a monolithic miter, on the worked example.

Not a benchmark campaign: one structured example, both sides encoded in the same engine, the same
solver and the same wall-clock budget.

**Both sides answer the same question.** The composition guarantee ignores wire 3, which the
candidate prefix always flips. The monolithic checker is therefore called with
``Contract(observed_outputs=(0, 1, 2))``, not with all four wires observed: comparing an
all-outputs monolithic verdict against a three-outputs compositional verdict would compare two
different predicates, and the earlier pilot did exactly that (monolithic said ``different``,
composition said ``accepted``, and the report called the pair ``ok``).

The earlier reachable-state suffix from ``7e7b481`` is recorded under ``historical``, clearly marked
as **not** an equivalent predicate: that revision did not prove the universal lemma, so its timing
is not a proof-cost comparison.

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
    OBSERVED,
    STRONG_RELATION,
    WIDTH,
    block_a,
    block_a_with_scratch_junk,
    block_b,
    guarantee,
)

from symq import Budget, Circuit
from symq.sat import Contract, check_sat_equivalence
from symq.sat.assumptions import Const, depth, variables
from symq.sat.composition import Interface, check_composition

REPEATS = 5
MAX_SECONDS = 30.0


def composed_left() -> Circuit:
    return Circuit(WIDTH, [*block_a().gates, *block_b().gates])


def composed_right() -> Circuit:
    return Circuit(WIDTH, [*block_a_with_scratch_junk().gates, *block_b().gates])


def monolithic() -> dict:
    """The monolithic miter over the **same** observed wires the composition contract uses."""
    times = []
    last = None
    contract = Contract(observed_outputs=OBSERVED)
    for _ in range(REPEATS):
        started = time.perf_counter()
        last = check_sat_equivalence(
            composed_left(),
            composed_right(),
            contract=contract,
            budget=Budget(max_seconds=MAX_SECONDS),
        )
        times.append(time.perf_counter() - started)
    return {
        "predicate": f"observed_outputs={OBSERVED}",
        "outcome": last.outcome,
        "equivalent": last.equivalent,
        "median_seconds": statistics.median(times),
        "clauses": last.clauses,
        "variables": last.variables,
    }


def monolithic_all_wires() -> dict:
    """The *different* question the old pilot actually asked, kept only to document the mismatch."""
    times = []
    last = None
    for _ in range(REPEATS):
        started = time.perf_counter()
        last = check_sat_equivalence(
            composed_left(), composed_right(), budget=Budget(max_seconds=MAX_SECONDS)
        )
        times.append(time.perf_counter() - started)
    return {
        "predicate": "all four wires",
        "outcome": last.outcome,
        "median_seconds": statistics.median(times),
        "clauses": last.clauses,
        "variables": last.variables,
        "note": "not comparable with the composition, which ignores wire 3",
    }


def compositional() -> dict:
    times = []
    last = None
    interface = Interface(WIDTH, Const(True), STRONG_RELATION)
    for _ in range(REPEATS):
        started = time.perf_counter()
        last = check_composition(
            prefix_left=block_a(),
            prefix_right=block_a_with_scratch_junk(),
            suffix_left=block_b(),
            suffix_right=block_b(),
            interface=interface,
            guarantee=guarantee(),
            budget=Budget(max_seconds=MAX_SECONDS),
        )
        times.append(time.perf_counter() - started)
    return {
        "accepted": last.accepted,
        "timed_out": last.timed_out,
        "median_seconds": statistics.median(times),
        "sum_obligation_seconds": last.total_seconds,
        "sum_clauses": sum(item.clauses for item in last.obligations),
        "obligations": {
            item.name: {
                "clauses": item.clauses,
                "variables": item.variables,
                "satisfiable": item.satisfiable,
                "seconds": item.seconds,
            }
            for item in last.obligations
        },
    }


def main() -> int:
    interface = Interface(WIDTH, Const(True), STRONG_RELATION)
    monolithic_result = monolithic()
    composition_result = compositional()
    payload = {
        "example": "block_a;block_b vs block_a_with_scratch_junk;block_b, width 4",
        "predicate": {
            "composition": "observed wires (0, 1, 2); wire 3 is ignored garbage",
            "monolithic": f"Contract(observed_outputs={OBSERVED})",
            "same_predicate": True,
        },
        "current": {
            "monolithic": monolithic_result,
            "composition": composition_result,
            "ratio": (
                composition_result["median_seconds"] / monolithic_result["median_seconds"]
                if monolithic_result["median_seconds"]
                else None
            ),
            "interface": {
                "wires": WIDTH,
                "relation_variables": len(variables(interface.relation)),
                "relation_depth": depth(interface.relation),
                "precondition_variables": len(variables(interface.precondition)),
            },
        },
        "different_predicate_not_a_comparison": {
            "monolithic_all_outputs": monolithic_all_wires(),
            "why": "the composition ignores wire 3 and the all-outputs miter does not; the two "
            "answers are 'accepted' and 'different' for that reason alone",
        },
        "historical_7e7b481": {
            "suffix_obligation": "reachable-state (prefixes encoded, u and v tied through x)",
            "proved_universal_lemma": False,
            "median_seconds": 0.00045,
            "clauses": 112,
            "ratio_vs_monolithic": 2.78,
            "status": "NOT a fair proof-cost comparison: different predicate and a weaker theorem",
        },
        "limits": {"max_seconds": MAX_SECONDS, "repeats": REPEATS},
    }
    (HERE.parent / "RESULTS" / "composition_pilot.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    print(json.dumps(payload, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
