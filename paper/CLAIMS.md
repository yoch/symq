# Claims of paper A, their prior art and their evidence

Status of this document: draft for the author (Joshua Melka), 28 Oct 2026. It answers issue #17. Every
number is quoted from a sealed run (directory and commit given); the paper's macros are
generated from the same files by `paper/tools/make_tables.py`.

Runs used:

| id | directory under `benchmarks/results/` | commit | content |
|---|---|---|---|
| R-QCEC | `20261027T175456Z_33515a36080b_matched-qcec` | `33515a3` | matched drivers, QCEC corpus, corrected harness, 684 cells |
| R-QCEC-OLD | `20261027T150621Z_23469829a0dc_matched-qcec` | `2346982` | first matched run, superseded (fused cells biased) |
| R-BLIND | `20261027T150621Z_23469829a0dc_matched-blind-merged` | `2346982` + re-runs | blind corpus, 1080 cells, merged with isolated re-runs and corrected fused runs (`merge.json`) |
| R-BIND | `20261027T175845Z_33515a36080b_binding` | `33515a3` | per-call cost of the Python bindings |
| R-ORDER | `20261027T175849Z_33515a36080b_variable-order-qcec` | `33515a3` | 7 variable orders × 19 circuits |
| R-ORDER-BLIND | `20261027T175949Z_33515a36080b_variable-order-blind` | `33515a3` | 7 variable orders × 30 blind circuits |
| R-THREE | `20261027T125339Z_d5427d4d5204_zdd-three-product` | `d5427d4` | earlier, Python backends only (adaptive selection) |
| R-QCEC0 | `20261027T122100Z_032df732465c_qcec-full` | `032df73` | earlier, Python backends only |

`2346982` = `main@234696e` plus the benchmark harness and the frozen blind corpus; it changes
no file under `src/` (`git diff --stat 234696e 2346982 -- src/` is empty). `9b62a75` (re-runs)
changes nothing under `src/`, `benchmarks/` or `tools/` relative to it; `33515a3` corrects the
harness (fused-loop input outside the timer, return codes, censoring per gate/control count,
binding calibration) and changes no file under `src/`. All runs use the same native binary (SHA-256 `2e3f6791…`, GCC 13.3.0).

## Main thesis (one sentence, falsifiable)

> Under identical drivers and controlled caches, a small native monomial-ZDD engine computes
> the exact ANF outputs of X/CX/CCX/MCX circuits several times faster than PolyBoRi and CUDD
> on small reversible benchmark circuits, but neither its fused C loop nor its factor
> ordering contributes to that gain, and the representation fails on multipliers.

It is refuted if any of the following happens on the same machine and protocol: the paired
geometric-mean ratio against PolyBoRi or CUDD falls to ≤ 1 on the blind corpus; a native
driver for PolyBoRi (C++ API) closes the gap; any output fingerprint differs across modes or
orders; or the fused loop turns out faster than the minimal loop on another corpus.

## Matrix C1–C4

Legend for the five levels the mission asked to distinguish: **L** known in the literature;
**S** known in existing software; **Y** realised in symq; **V** validated experimentally (with
the run); **H** hypothesis not yet demonstrated.

### C1. Fast native implementation of monomial ZDDs for symbolic simulation of X/CX/CCX/MCX circuits

