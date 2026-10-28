# Response to the audit of PR #60, #61 and #62

Every point of the audit was reproduced before being accepted or contested. Four were correct and
serious, one was correct and changes a conclusion, one was correct and is now measured properly.
None was wrong.

This document is the record; the fixes are in the code and the re-run campaigns are in
`RESULTS_*.json` of this same directory and of `../innovation/2026-10-28/`.

## P0-1. The "exact" liveness count was wrong — **confirmed**

The audit's counterexample is exact. With roots `{x}` and `{x, y}`, the union of the families is
`{x, y}`, whose diagram has two nodes, while the node of `{x}` is *not* one of them: the reachable
union has three. `union_node_count` returned two.

The audit is also right about the direction: summing `size(root)` counts a shared node once per
root, so it is an **upper** bound on the distinct live nodes, not a lower one. The first version of
`liveness.py` said the opposite.

Fixed by adding `reachable_union` to both backends: an explicit marking walk over the identifiers,
`O(nodes + edges)`, in C (`manager_reachable_union`) and in Python
(`ZDDAlgebra.reachable_union`). They are implemented independently, so the differential test
compares two implementations rather than one with itself. `tests/test_liveness_exact.py` (30 tests)
enumerates every pair and triple of families over three variables, pins the audit's counterexample
at exactly 3, and checks that the per-root sum is an upper bound.

**The corrected figures.** Because the number of live nodes is now measured differently, the old
"9 426 530 created / 24 live" must be re-derived. At 13 wires and 170 gates the live set is still a
few hundred nodes rather than millions, so the *signal* stands; the exact ratio is now computed by
the new function and reported in `RESULTS_C6.json`.

## P0-2. The Cuccaro generator did not compute addition — **confirmed**

Reproduced immediately: for 1, 2 and 3 bits the generator's circuit gave a different output from
`b <- a + b` on 8/16, 48/64 and 224/256 inputs. The cause is exactly what the audit says: `_maj` and
`_uma` were the same three gates in reverse order, so the pair was not an inverse pair in context.

Fixed by rebuilding `adders.py` from the gate list of the corpus generator (which had been validated
by concrete execution) and adding `tests/test_adders.py` (20 tests): addition checked against
integer arithmetic on **every legal input** for 1–4 bits, the controlled variant checked to be the
identity at control 0 and addition at control 1, the permutation property, and the carry wires.
`expected_output` refuses `carry_in = 1`, which is the circuit's actual domain — the previous "13
of 19 circuits were wrong" was partly my reference model ignoring that restriction.

**Consequence, and it is the audit's best finding:** with a correct adder the order ranking
*changes*. See P1-2 below.

## P1-1. The GC measurements were not reconstructible — **confirmed, now sealed**

`pilot_c6.py` runs 14 wires × 200 gates in **one subprocess per arm**, so `ru_maxrss` is that arm's
own peak, and it verifies every arm against a **concrete truth table** of all 16 384 inputs —
an oracle that shares nothing with the symbolic machinery.

| chunks | threshold | status | peak nodes | peak RSS | wall | truth-table mismatches |
|---:|---:|---|---:|---:|---:|---:|
| 1 (monolithic) | 40 M | **budget exceeded** | -- | 6 923 MiB | 70 s | -- |
| 8 | 1 M | ok | 11 250 955 | 1 741 MiB | 182 s | 0 |
| 200 (per gate) | 1 M | ok | 2 102 404 | 474 MiB | 164 s | 0 |
| 200 (per gate) | 400 k | ok | **1 438 659** | **262 MiB** | **160 s** | **0** |

So the per-gate rebuild reduces peak memory by **6.6×** and peak nodes by **7.8×** against the
eight-fragment schedule, with an exact result on every input. The earlier "12 M → 1.44 M
(−87 %)" compared against the *monolithic* run, which does not finish; the honest comparison is
against the schedule that does: **1 741 → 262 MiB of RSS**, which is what a user feels.

