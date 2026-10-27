# Experiments E1–E5 (issue #18)

Every number here comes from a sealed result directory under `benchmarks/results/` (checked
against its `SHA256SUMS`); the paper's tables, figure and macros are generated from the same
files by `python paper/tools/make_tables.py`. Nothing is copied by hand into LaTeX.

## Runs

| run | directory | commit | content |
|---|---|---|---|
| R-QCEC | `20261027T175456Z_33515a36080b_matched-qcec` | `33515a3` | QCEC corpus, corrected harness, 684 cells |
| R-BLIND | `20261027T150621Z_23469829a0dc_matched-blind-merged` | `2346982` + re-runs | blind corpus, 1 080 cells, derived (see below) |
| R-BIND | `20261027T175845Z_33515a36080b_binding` | `33515a3` | per-call cost of each Python binding |
| R-ORDER | `20261027T175849Z_33515a36080b_variable-order-qcec` | `33515a3` | 7 orders × 19 circuits |
| R-ORDER-BLIND | `20261027T175949Z_33515a36080b_variable-order-blind` | `33515a3` | 7 orders × 30 circuits |
| superseded | `20261027T150621Z_23469829a0dc_matched-qcec`, `…e71c7e0fc8a2_variable-order-*` | `2346982`, `e71c7e0` | first harness; kept sealed |

R-BLIND is built by `benchmarks/merge_runs.py` from the raw campaign
(`benchmarks/results-raw/20261027T150621Z_23469829a0dc_matched-blind`, 15:06–17:50 UTC) and
sealed re-runs in `benchmarks/results-raw/`; `merge.json` lists every substituted cell:

- 16 cells around a ten-second window (16:51:19–16:51:29 UTC) in which a git operation
  replaced the source tree: 10 failed at start-up, 4 CUDD cells ran on the replaced code, 2
  neighbours; re-run with the measured code.
- 16 cells killed by the memory cgroup (≈15 GiB shared by all processes; kernel records in
  `paper/evidence/oom_kills.md`), re-run one worker at a time with no other benchmark: 1 ok,
  6 timeouts, 2 censored, 7 killed again (6 `sparse/algebra`, 1 `zdd-native/loop-sorted`).
