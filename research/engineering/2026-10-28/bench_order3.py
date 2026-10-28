"""Campaign 3: validate the chosen order on a family nobody looked at.

Campaigns 1-2 compared heuristics on QCEC circuits, small arithmetic and dense random circuits,
and `reverse` won by 8.5x on the reserved arithmetic family. A policy chosen after seeing results
is not validated by those results, so this campaign runs the decision rule on **new** circuits
generated from seeds and sizes that appear in neither previous campaign:

* adders and controlled adders of 9, 11, 13, 15, 17, 19, 21, 23 bits (every size not used before);
* *multi-controlled* circuits with a different topology: chains of ``mcx`` gates where the
  controls grow along the wires (a pattern no previous case had);
* two ``incr`` circuits (the incrementer family, which is in neither campaign).

Decision rule, restated before running: keep `reverse` as the automatic order if it is at least
1.2x faster than identity in geometric mean on this family and is worse than identity on at most
one instance. Otherwise the order work produces no adoptable policy.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

import adders
import bench_order2

from symq.circuit import Circuit


def incrementer(bits: int) -> Circuit:
    """``x <- x + 1`` with an MCX cascade: controls on ``0..i-1``, target ``i``, high to low."""
    circuit = Circuit(bits)
    for index in range(bits - 1, -1, -1):
        if index == 0:
            circuit.x(0)
        else:
            circuit.mcx(*range(index), index)
    return circuit


def mcx_chain(bits: int) -> Circuit:
    """A growing-control chain: gate ``i`` targets wire ``i`` with controls ``0..i-1``."""
    circuit = Circuit(bits)
    for index in range(1, bits):
        circuit.mcx(*range(index), index)
    return circuit


def family():
    cases = []
    for bits in (9, 11, 13, 15, 17, 19, 21, 23):
        cases.append((f"new_adder_{bits}", adders.adder(bits)))
    for bits in (9, 11, 13, 15, 17):
        cases.append((f"new_cadder_{bits}", adders.adder(bits, controlled=True)))
    for bits in (12, 16, 20):
        cases.append((f"new_incr_{bits}", incrementer(bits)))
    for bits in (12, 16, 20):
        cases.append((f"new_mcxchain_{bits}", mcx_chain(bits)))
    return cases


def main() -> int:
    cases = family()
    candidates = ("identity", "reverse")
    rows = []
    for name, circuit in cases:
        for heuristic in candidates:
            rows.append({"case": name, "width": circuit.width, "gates": len(circuit.gates),
                         **bench_order2.one(circuit, heuristic)})
        reference = next((r["fingerprint"] for r in rows
                          if r["case"] == name and r["order"] == "identity"
                          and r["status"] == "ok"), None)
        for row in rows:
            if row["case"] == name and row["status"] == "ok" and reference:
                row["matches_identity_function"] = row["fingerprint"] == reference
        print(name, {r["order"]: r["status"] for r in rows if r["case"] == name}, flush=True)

    ratios = []
    for name, _ in cases:
        base = next((r for r in rows if r["case"] == name and r["order"] == "identity"
                     and r["status"] == "ok"), None)
        candidate = next((r for r in rows if r["case"] == name and r["order"] == "reverse"
                          and r["status"] == "ok"), None)
        if base and candidate and base["total_seconds"] > 0:
            ratios.append((name, candidate["total_seconds"] / base["total_seconds"]))
    geomean = statistics.geometric_mean([value for _, value in ratios])
    worse = [name for name, value in ratios if value > 1.0]
    bad = sum(1 for row in rows if row.get("matches_identity_function") is False)
    print(f"\nreverse/identity geomean = {geomean:.3f} over {len(ratios)} completed pairs")
    print(f"worse than identity on {len(worse)} instance(s): {worse}")
    print(f"wrong function: {bad}")
    print(f"decision: {'adopt' if geomean <= 1 / 1.2 and len(worse) <= 1 else 'reject'}")
    out = HERE.parent / "RESULTS_ORDER3.json"
    out.write_text(json.dumps({"geomean": geomean, "worse": worse, "wrong_function": bad,
                               "ratios": ratios, "rows": rows}, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
