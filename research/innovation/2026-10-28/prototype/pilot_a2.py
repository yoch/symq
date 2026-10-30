"""Pilot A2: is the widened criterion useful on programs people actually write?

``pilot_a.py`` shows the channel criterion accepts strictly more programs than O2 (40 vs 36 of
300 random ones), and that the density-matrix oracle confirms every extra acceptance. The
question that decides whether this matters is different:

    do the **canonical** measurement-based-uncomputation programs -- the ones an HMR compiler
    emits -- pass O2, or only the channel criterion?

If every such program already passes O2, the widening is a curiosity. If the canonical form
fails O2 and passes the channel criterion, the strict obligation is rejecting correct compiled
programs, which is a real (if modest) correctness/expressiveness result.

The construction tested is the standard one: compute into a clean ancilla, copy the result out,
then uncompute the ancilla with ``hmr``. The correction that makes it a *channel* identity
rather than a branch identity is the point of the experiment.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "src"))

import channel
import factored

from symq.phase import PhaseProgram, check_phase_equivalence, phase_semantics


def and_gadget(correction: bool, measure: bool) -> PhaseProgram:
    """``t ^= x0 x1`` through a clean ancilla, uncomputed by X-basis measurement."""
    program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    if measure:
        outcome = program.hmr(3)
        if correction:
            program.cz_if(outcome, 0, 1)
    return program


def and_chain(length: int, correction: str) -> PhaseProgram:
    """A chain of ``length`` ancilla ANDs, each measured, each optionally corrected.

    ``correction="data"`` corrects on the data wires (the usual form);
    ``correction="outcome"`` adds a phase that depends only on the outcomes;
    ``correction="none"`` omits the correction altogether.
    """
    data = 3
    program = PhaseProgram(data, length)
    for index in range(length):
        ancilla = data + index
        program.ccx(0, 1, ancilla)
        program.cx(ancilla, 2)
        outcome = program.hmr(ancilla)
        if correction == "data":
            program.cz_if(outcome, 0, 1)
        elif correction == "outcome":
            program.z_if(outcome, ancilla)
    return program


def classify(program: PhaseProgram) -> dict:
    """Compare the program against the identity on ``data + ancillas`` wires."""
    semantics = phase_semantics(program)
    strict = check_phase_equivalence(program, PhaseProgram(3))
    verdict = factored.equivalent_channel(program, PhaseProgram(3, program.ancillas))
    return {
        "measurements": program.measurements,
        "o2_violations": [v for v in semantics.violations() if v.startswith("O2")],
        "o1_violations": [v for v in semantics.violations() if v.startswith("O1")],
        "strict_equivalent": strict.equivalent,
        "channel_equivalent_to_identity": verdict.equivalent,
        "channel_reason": verdict.reason,
        "unclean_ancillas": factored.factor(program).unclean_ancillas(),
    }


def main() -> int:
    payload = {"cases": []}
    for length in (1, 2, 3):
        for correction in ("data", "outcome", "none"):
            program = and_chain(length, correction)
            record = {"kind": f"and_chain_{length}_{correction}", **classify(program)}
            payload["cases"].append(record)
    gadget = {
        "kind": "and_gadget_no_correction",
        **classify(and_gadget(correction=False, measure=True)),
    }
    payload["cases"].append(gadget)
    payload["gadget_vs_specification"] = {
        "channel": factored.equivalent_channel(
            and_gadget(correction=True, measure=True),
            PhaseProgram(3, 1).ccx(0, 1, 2)).__dict__,
        "oracle": channel.same_channel(and_gadget(correction=True, measure=True),
                                       PhaseProgram(3, 1).ccx(0, 1, 2)),
    }
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "PILOT_A2.json")
    out.write_text(json.dumps(payload, indent=2) + "\n")
    for case in payload["cases"]:
        print(f"{case['kind']:28s} O2={len(case['o2_violations'])} "
              f"channel={case['channel_equivalent_to_identity']:d} "
              f"ancillas={case['unclean_ancillas']}")
    print(payload["gadget_vs_specification"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
