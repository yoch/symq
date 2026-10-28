# Hypotheses and stop criteria -- 28 October 2026

Each hypothesis names a mechanism, a falsifiable prediction, the experiment that tests it, and
the result that would make me stop. The stop criteria were written before the runs; the results
are in `PILOT_A.md`, `PILOT_B.md`, `PILOT_C.md`.

## H-A: a factored phase is smaller than the expanded ANF

**Mechanism.** Keep `phi0(x)` and `g_j(x)` separately instead of one polynomial in
`data + M` variables. Storing `M` coefficients of a few monomials each should cost less than
`2^M` cross terms.

**Prediction.** `expand_terms / factored_terms` grows with `M`.

**Falsified if** the ratio stays at 1 for all `M`. Then the expansion is *already* factored --
which happens when `phi` is affine in `m` -- and the representation buys nothing.

**Stop criterion.** Ratio 1 on every instance ⇒ report as a negative and do not build the
storage layer.

## H-A2: the channel criterion accepts programs O2 rejects, and those programs matter

**Mechanism.** O2 requires the phase to be independent of the outcomes. The channel is
insensitive to outcome-only phases, so the channel criterion should accept strictly more.

**Prediction.** On random programs, `channel_accepts > strict_accepts`; on the canonical
measurement-based-uncomputation forms that an HMR compiler emits, the two agree.

**Falsified if** the criterion accepts nothing more (then it is vacuous), or if it accepts the
canonical forms that O2 rejects *and* those forms are wrong (then the criterion is unsound --
excluded by the oracle).

**Stop criterion.** If the extra acceptances occur only on random programs with no compiler
counterpart, the widening is a curiosity, not a contribution.

## H-B: simulating the composed circuit beats simulating both

**Mechanism.** In the ANF setting, `L ; R^{-1}` keeps the intermediate polynomials on the
*difference*. Separate simulation materialises `f_L` and `f_R` in full; the composition cancels
the common part as it goes.

**Prediction.** On instances with a long common prefix and a short divergence, the composed run
uses materially fewer nodes.

**Falsified if** the two are equal within noise on structured circuits, or if the composition
only helps when the circuits are nearly identical (a case a SAT checker also solves instantly).

**Stop criterion.** A gain confined to instances where the two circuits share a literal gate
prefix is not a contribution: that case is already trivial.

## H-C: the native unique table is dominated by dead nodes, so GC pays

**Mechanism.** No collection is performed, so every node ever created stays. If the live roots
hold a small fraction, a collector could cut memory.

**Prediction.** `reachable / nodes_created` is small (well under 50 %) after a dense simulation.

**Falsified if** the live roots dominate (then memory is structural and GC is pointless).

**Second prediction (C2).** Rebuilding costs less than the simulation it interrupts, so the
memory can be reclaimed cheaply. Implemented the most expensive possible way -- expand every
live root to monomials and re-import -- the rebuild should still be cheaper than the simulation.

**Falsified if** the rebuild costs more than the work it saves.

## Global stop rules

* No experiment is extended past its pilot budget unless the pilot showed a difference larger
  than the run-to-run noise and a mechanism that explains it.
* Every predicate that is compared must be cross-checked against an independent oracle
  (`research/innovation/2026-10-28/prototype/channel.py`), not against itself.
* A result that only survives on the corpus that produced it is not a result.
