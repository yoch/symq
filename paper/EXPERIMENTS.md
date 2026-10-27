# Experiments E1–E5 (issue #18)

Every number here comes from a sealed result directory under `benchmarks/results/` (checked
against its `SHA256SUMS`); the paper's tables, figure and macros are generated from the same
files by `python paper/tools/make_tables.py`. Nothing is copied by hand into LaTeX.
Items marked **PENDING** are expected results, not results.

## Runs

| run | directory | commit | status |
|---|---|---|---|
| R-QCEC | `20261027T150621Z_23469829a0dc_matched-qcec` | `2346982` | sealed, 684 cells, exit 0 |
| R-BLIND | `20261027T150621Z_23469829a0dc_matched-blind` | `2346982` | **PENDING**: running (1080 cells) when this file was written |
| R-ORDER | `20261027T153026Z_e71c7e0fc8a2_variable-order-qcec` | `e71c7e0` | sealed, 133 cells |
| R-ORDER-BLIND | `20261027T153137Z_e71c7e0fc8a2_variable-order-blind` | `e71c7e0` | sealed, 210 cells |

Common protocol (from `environment.json`): CPython 3.12.3; native extension SHA-256
`2e3f67910a34…` built by GCC 13.3.0 with `-O3` (the `compiler` field of the R-QCEC/R-BLIND
records says clang 18: it is the output of `cc --version`, not the compiler that built the
binary; R-ORDER records the `.comment` section of the binary instead); passagemath-brial
10.8.13; dd 0.6.0 (CUDD 3.0.0); mqt.qcec 3.11.0 with only the alternating checker;
4-vCPU Intel Xeon VM, Linux 6.12; one fresh worker per cell pinned to one CPU; 1 warmup, then
the median of 7 runs (3 if a run exceeds 1 s, 1 if it exceeds 10 s); 120 s per cell;
family-wise monotone censoring after a timeout; extraction of explicit monomials budgeted to
2·10⁶ terms and 30 s.