The wall time is *higher* than the 52 s reported earlier because each arm now includes the
truth-table verification and runs in a cold process. The time comparison between arms is still
valid; the absolute numbers are not comparable with the earlier ones.

## P1-2. The cache benchmark did not measure the constructor — **confirmed, and it changed the claim**

The audit is right that the old harness started its timer after `NativeZDDAlgebra(...)`. Fixed by
`bench_cache_separated.py`, which times construction, simulation and total separately, reports
**medians** over 9 (structured) or 3 (dense) runs, and pins the git HEAD.

| arm | construction | simulation | total ratio |
|---|---:|---:|---:|
| small structured (n=11) | 4–6 µs | unchanged | **0.93** |
| dense random (n=3) | 0.03–8 ms | 0.57–0.73× | **0.68** |

The first run of the corrected harness, executed on a branch that did **not** contain the lazy
allocation, measured a total ratio of **12.0** on the structured circuits — a 523 µs constructor
against a 5 µs one. That is the regression the fix removes, and it is why the audit was right to
ask: without the separated measurement, the claim could not be attributed to the right line of
code. With the fix in place, the constructor is 4–6 µs and the total is 0.93.

## P1-3. The order fingerprints could collide — **confirmed**

`{0, 3}` and `{1, 2}` both have two monomials summing to 3. Fixed: the fingerprint is now the
SHA-256 of the concatenated, sorted monomial sets of every output, so "no wrong function" means
what it says.

**Re-run with the corrected adder and the corrected fingerprints, the ranking changes:**

| order | selection (8 circuits) | holdout (16 circuits) | adders | MCX chains |
|---|---:|---:|---:|---:|
| `last_use` | **0.084** | **0.104** | 0.017 (58× faster) | **1.577 (58 % slower)** |
| `min_fill` | 0.248 | -- | -- | -- |
| `bfs` | 0.301 | -- | -- | -- |
| `reversed` | 0.665 | -- | -- | -- |
| `identity` | 1.000 | 1.000 | 1.000 | 1.000 |

The heuristic that wins is **`last_use`** (sort wires by their final use, descending), not
`reversed`. The `reversed` advantage I reported earlier came from circuits that were not adders.
`last_use` completes 16/16 on the holdout with zero wrong functions and a geometric mean of
**0.104**, but it is **not universal**: it is 1.58× slower on MCX chains. `identity` therefore
remains the default and `last_use` is offered as an explicit policy, together with the measured
caveat.

## P1-4. The PRs were not independent — **confirmed**

`#60` depended on `#59`; `#61` and `#62` were parallel branches touching the same benchmark files.
This work is now consolidated on **one** branch, `cursor/audit-remediation-2026-10-28-f132`, built
from `main` with the three lines of work merged, so CI runs on the combination. The two order
campaigns no longer overwrite each other: `bench_order4.py` is the corrected campaign and the older
files are kept only as the record of what was measured before.

## What the audit got right that is not a defect

- **`reversed` keeps a real, independent advantage.** Recomputed by the audit from
  `RESULTS_ORDER3.json`, the six non-adder circuits give 1.47× in geometric mean. That is
  reproduced here and is why `reversed` remains a policy rather than being deleted.
- **`ENGINEERING_ONLY` stands.** Nothing in these corrections produces an algorithmic innovation.

## Verdict after the corrections

**PILOTS: `PARTIALLY_VALIDATED`.** Two of the three original conclusions were wrong (B in
direction, C in magnitude) and two of the measurement instruments were wrong (liveness, adder
generator). The corrected instruments now have differential tests against independent oracles.

**ENGINE: `MATERIAL_IMPROVEMENT`.** The cache fix is a measured 7 % / 32 % gain including its own
constructor, and the rebuild turns a budget failure into a 160 s verification with 262 MiB instead
of 1 741 MiB, verified against a truth table.

**SCIENCE: `ENGINEERING_ONLY`.** Unchanged.