| question | answer |
|---|---|
| 1. Mechanism | ANF of every wire as a hash-consed ZDD of its monomial family; product by the three-product recursion `PQ = P0Q0 + v(P0Q1 + P1Q0 + P1Q1)`; lossless growing operation cache; per-node monomial counts; 64-bit monomial masks (width ≤ 64); time/node/term budgets that raise instead of returning partial results; minimum-degree counterexample re-executed concretely. `src/symq/backends/_zdd.c` (≈1 240 lines). |
| 2. Prior art | **L**: ZDDs (Minato 1993, 2001), polynomials as ZDDs (Minato 1995), Boolean polynomials as monomial ZDDs with recursive ring operations (Brickenstein & Dreyer 2009, PolyBoRi), applied to circuit verification (Brickenstein et al. 2008). **S**: PolyBoRi/BRiAl (C++, GPL), CUDD ZDDs (covers, not GF(2)). Irene (2026) uses ZDDs to *count* ANF monomials and argues against ANF. |
| 3. Remaining difference | No new representation or algorithm. Differences are engineering: specialisation (fixed width ≤ 64, one operation pattern), lossless cache without GC for short-lived managers, budgets, certified counterexamples, integration in an exact checker with interchangeable backends. |
| 4. Evidence | **V** (R-QCEC, `33515a3`, cold compute, same minimal Python loop): vs PolyBoRi 3.94× [3.49, 4.41], 19/19 wins (simulate); 3.00× (equiv); 3.46× (nonequiv). Warm caches: 2.11×. vs CUDD BDD (dynamic reordering) 3.48× [2.95, 4.10]; static order 3.38×. Native core vs Python ZDD under the same driver: 5.41× cold, 1.21× warm. Setup: 0.009 ms vs 4.39 ms (PolyBoRi ring) and 3.01 ms (CUDD manager). Binding costs (R-BIND) do not explain the gap: removing them leaves 4.41× (PolyBoRi) and 3.86× (CUDD). **R-BLIND**: vs PolyBoRi 3.47× [2.23, 5.04], 13/15 wins (H1 supported); vs CUDD with reordering **0.69× [0.15, 2.41]**, 9/16 wins — not distinguishable from 1; CUDD completes 71/90 cells vs 46/90; faster than native on adders and multipliers (default-order failures), slower on incrementers and controlled adders. |
| 5. Refuting experiment | Run: the blind corpus refutes the claim against CUDD (not against PolyBoRi). Not run: PolyBoRi driven from C++ (no Python per operation); a PolyBoRi/CUDD configuration (order, cache size) that closes the gap; another machine. |
| 6. Abstract wording | "…computes the symbolic outputs X× faster than PolyBoRi under identical Python drivers and cold caches, on the QCEC circuits and on a blind corpus; the advantage over CUDD BDDs seen on the QCEC circuits does not survive the blind corpus." **Not**: "new algorithm", "state of the art", "faster than CUDD" without qualification. |
| Verdict | **Engineering contribution.** Publishable only as an engineering/benchmarking result with the protocol (C5) as its backbone. |

### C2. Fusing many gates into one C call

| question | answer |
|---|---|
| 1. Mechanism | `NativeZDDManager.simulate` takes the whole gate list (control indices, offsets, targets) and runs the loop in C, multiplying the controls of each gate in increasing monomial count. |
| 2. Prior art | **L/S**: batching calls across a language boundary is standard practice; nothing to claim. |
| 3. Remaining difference | None scientific. |
| 4. Evidence | **V, positive after correction** (R-QCEC, `33515a3`): fused vs the plain unsorted Python loop **2.05× [1.83, 2.26], 19/19 wins**; fused vs the sorted loop 2.28×; sorting itself 0.90× [0.87, 0.93] (it slows down). R-BLIND (corrected-harness fused runs): 1.52× [1.30, 1.80], 15/18 wins on simulate (H2 supported). The first matched harness (`2346982`) found 0.97×: it built the fused loop's index arrays and gathered statistics inside the timed phase, while the Python loops received a pre-built gate list — a harness artifact, not an engine property. |
| 5. Refuting experiment | A fused loop without sorting (expected to gain a further ≈1.1×); long, shallow circuits. |
| 6. Abstract wording | "The gate loop fused in C is about 2× faster than a Python loop over the same operations, a gain our first harness hid; sorting factors by size slows the engine down." |
| Verdict | **Minor engineering result**, reported together with the harness artifact that had hidden it. |

### C3. Adaptive selection between explicit, ZDD and specialised representations

