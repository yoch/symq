"""Diagnostic for issue #70: is there structural slack in a miter, and how much?

No preprocessing is implemented here. The question is whether a *measured* reduction exists on
pairs that a user actually checks, because two obvious cases give no room at all:

* **identical pairs** share their whole gate list, so a prefix share is 100 % -- and they are also
  the least interesting input a checker receives;
* **full equivalence** observes every output, so every wire is live in the backward cone and a
  plain cone pruning removes nothing.

What is measured, for each pair:

* gate counts on both sides;
* the longest exact common prefix;
* the live cone of the observed outputs, computed backwards from the outputs through the gates,
  which is the set a cone-pruning pass would keep;
* the resulting clause/variable reduction a TSA encoder would see if it pruned to that cone.

Three families, chosen to separate the cases: synthetic variants from one generator, independent
constructions of the same function, and partial-output contracts where pruning can legitimately
drop work.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from symq import Circuit
from symq.generators import equivalent_variant, mutate, random_circuit


def load_adders():
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("diag_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["diag_adders"] = module
    spec.loader.exec_module(module)
    return module


ADDERS = load_adders()


def common_prefix(left: Circuit, right: Circuit) -> int:
    """Longest prefix of gates identical on both sides, in order."""
    count = 0
    for first, second in zip(left.gates, right.gates):
        if first != second:
            break
        count += 1
    return count


def live_cone(circuit: Circuit, observed: set[int]) -> int:
    """Gates that can influence an observed output, found by walking backwards.

    A gate is live if its target is live; then all its controls become live and the gate before it
    on any of those wires stays reachable. This is the standard backward cone used by miter
    preprocessing, computed here only to *size* it.
    """
    live_wires = set(observed)
    live_gates = 0
    for gate in reversed(circuit.gates):
        *controls, target = gate.qubits
        if target in live_wires:
            live_gates += 1
            live_wires.update(controls)
    return live_gates


def pair_report(name: str, left: Circuit, right: Circuit, observed: set[int] | None) -> dict:
    if observed is None:
        observed = set(range(left.width))
    left_live = live_cone(left, observed)
    right_live = live_cone(right, observed)
    prefix = common_prefix(left, right)
    return {
        "pair": name,
        "width": left.width,
        "gates_left": len(left.gates),
        "gates_right": len(right.gates),
        "observed_outputs": len(observed),
        "common_prefix": prefix,
        "prefix_fraction": prefix / max(len(left.gates), len(right.gates), 1),
        "live_left": left_live,
        "live_right": right_live,
        # What a cone-pruning pass would remove from each side.
        "prunable_left": len(left.gates) - left_live,
        "prunable_right": len(right.gates) - right_live,
        "prunable_fraction": ((len(left.gates) - left_live) + (len(right.gates) - right_live))
        / max(len(left.gates) + len(right.gates), 1),
    }


def families():
    rng = random.Random(20261028)
    out: list[tuple[str, Circuit, Circuit, set[int] | None]] = []

    # 1. Synthetic variants of one generator: the case a checker sees most often in CI.
    base = random_circuit(10, 60, rng)
    out.append(("synth/variant_shared_prefix", base, equivalent_variant(base, rng, steps=2),
                None))
    out.append(("synth/variant_rewritten", base,
                equivalent_variant(base, rng, steps=40), None))
    out.append(("synth/mutant_one_gate", base, mutate(base, rng, "insert")[0], None))
    out.append(("synth/identical", base, Circuit(10, list(base.gates)), None))

    # 2. Independent constructions of the same function.
    for bits in (8, 12):
        adder = ADDERS.adder(bits)
        out.append((f"indep/adder_{bits}_self", adder,
                    Circuit(adder.width, list(adder.gates)), None))
    # A long common prefix written by hand, then a divergence: the case a prefix share would catch.
    common = random_circuit(8, 40, rng)
    out.append(("indep/shared_prefix_then_diverge",
                Circuit(8, [*common.gates, *random_circuit(8, 5, rng).gates]),
                Circuit(8, [*common.gates, *random_circuit(8, 5, rng).gates]), None))

    # 3. Contracts that observe only part of the outputs: the only place pruning can pay.
    wide = random_circuit(12, 80, rng)
    other = equivalent_variant(wide, rng, steps=6)
    out.append(("contract/all_outputs", wide, other, None))
    out.append(("contract/one_output", wide, other, {0}))
    out.append(("contract/quarter_outputs", wide, other, {0, 1, 2}))
    return out


def main() -> int:
    rows = [pair_report(name, left, right, observed) for name, left, right, observed in families()]
    for row in rows:
        print(f"{row['pair']:32s} g={row['gates_left']:3d}/{row['gates_right']:3d} "
              f"prefix={row['prefix_fraction']:5.2f} "
              f"live={row['live_left']:3d}/{row['live_right']:3d} "
              f"prunable={row['prunable_fraction']:5.2f}", flush=True)
    payload = {"rows": rows,
               "note": "sizes only; no preprocessing is implemented or claimed"}
    (HERE.parent / "RESULTS" / "issue70_diagnostic.json").write_text(
        json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
