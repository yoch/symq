"""Pilot A, corrected: every gadget is compared with *its own* specification.

The first version compared every AND gadget with the identity, including the gadgets that change
the data wires, so the question it answered was not the one it claimed to answer. Here each
program is compared with the reversible circuit it is supposed to implement, built independently,
and the result is cross-checked with the exact density-matrix oracle.

Two families:

``gadgets``
    computation into a clean ancilla, copy-out, ``hmr`` uncomputation, and a correction that is
    either on the data wires (the canonical form), on the outcome alone, or absent;
``kernel``
    programs whose syndrome vectors differ but whose *kernels* agree, because the two syndrome
    vectors are related by an invertible GF(2) map -- the case the channel criterion exists for.

For each program the report counts, separately:

* accepted by the strict criterion (O1 + O2 + equality up to a global phase);
* accepted by the channel criterion;
* confirmed by the density-matrix oracle;
* incompatible with the model (never silently dropped).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE.parent))

import channel
import factored

from symq.phase import PhaseProgram, check_phase_equivalence


def and_gadget(*, correction: str, measure: bool = True) -> tuple[PhaseProgram, PhaseProgram]:
    """``t ^= x0 x1`` through a clean ancilla; returns (program, specification)."""
    data = 3
    program = PhaseProgram(data, 1).ccx(0, 1, 3).cx(3, 2)
    specification = PhaseProgram(data, 1).ccx(0, 1, 2)
    if measure:
        outcome = program.hmr(3)
        if correction == "data":
            program.cz_if(outcome, 0, 1)
        elif correction == "outcome":
            # A phase that depends only on the outcome: it cannot change the channel.
            program.x(3)
            program.z_if(outcome, 3)
    return program, specification


def and_chain(length: int, correction: str) -> tuple[PhaseProgram, PhaseProgram]:
    """``length`` independent ancilla ANDs, each measured, then corrected."""
    program = PhaseProgram(3, length)
    for index in range(length):
        ancilla = 3 + index
        program.ccx(0, 1, ancilla)
        program.cx(ancilla, 2)
        if correction != "none":
            outcome = program.hmr(ancilla)
            if correction == "data":
                program.cz_if(outcome, 0, 1)
            else:
                program.x(ancilla)
                program.z_if(outcome, ancilla)
        else:
            program.hmr(ancilla)
    specification = PhaseProgram(3, length).ccx(0, 1, 2)
    return program, specification


def syndrome_pair() -> tuple[PhaseProgram, PhaseProgram, PhaseProgram]:
    """Two programs whose syndrome vectors are related by an invertible map.

    ``left`` measures ``x0`` then ``x1``; ``middle`` measures ``x0`` then ``x0 xor x1``. The
    kernels of the two syndrome vectors are the same set of pairs, so the channels agree. ``right``
    measures ``x0`` twice, which changes the kernel and must be rejected.
    """
    left = PhaseProgram(2, 2)
    left.mcx(0, 2)
    left.hmr(2)
    left.mcx(1, 3)
    left.hmr(3)

    middle = PhaseProgram(2, 2)
    middle.mcx(0, 2)
    middle.hmr(2)
    middle.cx(0, 3)
    middle.mcx(1, 3)
    middle.hmr(3)

    right = PhaseProgram(2, 2)
    right.mcx(0, 2)
    right.hmr(2)
    right.mcx(0, 3)
    right.hmr(3)
    return left, middle, right


def classify(program: PhaseProgram, specification: PhaseProgram) -> dict:
    record = {"measurements": program.measurements, "ancillas": program.ancillas}
    try:
        strict = check_phase_equivalence(program, specification)
        record["strict"] = strict.equivalent and not strict.violations
        record["strict_violations"] = list(strict.violations)
        record["channel"] = factored.equivalent_channel(program, specification).equivalent
        record["oracle"] = channel.same_channel(program, specification)
        record["oracle_traced"] = channel.same_channel(program, specification,
                                                        trace_ancillas=True)
    except (ValueError, TypeError) as error:
        record["strict"] = None
        record["channel"] = None
        record["oracle"] = None
        record["incompatible"] = f"{type(error).__name__}: {error}"
    return record


def main() -> int:
    cases: list[tuple[str, PhaseProgram, PhaseProgram]] = []
    for correction in ("data", "outcome", "none"):
        program, specification = and_gadget(correction=correction)
        cases.append((f"and_gadget_{correction}", program, specification))
    for length in (1, 2, 3, 5):
        for correction in ("data", "outcome", "none"):
            program, specification = and_chain(length, correction)
            cases.append((f"and_chain_{length}_{correction}", program, specification))
    left, middle, right = syndrome_pair()
    cases.append(("syndrome_invertible_left_vs_middle", left, middle))
    cases.append(("syndrome_same_control_left_vs_right", left, right))

    rows = []
    for name, program, specification in cases:
        record = {"case": name, **classify(program, specification)}
        rows.append(record)
        print(f"{name:36s} strict={record.get('strict')!s:5s} "
              f"channel={record.get('channel')!s:5s} oracle={record.get('oracle')!s:5s} "
              f"violations={len(record.get('strict_violations', []))}", flush=True)

    strict_only = [r["case"] for r in rows if r.get("strict") and not r.get("channel")]
    channel_only = [r["case"] for r in rows if r.get("channel") and not r.get("strict")]
    both = [r["case"] for r in rows if r.get("channel") and r.get("strict")]
    neither = [r["case"] for r in rows
               if r.get("channel") is False and r.get("strict") is False]
    incompatible = [r["case"] for r in rows if r.get("incompatible")]
    mismatched = [r["case"] for r in rows if r.get("channel") != r.get("oracle")]
    summary = {"both": both, "channel_only": channel_only, "strict_only": strict_only,
               "neither": neither, "incompatible": incompatible,
               "criterion_disagrees_with_oracle": mismatched}
    print(json.dumps(summary, indent=1))
    out = HERE.parent / "RESULTS_A_CORRECTED.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