| question | answer |
|---|---|
| 1. Mechanism | `auto-zdd`: explicit sparse ANF promoted to ZDD when a live monomial count exceeds a threshold (850); `adaptive`: packed degree-≤2 representation with fallback; `adaptive-wire`: per-wire promotion. `src/symq/backends/adaptive.py` and selectors. |
| 2. Prior art | **L/S**: choosing a representation per instance is common (Irene keeps XOR–AND graphs instead of distributing to ANF; QCEC runs a portfolio of decision-diagram, simulation and ZX checkers). We did not survey adaptive ANF/ZDD switching specifically. |
| 3. Remaining difference | None demonstrated. |
| 4. Evidence | **Y, not V, partly negative** (R-QCEC0, R-THREE, Python backends): `auto-zdd` helps only on `c2_181` (37.5× over sparse) and costs a median ≈6 % elsewhere; it never switches on `apla_203`/`dk17_224` where pure ZDD wins up to 19×; `packed-fallback` 0.37–0.47×; `adaptive-wire` dominated by `auto-zdd`. Not measured with the native engine, not in R-QCEC/R-BLIND. Variable order changes node counts by up to 146× (R-ORDER, `c2_181`) and time by up to 156× (R-ORDER-BLIND, `adder_16`, identity vs best random order); on four blind adders only non-default orders complete. Any selector must include the order; symq has no ordering heuristic. |
| 5. Refuting experiment | Already partly refuted for the current selectors. A positive claim would need a selector tuned on a development split and evaluated on held-out circuits against "always native ZDD". |
| 6. Abstract wording | None. Mention only in limitations/future work. |
| Verdict | **Hypothesis, not a contribution of paper A.** |

### C4. Exact certificates for ±1 phases and HMR measurement outcomes under a restricted contract