- every `zdd-native/fused` cell, re-measured with the corrected harness together with
  `zdd-native/loop` (and `loop-sorted` for *equiv*/*nonequiv*):
  `…181221Z_33515a36080b_matched-blind-fused` (*simulate*) and
  `…220741Z_8d829fae5ff7_matched-blind-fused-eq` (*equiv*, *nonequiv*). Six fused workers
  killed there (return code −9) were not re-run.
- remaining rows of SIGKILLed workers are labelled `killed`; any other error aborts the merge.

Common protocol: CPython 3.12.3; native extension SHA-256 `2e3f67910a34…` (GCC 13.3.0,
`-O3`) in every run; passagemath-brial 10.8.13; dd 0.6.0 (CUDD 3.0.0); mqt.qcec 3.11.0 with
only the alternating checker; 4-vCPU Intel Xeon VM, Linux 6.12; one fresh worker per cell
pinned to one CPU (CPUs 2 and 3); 1 warmup, then the median of 7 runs (3 if a run exceeds
1 s, 1 if it exceeds 10 s); 120 s per cell; monotone censoring after a timeout per family
(random circuits: per gate and control count in the corrected harness); extraction of
explicit monomials budgeted to 2·10⁶ terms and 30 s.

Corrected harness (`33515a3`): the fused loop receives control/offset/target arrays built
before the timer, as the Python loops receive their gate list (the first harness built them,
and gathered statistics, inside the timed phase); worker return codes are recorded; random
circuits are censored per (gates, controls); per-call binding costs are calibrated.

## E1 — Ablation (R-QCEC, cold compute, paired geometric mean, 95% bootstrap CI, wins/19)

| change (candidate vs baseline) | simulate | equiv | nonequiv |
|---|---|---|---|
| C core vs Python ZDD, same `Algebra` driver | 5.41 [4.48, 6.73] 19/19 | 4.19 [3.53, 5.09] | 4.29 [3.61, 5.26] |
| minimal loop vs `Algebra` driver (native) | 2.13 [1.94, 2.33] 19/19 | 2.11 [1.85, 2.39] | 2.40 [2.18, 2.61] |
| sorted vs unsorted factors (native loop) | **0.90** [0.87, 0.93] 2/19 | 0.89 [0.87, 0.92] | 0.88 [0.86, 0.90] |
| fused C loop vs sorted Python loop | 2.28 [2.02, 2.54] 19/19 | 2.30 [1.85, 2.83] | 2.67 [2.30, 3.07] |
| fused C loop vs unsorted Python loop | **2.05** [1.83, 2.26] 19/19 | 2.05 | 2.34 |

Warm caches: C core 1.21×. Reading: the C core is the gain under cold caches; symq's
`Algebra` layer costs ≈2×; sorting factors by monomial count hurts; fusing the loop gains
≈2×. The first harness reported 0.97× for fused vs unsorted loop: a harness artifact.

## E2 — Matched baselines (R-QCEC, cold compute)

| symq native vs | simulate | equiv | nonequiv |
|---|---|---|---|
| PolyBoRi, same minimal loop | 3.94 [3.49, 4.41] 19/19 | 3.00 [2.61, 3.42] | 3.46 [3.12, 3.80] |
| CUDD BDD (reordering), same loop | 3.48 [2.95, 4.10] 19/19 | 2.74 [2.27, 3.26] | 3.15 [2.72, 3.64] |
| CUDD BDD (static order), same loop | 3.38 [2.87, 3.96] 19/19 | 2.71 [2.22, 3.26] | 3.10 [2.69, 3.58] |
| MQT QCEC alternating checker (fused symq, end to end) | n/a | 61.8 [36.1, 105.9] | 63.6 [42.7, 90.9] |

Warm simulate vs PolyBoRi: 2.11× [2.03, …]. Setup (median, ms): native 0.009; PolyBoRi ring
4.387; CUDD manager 3.008.

**Bindings (R-BIND).** One product / one sum of two variables (cache hits), tight loop: native
56/50 ns, PolyBoRi 156/117 ns, CUDD 70/224 ns; empty Python call 23 ns. Bindings take a median
27 % of the native loop time, 16 % of PolyBoRi's. Subtracting calls × cost from both sides (a
bound) leaves 4.41× vs PolyBoRi and 3.86× vs CUDD on R-QCEC (blind: 3.95× and 0.79×).

Not done: PolyBoRi or CUDD driven from C/C++; tuned variable orders; QCEC's default
portfolio.

## E3 — Blind corpus (R-BLIND)

Corpus frozen in `c3b0e9a` (30 circuits: 5 Cuccaro adders, 5 controlled adders, 7
multipliers, 4 incrementers, 9 seeded random MCX circuits); hypotheses and amendment pushed
before the run (`PREREGISTRATION.md`).

- **H1** (native vs PolyBoRi, same loop, simulate): 3.47× [2.23, 5.04], 13/15 wins — supported.
- **H2** (fused vs minimal loop, corrected harness, paired within the fused runs): simulate
  1.52× [1.30, 1.80], 15/18 wins; equiv 1.68× [1.35, 2.09], 14/16; nonequiv 1.49×
  [1.27, 1.77], 17/18 — supported.
- **H3** (exactness): 70 groups, 3 fingerprint disagreements, 0 wrong verdicts, 0 invalid
  witnesses — **rejected as stated**. All three (`mult_6`, `rand_16_100_2`, `rand_16_100_4`,
  simulate) set `cudd-bdd/loop` against every other engine, `cudd-bdd-static/loop` included.
  The BDDs are right (300 random inputs on `rand_16_100_2` agree with concrete execution);
  `CuddBDDAlgebra.to_anf` memoised by node id without keeping nodes alive, and CUDD reused
  freed ids. Fixed on `main` by PR #38 with a regression test. Timings unaffected.
- **H4** (multipliers): simulate completes on 4/7 multipliers for the native loop and
  PolyBoRi (largest `mult_5`), 5/7 for CUDD with reordering (`mult_6`), 6/7 with a static
  order. Direction as expected; no test.
- **vs CUDD**: 0.69× [0.15, 2.41], 9/16 wins with reordering; 1.63× [0.45, 4.52] static.
  CUDD completes 71/90 cells, the native loop 46/90. By family (simulate, both complete):
  adders 0.25×, controlled adders 1.23×, incrementers 4.06×, multipliers 0.23×, random 0.47×
  (1 circuit). The QCEC-corpus advantage over CUDD does not carry over.

## E4 — Robustness

- **Variable order (R-ORDER).** 7 orders × 19 circuits, all complete; fingerprints identical;
  node spread geometric mean 1.79, maximum 146 (`c2_181`); identity order within 1.19× of the
  best in time (geometric mean), best on 6/19.
- **Variable order (R-ORDER-BLIND,** exploratory, 25 s and 2·10⁷ nodes per cell). 138/210
  cells ok; all orders complete on 17/30 circuits; 0 disagreements; identity never best
  (0/17), 3.13× slower than the best in geometric mean, 156× on `adder_16`. On `adder_24`,
  `adder_31`, `cadder_24`, `cadder_30` only non-identity orders complete; 9 circuits complete
  under no order. Failures of monomial engines on adders are default-order failures.
- **Memory.** Seven blind cells exhaust the 15 GiB machine on their own (`killed`); the native
  engine never frees nodes during a verification.
- **Defects found while preparing the paper**, none in the measured code path of a verdict:
  `int64` monomial counts overflow beyond 2⁶³−1 (PR #23, saturation); explicit-monomial
  import rejected every non-constant monomial at width exactly 64 (PR #37); the CUDD
  conversion defect above (PR #38). Largest output measured: 67 108 911 monomials.

## E5 — Exactness

- R-QCEC: 57 groups across the symbolic modes, 0 disagreements; 0 wrong verdicts; every
  counterexample re-executed concretely; QCEC's 38 conclusive verdicts agree.
- R-BLIND: see H3; every engine that builds ANF agrees on every group.
- R-ORDER / R-ORDER-BLIND: identical output monomials under 7 orders wherever they complete.
- Test suite at the measured commit: 2 490 tests; on current `main` 2 648 passed, 2 skipped.

These are differential and exhaustive-small-case tests, not proofs (`FORMAL_MODEL.md`).