Modes: `<engine>/algebra` (symq's `Algebra` driver), `<engine>/loop` (the same minimal
Python loop for every engine), `<engine>/loop-sorted` (factors sorted by monomial count),
`zdd-native/fused` (symq's C gate loop, sorts factors), `qcec`. Engines: `zdd-native`,
`zdd-python`, `sparse`, `polybori`, `cudd-bdd` (dynamic reordering), `cudd-bdd-static`.

Regimes: *cold* — fresh manager per run (PolyBoRi: fresh ring with fresh variable names,
because SageMath caches `BooleanPolynomialRing` by its arguments); *warm* — one manager reused
after a filling run (skipped when a cold run exceeds 10 s).

## E1 — Ablation (R-QCEC, cold compute, paired geometric mean, 95% bootstrap CI, wins/19)

| change (candidate vs baseline) | simulate | equiv | nonequiv | warm simulate |
|---|---|---|---|---|
| C core vs Python ZDD, same `Algebra` driver | 4.92 [4.37, 5.56] 19/19 | 4.16 [3.33, 5.40] 19/19 | 3.91 [3.12, 4.76] 18/19 | 1.23 [1.20, 1.25] |
| minimal loop vs `Algebra` driver (native) | 2.18 [1.99, 2.37] 19/19 | 2.13 [1.84, 2.49] 19/19 | 2.47 [2.12, 3.01] 19/19 | 3.34 [3.17, 3.53] |
| sorted vs unsorted factors (native loop) | **0.85** [0.81, 0.90] 0/19 | 0.89 [0.83, 0.95] 2/19 | 0.91 [0.88, 0.95] 3/19 | 0.78 |
| fused C loop vs sorted Python loop | 1.14 [1.03, 1.27] 13/19 | 1.13 [1.05, 1.21] 17/19 | 1.10 [1.02, 1.19] 15/19 | 1.31 |
| fused C loop vs unsorted Python loop (recomputed from raw rows by `make_tables.py`) | **0.97** [0.89, 1.06] 9/19 | 1.01 [0.95, 1.07] 10/19 | 1.01 [0.93, 1.09] 8/19 | — |
| fused C loop vs Python ZDD + `Algebra` (total) | see `tables/tab_ablation.tex` | | | |

Reading: the C core is the gain under cold caches; with warm caches, when nearly every
operation hits the cache, symq's `Algebra` layer dominates. Sorting factors by monomial count
hurts on this corpus. Fusion does not pay once sorting is accounted for. Not ablated:
memoisation (the cache cannot be disabled without changing the engine) and the
three-product vs two-product recursion (measured earlier with the Python ZDD, run
`d5427d4`, `docs/research/BENCHMARK_FINDINGS.md`: up to 238 615 vs 1 436 nodes on `rd84_313`
under the reversed order).

Pre-registered H2 ("fused faster than the same engine driven gate by gate") is evaluated on
R-BLIND; on R-QCEC the answer is **no** against the unsorted loop.

## E2 — Matched baselines (R-QCEC, cold compute)

| symq native vs | simulate | equiv | nonequiv | warm simulate |
|---|---|---|---|---|
| PolyBoRi, same minimal loop | 4.16 [3.68, 4.67] 19/19 | 2.98 [2.59, 3.42] 19/19 | 3.28 [2.97, 3.61] 19/19 | 2.11 [2.03, 2.19] |
| PolyBoRi, best of its 3 drivers, vs symq fused | 4.01 [3.67, 4.37] 19/19 | 2.98 [2.59, 3.36] 19/19 | 3.31 [3.12, 3.50] 19/19 | 2.14 |
| CUDD BDD (reordering), same loop | 3.86 [3.08, 5.18] 19/19 | 2.62 [2.16, 3.17] 18/19 | 3.33 [2.77, 4.00] 19/19 | 2.46 |
| CUDD BDD (static order), same loop | 3.54 [2.99, 4.24] 19/19 | 2.58 [2.11, 3.12] 18/19 | 3.21 [2.77, 3.73] 19/19 | — |
| MQT QCEC alternating checker (fused symq, both simulations + comparison) | n/a | 50.5 [30.8, 84.8] 19/19 | 65.0 [44.8, 93.4] 19/19 | — |

Setup (median over circuits, ms): native manager 0.010; fresh PolyBoRi ring 4.108; CUDD
manager 2.659 (`tables/tab_setup.tex`). End-to-end ratios are dominated by these fixed costs
and are not headlined.

Not done, and stated as threats: PolyBoRi or CUDD driven from C/C++; tuned variable orders;
QCEC's default portfolio (simulation + ZX), which may be faster but is not always a proof.

## E3 — Blind corpus (R-BLIND)

Corpus frozen in `c3b0e9a` (30 generated circuits: Cuccaro adders, controlled adders,
shift-and-add multipliers, incrementers, seeded random MCX circuits; `PREREGISTRATION.md`,
hypotheses H1–H4, amendment 1 before any inspected measurement).

**PENDING**: H1 (matched driver, native vs PolyBoRi > 1), H2 (fused > per-gate), H3
(exactness), H4 (multipliers blow up for monomial tools faster than for BDDs). Tables
`tab_status.tex` and `tab_families.tex` are generated from R-BLIND once sealed; until then the
paper prints a red PENDING marker instead of any blind number.

## E4 — Robustness

- **Variable order (R-ORDER, QCEC corpus).** 7 orders × 19 circuits, all completed; output
  fingerprints identical across orders on 19/19 circuits; node spread geometric mean 1.79,
  maximum 146 (`c2_181`: 443 nodes reversed, 2 232 identity, 64 753 for one random order);
  the default order is within 1.26× of the best order in time (geometric mean), best on 6/19,
  and 5.1× slower than the best on `c2_181`.
- **Variable order (R-ORDER-BLIND, `20261027T153137Z_e71c7e0fc8a2_variable-order-blind`,
  25 s and 2·10⁷ nodes per cell, censoring per (family, order)).** 124/210 cells ok; all 7
  orders complete on 15/30 circuits; 0 disagreements (fingerprints on 15 circuits, monomial
  counts on all completed cells). The identity order is never the best (0/15), 3.56× slower
  than the best order in geometric mean, 164× on `adder_16` (197 200 vs 2 330 nodes). On
  `adder_24`, `adder_31`, `cadder_24`, `cadder_30` the identity order exhausts the budget (or
  is censored) while random orders complete. `mult_5` completes under all orders (best:
  reversed, 627 655 nodes); `mult_6` fails under all orders; `rand_16_100_2` completes and
  `rand_16_100_4` fails under all orders (larger circuits of both families censored).
  **Consequence:** in the matched blind run, failures of the monomial engines on adders must
  be read as default-order failures, not representation limits.
- **Failures and limits.** R-QCEC: no timeout, no error; QCEC `simulate` is not applicable.
  R-BLIND: **PENDING** (timeouts and censoring by family and mode, `tab_status.tex`).
- **Memory.** `rss_growth_kib` per cell is recorded in both runs (includes native heaps); the
  native engine never frees nodes during a verification (no GC).
- **Defects found while preparing the paper.** Per-node monomial counts are `int64` and
  overflow silently beyond 2⁶³−1 (possible at width ≥ 63). Fixed by saturation plus an
  `OverflowError` when a saturated polynomial is materialised, with an exact test at
  2⁶²+1 and a test that fails on the old code, and an ASan/UBSan CI job: PR #23 (open, not
  in the measured binary). Largest output measured here: 8 520 monomials (R-QCEC).

## E5 — Exactness

- R-QCEC: 57 (circuit, workload) groups, output fingerprints compared across the 11
  symbolic modes: 0 disagreements; 0 wrong verdicts; every counterexample re-executed
  concretely; QCEC's 38 conclusive verdicts all agree.
- R-ORDER: identical output monomials under 7 variable orders on 19/19 circuits;
  R-ORDER-BLIND: on 15/15 circuits with fingerprints, and identical monomial counts on every
  completed cell.
- Test suite at the measured commit: 2 490 tests, 2 489 passed and 1 deselected locally
  (the deselected test checks the seal of R-BLIND, which was still being written); it
  includes exhaustive comparison with concrete execution on seeded random circuits, node-for-
  node agreement between the native and Python ZDDs, and mutation tests of the algebra.
- R-BLIND: **PENDING** (H3).

These are differential and exhaustive-small-case tests, not proofs. The proofs on paper are
in `FORMAL_MODEL.md`; nothing is machine-checked.
