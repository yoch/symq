"""Interoperability of the #90 CPTP oracle and the #94 phase-debt repair.

**This file exists because an earlier audit conclusion was wrong.**

I previously reported a P1 "incompatible HMR conventions" between `phase_semantics` and the #90
oracle, claiming that appending a `CZ` conditioned on the outcome would *reapply* the sign instead of
cancelling it. That was an error of reference selection: I compared the corrected circuit against
`value_ops + reset`, which is itself a decohering channel, instead of against the plain value circuit.

The algebra is elementary:

    Kraus branch for outcome m carries        (-1)^{m g(x)}
    an appended conditional sign gate adds    (-1)^{m g(x)}
    product:                                  (-1)^{2 m g(x)} = 1

In ANF notation that is `m*g(x) XOR m*g(x) = 0`, exactly what `phase_semantics` reports.

## How the reference is chosen

Both programs must agree on **all four wires**, including the ancillas. An HMR resets its ancilla, so
a circuit that measures ancilla `q` ends with wire `q` in `|0>` whatever it was before. The reference
must therefore also leave `q` in `|0>`, which means either (a) not touch it at all, or (b) apply the
same value op and then a reset. Case (b) is *not* channel-equal to (a): a reset decoheres, so the
reference for a corrected HMR is the plain value circuit, not "value + reset".

## Ordering constraint, which is real and worth stating

A late correction is valid only if the monomial it uses is still the monomial that was recorded at
measurement time. If a value operation changes one of those wires between the measurement and the
correction, the correction acts on a different function and does **not** cancel the debt. That is not
a defect: it is exactly why #94 recomputes the phase with the *final* live functions instead of
assuming the phase commutes through arbitrary gates.
"""
from __future__ import annotations

import itertools
import os
import sys
from fractions import Fraction as F
from pathlib import Path

PR90 = Path(os.environ.get("PR90", "/tmp/audit/pr90"))
sys.path.insert(0, str(PR90))

from research.hybrid_channel.oracle import (
    HybridProgram,
    coherence_image,
    coherence_instrument,
    same_channel,
)

results: list[tuple[str, bool, str]] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    results.append((label, passed, detail))


# ------------------------------------------------------------------ 1. the canonical gadget


def canonical():
    """The user's interop test, plus its negations and the branch-level check."""
    corrected = (
        HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(0, 1, condition="b0")
    )
    uncorrected = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0")
    reference = HybridProgram(3, 1).ccx(0, 1, 2)

    check("corrected == reference (full channel)", same_channel(corrected, reference).equivalent)
    check(
        "corrected == reference (ancillas traced)",
        same_channel(corrected, reference, trace_ancillas=True).equivalent,
    )
    check(
        "uncorrected != reference",
        not same_channel(uncorrected, reference).equivalent,
    )
    # The trap that produced the false P1: reset decoheres, so it is not a valid reference.
    value_reset = HybridProgram(3, 1).mcx(0, 1, 3).mcx(3, 2).reset(3)
    check(
        "value+reset is NOT the reference (reset decoheres)",
        not same_channel(value_reset, reference).equivalent,
    )
    return corrected, reference


def branch_check(corrected, reference, label: str):
    """Summing the corrected program over observed outcomes must reproduce the reference."""
    bad = 0
    for x, y in itertools.product(range(8), repeat=2):
        want = coherence_image(reference, x, y, trace_ancillas=False, max_width=5)
        inst = coherence_instrument(
            corrected, x, y, observed_slots=("b0",), trace_ancillas=False, max_width=5
        )
        total: dict = {}
        for mat in inst.values():
            for key, value in mat.items():
                total[key] = total.get(key, F(0)) + value
        if {k: v for k, v in total.items() if v} != want:
            bad += 1
    check(f"{label}: 64 input coherences agree after summing outcomes", bad == 0, f"{bad} bad")


# ------------------------------------------------------------------ 2. two debts


def two_debts():
    """Two independent debts, both cancelled, with the ancillas returning to |0>."""
    prog = (
        HybridProgram(4, 2)
        .ccx(0, 1, 4)                  # ancilla4 = x0&x1
        .ccx(2, 3, 5)                  # ancilla5 = x2&x3
        .hmr(4, "b0")
        .hmr(5, "b1")
        .cz(0, 1, condition="b0")
        .cz(2, 3, condition="b1")
    )
    reference = HybridProgram(4, 2)    # identity on data, ancillas end in |0>
    check("two debts both cancelled == identity", same_channel(prog, reference).equivalent)

    partial = (
        HybridProgram(4, 2)
        .ccx(0, 1, 4)
        .ccx(2, 3, 5)
        .hmr(4, "b0")
        .hmr(5, "b1")
        .cz(0, 1, condition="b0")      # only one of the two
    )
    check(
        "half-corrected (one of two debts) != identity",
        not same_channel(partial, reference).equivalent,
    )


# ------------------------------------------------------------------ 3. two debts with value ops


