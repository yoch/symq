# Decision -- 28 October 2026

> **Superseded on 28 October 2026 (same day) by the corrected pilots.**
> `PILOT_CORRECTIONS.md` lists eleven defects found in the measurements below; the corrected
> verdicts are in `DECISION_CORRECTED.md`. Two of the three conclusions changed materially:
> pilot B is **worse** than reported here (the miter is slower in the regime it was designed for,
> not "unstable"), and pilot C's effect is **larger** (-87 % peak nodes, and it turns a budget
> failure into a completion). Pilot A's criterion survived but is narrower than stated. The text
> below is kept as the record of what was concluded before the defects were found.

**Verdict: `ENGINEERING_IMPROVEMENT_ONLY`.**

No pilot produced a mechanism that is both new with respect to the sources in
`STATE_OF_THE_ART.md` and demonstrably useful on a real circuit. One pilot produced a new
*criterion* (`PILOT_A.md`, A2) with no instance that needs it; one produced a real but
unstable effect (`PILOT_B.md`); one produced a clean engineering justification
(`PILOT_C.md`).

## Category per pilot

| pilot | category | why |
|---|---|---|
| A1, factored phase | **III -- negative** | The expansion is already factored: ratio 1.00 at every `M` up to 64, because the fragment makes the phase affine in the outcomes. The `2^M` problem the factorisation was meant to solve does not occur. |
| A2, channel criterion | **I -- potential, unexercised** | A decision procedure that is strictly weaker in its obligations than O2 and still sound (4/4 extra acceptances confirmed by the density-matrix oracle, 0 disagreements in 400 random pairs). But every canonically corrected HMR program already passes O2, so no real program needs it. |
| B, composed-circuit simulation | **II -- engineering** | The miter is prior art (Wille 2009, ABC). The ANF-specific claim -- intermediates stay proportional to the difference -- shows up as -39 % and -42 % nodes on two instances, no change on two, and +6-9 % on two; geometric mean 0.85 over six non-equivalent pairs. Not robust. |
| C, GC | **II -- engineering** | 99.6-99.8 % of the unique table is dead, and a maximally naive rebuild costs 44-72 % of the simulation it interrupts. That justifies building a collector, and a collector is what CUDD has had for thirty years. |

## Why A2 is not promoted to a paper

The criterion is genuinely new *as a decision procedure for this fragment*: I did not find, in
PolyBoRi/BRiAl, CUDD, QCEC, ABC, Irene, QuPRS or the phased outcome-complete simulation work, a
statement that channel equality of measurement-assisted programs can be decided by two
Boolean-function comparisons over pair variables with no outcome enumeration. But:

1. **The problem it solves does not arise in practice.** Every corrected measurement-based
   uncomputation gadget passes O2 already (`PILOT_A.md`, A2b). The extra acceptances are random
   programs with outcome-only phases.
2. **It is not asymptotically better on any measured instance.** The expanded phase is affine in
   `m`, so the cost of the strict path never grows with `M` in this fragment either.
3. **Its natural comparison is not done.** Claiming an advantage over Irene or over phased
   outcome-complete simulation requires running those tools on the same instances. Neither is
   installed here, and their benchmarks are not the reversible fragment.

That combination is the definition of a result that should be written down and not published.

## What would change the verdict

A single family of *real*, publicly available measurement-assisted programs where the strict O2
criterion rejects the program and the channel criterion accepts it, and where the reason is a
correction an actual compiler emits. `NEXT_STEPS.md` names the concrete search.

## Engineering work this justifies

1. A collector over the native unique table, with the root set defined by the checker (wire
   values of both circuits, the witness, the extracted polynomials) and rebuild-based, since the
   rebuild is cheap relative to the simulation. `pilot_c2.py` is its cost model.
2. The composed-circuit path as an *optional* equivalence strategy, selected only when the two
   circuits share a long gate prefix -- the only measured regime where it helps. Not as a
   replacement: on equivalent pairs it is identical, and on some non-equivalent pairs it is worse.
3. Nothing from A1: the storage layer would add code and save nothing.
