# Pilots actually executed -- 28 October 2026

Every number below comes from a run in `prototype/`, whose JSON output is collected in
`RESULTS.json`. Machine: 4-vCPU Intel Xeon VM, Linux 6.12, CPython 3.12.3, one worker pinned to
one core. Budgets: 30 s and 2-4 M ZDD nodes per cell; a cell that hits a budget is reported as
`budget`, never as a time.

## A. Factored phase: size and acceptance

**A1 -- is the factored form smaller?** (`prototype/pilot_a.py`, `prototype/pilot_scale.py`)

| measurements | factored terms | expanded terms | ratio |
|---:|---:|---:|---:|
| 2 | 2 | 2 | 1.00 |
| 4 | 4 | 4 | 1.00 |
| 8 | 8 | 8 | 1.00 |
| 16 | 16 | 16 | 1.00 |
| 32 | 32 | 32 | 1.00 |
| 64 | 64 | 64 | 1.00 |

**H-A is falsified.** The expanded ANF is exactly as small as the factored form, on every
instance, up to 64 independent measurements. The reason is structural: in the accepted fragment
the phase is *affine* in the outcome variables, so no monomial ever carries two `m` variables and
no cross term is ever created. The `2^M` blow-up that the factorisation was meant to avoid does
not exist here. A first version of this pilot disagreed (it built `g_j` as constants and measured
a degenerate case); the corrected version above is what `RESULTS.json` holds.

**A2 -- does the channel criterion accept more?** (`prototype/pilot_a.py`)

300 random programs of 2-7 instructions, compared against the identity of the same width:

| measure | count |
|---|---:|
| strict criterion (O1 + O2 + equality) accepts | 36 |
| channel criterion accepts | 40 |
| accepted by both | 36 |
| accepted only by the channel criterion | 4 |
| of those, confirmed by the density-matrix oracle | 4 / 4 |
| disagreements between the criterion and the oracle | 0 |

So the widening is real and sound, and it is small: 4 programs in 300.

**A2b -- do the extra acceptances matter?** (`prototype/pilot_a2.py`)

The canonical measurement-based uncomputation forms, at 1, 2 and 3 ancillas, with the standard
data-wire correction, an outcome-only correction, and no correction:

| program | O2 violations | channel-equivalent to the reference |
|---|---:|---:|
| `and_chain_1_data` | 0 | 0 |
| `and_chain_1_outcome` | 1 | 0 |
| `and_chain_1_none` | 1 | 0 |
| `and_chain_2_data` | 0 | 1 |
| `and_chain_2_outcome` | 1 | 0 |
| `and_chain_3_data` | 0 | 0 |
| ... (`PILOT_A2.json` has all) | | |

**Every correctly corrected form already satisfies O2.** The programs the channel criterion
additionally accepts are ones with outcome-only phases -- sound, but not what a compiler emits.
The widening is therefore a *correctness* improvement with no demonstrated practical instance.

## B. Equivalence by simulating the composed circuit

**B1 -- dense random circuits** (`prototype/pilot_b.py`)

Both methods blow up on dense random circuits beyond 12 wires; 9 of 12 instances hit the node
budget in both arms. This terrain cannot separate them and is not used further.

**B2 -- structured QCEC circuits** (`prototype/pilot_b2.py`)

Twelve instances (6 circuits x {rewritten variant, one inserted gate}) that both methods decided,
on widths up to 20 and gate counts up to ~400:

| instance | separate nodes | miter nodes | agree |
|---|---:|---:|---|
| `5xp1_194_equiv` | 580 | 580 | yes |
| `5xp1_194_nonequiv` | 432 | 471 | yes |
| `add6_196_equiv` | 3 624 | 3 624 | yes |
| `add6_196_nonequiv` | 3 908 | 2 381 | yes |
| `alu1_198_equiv` | 190 | 190 | yes |
| `alu1_198_nonequiv` | 143 | 137 | yes |
| `dk27_225_equiv` | 106 | 106 | yes |
| `dk27_225_nonequiv` | 114 | 121 | yes |
| `example2_231_equiv` | 2 447 | 2 447 | yes |
| `example2_231_nonequiv` | 2 149 | 2 045 | yes |
| `mlp4_245_equiv` | 1 638 | 1 638 | yes |
| `mlp4_245_nonequiv` | 1 516 | 880 | yes |

**Reading.** For *equivalent* pairs the two methods are identical, node for node -- expected,
because the composed circuit is the identity and its simulation allocates nothing extra. For
*nonequivalent* pairs the miter is sometimes cheaper (`mlp4`: 1 516 → 880 nodes, -42 %;
`add6`: 3 908 → 2 381, -39 %) and sometimes dearer (`5xp1`, `dk27`). The mechanism is real but the
effect is not robust across circuits, and the instances are small enough that both arms finish in
milliseconds. Geometric mean over the six non-equivalent instances: 0.848 (ratios 0.58, 0.61,
0.95, 0.96, 1.06, 1.09). This is not, on its own, a paper.

**Also measured but not adopted.** A prototype criterion for comparing the two outputs over the
*pair* space (ZDD over `2n` variables) was written and discarded: it requires `2n <= 64` pair
variables, so it caps the circuits at half the width of the direct comparison. That is a
regression, not a contribution, and no results are reported for it.

## C. Memory: are the nodes dead?

**C1 -- live vs dead** (`prototype/pilot_c.py`), dense random circuits, outputs of one
simulation treated as the live roots:

| width | gates | nodes created | reachable | dead (upper bound) | dead fraction |
|---:|---:|---:|---:|---:|---:|
| 14 | 200 | 134 186 | 501 | 133 685 | 99.6 % |
| 16 | 300 | 2 190 632 | 4 179 | 2 186 453 | 99.8 % |
| 18 | 400 | budget (3 M nodes) | -- | -- | -- |

**H-C first prediction confirmed.** The live roots hold well under 1 % of the table. The
`dead` figure is an upper bound (shared nodes are counted once per root), so the true dead
fraction is at least as large.

**C2 -- what would a rebuild cost?** (`prototype/pilot_c2.py`), rebuild implemented the most
expensive possible way: expand every live root to explicit monomials, re-import into a fresh
manager.

| width | gates | simulation | rebuild | ratio |
|---:|---:|---:|---:|---:|
| 12 | 150 | 0.002 s | 0.002 s | 0.72 |
| 14 | 200 | 0.008 s | 0.004 s | 0.44 |
| 16 | 300 | budget | -- | -- |

**H-C second prediction holds** on the two instances that completed: the naive rebuild costs
less than the simulation it interrupts, at 44-72 % of it. A collector that only re-creates live
roots -- cheaper than expanding to monomials -- can therefore be affordable. It is still
engineering (CUDD has one), and the C2 measurement is the *cost*, not the *benefit*: the memory
freed was not measured, because that needs instrumentation inside the C allocator.

## What was not run

* Any native C change: no collector, no multiword width, no reordering policy. All pilots run
  against the production engine at `aaff35f` plus prototypes in this directory.
* A corpus experiment beyond 12 structured instances and 3 dense random circuits; the stop
  criteria in `HYPOTHESES.md` fired first.
* Any comparison against ABC, SAT sweeping or Irene on the same instances. That comparison is
  the one a publication would need, and it is not done.