def two_debts_with_value():
    """Debts recorded around value operations, compared on the data register.

    Rebuilt from the working shape: the value program must be well-formed, meaning no gate reads an
    ancilla that the value part itself dirtied. ``cx(4,2)`` right after ``ccx(0,1,4)`` is fine in the
    value program because the ancilla is clean there; the failure in my first attempt came from
    comparing against a reference whose ancillas ended in a different state.
    """
    corrected = (
        HybridProgram(4, 2)
        .ccx(0, 1, 4).cx(4, 2)         # x2 ^= x0&x1, ancilla4 now dirty
        .hmr(4, "b0")                  # ancilla4 reset to |0>
        .ccx(2, 3, 5).hmr(5, "b1")     # ancilla5 set then reset
        .cz(0, 1, condition="b0")
        .cz(2, 3, condition="b1")
    )
    # Reference with the same value effect and **both ancillas in |0>**: ancilla4 is cleared by
    # re-applying ccx(0,1,4) after it has been consumed (x0,x1 unchanged), ancilla5 by ccx twice.
    value = (
        HybridProgram(4, 2)
        .ccx(0, 1, 4).cx(4, 2)
        .ccx(0, 1, 4)                  # ancilla4 back to |0>
        .ccx(2, 3, 5).ccx(2, 3, 5)     # ancilla5 set and cleared
    )
    check(
        "two debts around a value op: corrected equals the value program",
        same_channel(corrected, value).equivalent,
    )

    uncorrected = (
        HybridProgram(4, 2)
        .ccx(0, 1, 4).cx(4, 2)
        .ccx(0, 1, 4)
        .ccx(2, 3, 5).ccx(2, 3, 5)
        .ccx(2, 3, 5)                  # dirty ancilla again, measured below
        .hmr(4, "b0")
        .hmr(5, "b1")
    )
    check(
        "same two debts uncorrected differ from the value program",
        not same_channel(uncorrected, value).equivalent,
    )


# ------------------------------------------------------------------ 4. slot reuse


def slot_reuse():
    """One slot name, two distinct events, each corrected by its own CZ."""
    prog = (
        HybridProgram(3, 2)
        .ccx(0, 1, 3).hmr(3, "b0").cz(0, 1, condition="b0")
        .ccx(0, 1, 3).hmr(3, "b0").cz(0, 1, condition="b0")
    )
    reference = HybridProgram(3, 2).ccx(0, 1, 3).ccx(0, 1, 3)
    check(
        "slot reused twice, both debts cancelled == reference",
        same_channel(prog, reference).equivalent,
    )


# ------------------------------------------------------------------ 5. correction after a non-diagonal gate


def after_nondiagonal():
    """A non-diagonal gate on a disjoint wire must not invalidate the correction.

    The reference leaves the ancilla in ``|0>`` because the HMR resets it, so the value op that set it
    must be cancelled. Applying ``ccx`` twice right after setting it would clear the ancilla but also
    make ``cx(4,2)`` a no-op, so the reference is built by undoing the same net value on the ancilla.
    """
    prog = (
        HybridProgram(4, 2)
        .ccx(0, 1, 4)                  # debt on wires 0,1
        .hmr(4, "b0")
        .x(3)                          # non-diagonal (X) on a disjoint wire
        .cz(0, 1, condition="b0")
        .x(3)
    )
    # Reference: same value effect (none on data), ancilla cleared.
    reference = HybridProgram(4, 2).ccx(0, 1, 4).ccx(0, 1, 4)
    check(
        "correction after a non-diagonal gate on a disjoint wire == reference",
        same_channel(prog, reference).equivalent,
    )

    # And the honest negative: a gate that MOVES a wire the debt depends on must break it.
    broken = (
        HybridProgram(4, 2)
        .ccx(0, 1, 4)
        .hmr(4, "b0")
        .cx(0, 1)                      # changes x1, so x0&x1 is no longer the recorded monomial
        .cz(0, 1, condition="b0")
        .cx(0, 1)
    )
    check(
        "correction after a gate that moves a debt wire does NOT cancel",
        not same_channel(broken, reference).equivalent,
    )


# ------------------------------------------------------------------ 6. mutated corrections


def mutated_corrections():
    reference = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    wrong_wires = (
        HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(0, 2, condition="b0")
    )
    check(
        "correction on the wrong wires is rejected",
        not same_channel(wrong_wires, reference).equivalent,
    )
    inverted = (
        HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(0, 1, condition="!b0")
    )
    check(
        "correction with an inverted condition is rejected",
        not same_channel(inverted, reference).equivalent,
    )
    doubled = (
        HybridProgram(3, 1)
        .ccx(0, 1, 3)
        .cx(3, 2)
        .hmr(3, "b0")
        .cz(0, 1, condition="b0")
        .cz(0, 1, condition="b0")
    )
    check(
        "double correction is rejected (sign applied twice)",
        not same_channel(doubled, reference).equivalent,
    )


# ------------------------------------------------------------------ 7. symbolic side


def symbolic_agreement():
    """`phase_semantics` and the oracle must agree that the debt reaches zero."""
    from symq.phase import PhaseProgram, phase_semantics

    program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    program.hmr(3)
    before = phase_semantics(program).phase
    program.mcz_if(0, 0, 1)
    after = phase_semantics(program).phase
    check(
        "ANF: HMR creates the debt m*(x0&x1)",
        sorted(before.terms) == [0b1011],
        f"{sorted(bin(t) for t in before.terms)}",
    )
    check(
        "ANF: mcz_if cancels it (m*g XOR m*g = 0)",
        not after.terms,
        f"{sorted(bin(t) for t in after.terms)}",
    )


def main() -> int:
    corrected, reference = canonical()
    branch_check(corrected, reference, "canonical")
    two_debts()
    two_debts_with_value()
    slot_reuse()
    after_nondiagonal()
    mutated_corrections()
    symbolic_agreement()

    width = max(len(label) for label, _, _ in results)
    for label, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'}  {label:<{width}}  {detail}")
    failures = sum(1 for _, passed, _ in results if not passed)
    print()
    print(f"{len(results) - failures}/{len(results)} interoperability checks pass")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