| question | answer |
|---|---|
| 1. Mechanism | `src/symq/phase.py`: Boolean wire functions plus a phase polynomial over input and outcome variables; X-basis measure-and-reset; Z-type classical corrections; checks for outcome-independence of phase and output and for clean ancillas. Specification `docs/research/PHASE_HMR_SPEC.md`. |
| 2. Prior art | **L**: measure-and-fix-up uncomputation (Jones 2013; Gidney 2018; Luongo et al. 2024; Jeon et al. 2026); path sums with phase polynomials (Amy 2018); outcome-complete phased stabilizer simulation, which explicitly lists reversible adders/multipliers (Kliuchnikov et al. 2026); dynamic/hybrid circuit equivalence (Hong et al. 2022; Burgholzer & Wille 2022; Ricciardi et al. 2025; Irene 2026). **S**: `andigu/uncompute` exact "kickmix" evaluator with Lean 4 proofs (Apache-2.0). |
| 3. Remaining difference | Possibly a symbolic (all-inputs, all-outcomes) certificate for the restricted fragment with a monomial-ZDD backend; not demonstrated against the above. |
| 4. Evidence | **Y** reference implementation, proof sketches, exhaustive small-case tests against an independent state-vector oracle. **No external corpus, no budgeted native backend, no comparison** (issue #19). |
| 5. Refuting experiment | Import real programs from `andigu/uncompute`; compare with its exact evaluator and with phased outcome-complete simulation on the same programs. |
| 6. Abstract wording | None in paper A. Candidate thesis of a separate paper B. |
| Verdict | **Out of scope of paper A; exploratory.** |

### C5 (added). A matched-driver, cache-controlled benchmarking protocol and what it corrects

| question | answer |
|---|---|
| 1. Mechanism | Every engine runs under the same drivers (minimal loop, sorted loop, symq's `Algebra`; fused loop for symq only); phases timed separately (setup, compute, compare, witness, end-to-end, extraction); cold and warm cache regimes; fresh pinned worker per cell; paired ratios with bootstrap CIs; family-wise censoring; pre-registered blind corpus; cross-mode output fingerprints. `benchmarks/matched.py`, `benchmarks/matched_report.py`. |
| 2. Prior art | **L**: standard benchmarking hygiene; nothing new as methodology. |
| 3. Remaining difference | The specific findings: SageMath caches `BooleanPolynomialRing` by arguments, so repeated PolyBoRi runs in one process share warm operation caches (fresh variable names avoid it); symq's own `Algebra` driver costs 2.13×; building the fused loop's input inside the timer hid its ≈2× gain (our own harness artifact). |
| 4. Evidence | **V** (R-QCEC): cold vs warm PolyBoRi ratio 3.94× vs 2.11×; driver ablation table. |
| 5. Refuting experiment | Showing that the earlier campaigns on `main` (`b7f6045`, `b599319`) did not run PolyBoRi warm. Their adapter (`src/symq/external/polybori.py`) calls `BooleanPolynomialRing(width, "x", order="lp")`, which SageMath returns from its cache for every repetition of the same width in one process, so this is unlikely. |
| 6. Abstract wording | "We find that driver overhead and warm caches each change the measured ratios by about 2×, and report both regimes." |
| Verdict | **Secondary contribution (methodological lesson), not novel methodology.** |

## Contribution statement (≤ 1 page, for author approval)

**Title.** SymQ: Exact Equivalence Checking of Reversible Boolean Circuits with a Native
Monomial-ZDD Engine — an Evaluation with Matched Drivers.

**What the paper is.** An engineering and measurement paper. It describes an open-source
exact checker for X/CX/CCX/MCX circuits based on symbolic simulation in the Boolean ring, a
small budgeted native monomial-ZDD engine, and an evaluation protocol that separates the
engine from its driver and controls cache state.

**Contributions.**
1. A specialised, budgeted native engine for monomial ZDDs with certified counterexamples,
   integrated in an exact checker with interchangeable backends (C1, engineering).
2. A matched-driver, cache-controlled comparison with PolyBoRi and CUDD on 19 public
   circuits and a pre-registered blind corpus, with paired statistics (C1/C5).
3. Adverse results: factor sorting slows the engine; the advantage over CUDD does not survive
   the blind corpus; a harness artifact had hidden the ≈2× gain of the fused loop; ANF blows up on
   multipliers under every order tried; the default variable order is up to two orders of
   magnitude slower than a random one on adders, and fails on larger adders that other
   orders handle (C2, C3, E4).
4. Exactness evidence: identical outputs across every engine that builds ANF and 7 variable
   orders, 38 independent QCEC proofs agreeing with every verdict, re-checked
   counterexamples; the 3 blind-corpus disagreements came from our CUDD-to-ANF conversion
   (pre-registered H3 rejected as stated; defect fixed by PR #38).

**Explicit non-contributions.** No new representation (ANF as monomial ZDDs is PolyBoRi's);
no new decision procedure or complexity bound; no claim of state of the art or general
superiority; no claim against PolyBoRi/CUDD/QCEC beyond the measured drivers and circuits;
no quantum (non-classical) gates; no HMR/phase result (paper B); no machine-checked proof.

**Limitations that must appear in the abstract.** ≤ 64 variables; small circuits and
sub-millisecond medians; one machine; Python drivers for all tools; ANF blow-up on
multipliers; QCEC answers a different question and is context only.

## Threats specific to the claims

- **Driver bias against other tools** (C1). The minimal loop is Python for everybody. symq's
  fused loop gains ≈2× over the Python loop *for symq*, so a C++ driver could plausibly gain
  as much for PolyBoRi; calibrated binding costs bound but do not replace that experiment.
- **Holdout** (C1). The QCEC circuits shaped the design (three-product recursion, default
  order). Only the blind corpus is a holdout; it is generated, not collected.
- **Measurement on older code.** All runs use the native binary `2e3f6791` built from
  `main@234696e` sources; the overflow fix (PR #23), the width-64 fix (PR #37) and the CUDD
  conversion fix (PR #38) are not in the measured code.
