# Pre-registration of the blind corpus (issue #18, E3)

Frozen on 27 October 2026, in the commit that adds this file, **before** any symbolic
backend or external tool was run on these circuits. The only computations performed before
freezing were concrete executions checking that each arithmetic circuit computes its
function (200 random inputs per circuit, `generate_blind.py`). `MANIFEST.json` records the
SHA-256 and Git blob SHA-1 of every file; `tests/test_blind_corpus.py` checks them and
regenerates the corpus byte for byte.

## Why a new corpus

The 19 supported QCEC circuits have all influenced design decisions (DEV tuned the
`auto-zdd` threshold; holdout and extension were inspected while the native core was
written). Any comparison that is meant to generalise must be evaluated on circuits that
influenced nothing.

## Families and sizes (fixed before measurement)

| family | sizes | width | why |
|---|---|---|---|
| `adder_n` (Cuccaro) | n = 4, 8, 16, 24, 31 | 2n + 2 | standard reversible arithmetic, low degree per gate, long carry chain |
| `cadder_n` (controlled Cuccaro) | n = 4, 8, 16, 24, 30 | 2n + 3 | adds a global control: every gate gets one more control |
| `mult_n` (shift-and-add) | n = 2, 3, 4, 5, 6, 8, 10 | 4n + 1 | dense high-degree outputs; expected to defeat monomial representations |
| `incr_n` | n = 16, 32, 48, 64 | n | very wide MCX gates; outputs with two monomials each |
| `rand_w_g_k` | w = 16, 32, 64; (g, k) = (100, 2), (100, 4), (400, 2) | w | unstructured, seeded |

Widths stop at 64 because `zdd-native` packs monomials in 64-bit masks; that restriction
is part of the contract being evaluated, not a selection of favourable cases.

## Protocol

- Driver: `benchmarks/matched.py`, one fresh worker process per (circuit, workload, mode),
  pinned to one CPU, cells in a seeded random order, 1 warmup then the median of the
  repetitions (7 by default, 3 if one run exceeds 1 s, 1 if it exceeds 10 s).
- Timeout: a worker is killed after 120 s of wall time (warmup and repetitions included);
  the cell is then reported as `timeout` and never imputed.
- Workloads: `simulate`, `equiv` (sound rewrites), `nonequiv` (one inserted MCX), generated
  with the same seeded generators as the QCEC corpus.
- Phases timed separately: manager setup, symbolic computation, comparison, witness,
  extraction of explicit monomials, end to end.

## Hypotheses (stated before measurement)

- **H1 (matched driver).** With the *same* Python per-gate loop, `zdd-native` is faster than
  PolyBoRi on `simulate`: geometric mean of the paired ratio > 1 over the circuits both
  complete. This isolates the engine from the driver.
- **H2 (fused loop).** The fused C gate loop is faster than the same engine driven gate by
  gate from Python: geometric mean > 1.
- **H3 (exactness).** Every completed cell agrees: identical output fingerprints across
  modes, correct verdicts, concretely valid witnesses.
- **H4 (expected negative).** Multipliers blow up for monomial representations
  (`zdd-native`, PolyBoRi) faster than for function BDDs (CUDD). No direction is assumed
  between CUDD and the monomial tools elsewhere.
- No hypothesis is stated for MQT QCEC: it answers a different question (unitary equality)
  and is reported for context only.

## Analysis plan

Paired ratios per circuit and workload; geometric mean with a 95% percentile bootstrap
interval over circuits (10 000 resamples, fixed seed), median, minimum, maximum and the
number of wins. Circuits where only one side completes are counted separately. All results,
including adverse ones, go into the sealed result directory and the paper.

## Amendment 1 (27 October 2026, before the sealed measurement)

Made after a harness smoke test on two QCEC circuits revealed a cache asymmetry, and before
any measurement on this corpus whose timings were inspected (a second smoke test on
`adder_4` and `incr_16` checked only the cell statuses of the harness; its output was
discarded unread).

1. **Cache regimes.** Sage caches `BooleanPolynomialRing` by its arguments, so successive
   PolyBoRi runs of the same width reused one ring and its operation cache, while every
   other tool started from a fresh manager. Each run now builds a fresh manager for every
   tool, PolyBoRi included (fresh variable names), and is reported as *cold*. A *warm*
   regime — one manager reused across runs after a filling run — is reported separately.
   H1 and H2 are evaluated on the cold compute phase.
2. **Monotone timeout censoring.** Cells of one (family, workload, mode) run in increasing
   size; after a timeout, the larger circuits of that chain are recorded as
   `timeout_censored` without being run. Chains are shuffled with the fixed seed.
3. **Parallel workers.** Up to three workers run at once, each pinned to its own physical
   core (4 cores, 1 thread per core).
