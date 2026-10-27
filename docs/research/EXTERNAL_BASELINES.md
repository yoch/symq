# Native baselines: PolyBoRi, CUDD and MQT QCEC (issue #5)

Source: `benchmarks/results/20261027T135651Z_b7f604567098_native-core/` (symq `b7f6045`,
CPython 3.12.3, 4 vCPU Intel Xeon, single-threaded workers; 1 warmup + median of 7; 19
supported circuits × 3 workloads × 9 backends = 513 cells). Reproduce with:

```bash
pip install -e ".[external,native]"
python benchmarks/run.py --backends sparse-copy sparse zdd zdd-native auto-zdd polybori \
    cudd-bdd cudd-zdd qcec
```

The tools are reached through Python bindings, driven gate by gate by the same Python code as
the symq backends, on one machine and a corpus of small circuits (16–35 wires, most medians
below 2 ms). The earlier run `20261027T132423Z_38c6ef486b3b_external-eq/` covers the same
backends without `zdd-native`; its numbers are unchanged where the two runs overlap.

## Semantic compatibility

| tool (version) | adapter | what it represents | matched operations | what it cannot give |
|---|---|---|---|---|
| PolyBoRi / BRiAl (`passagemath-brial` 10.8.13) | `polybori` | GF(2)[x]/(x²−x), the same ring as symq, stored as monomial ZDDs; order `lp` | XOR = `+`, product = `*`, equality = `(a + b).is_zero()` | — |
| CUDD 3.0.0 through `dd` 0.6.0 | `cudd-bdd` | the same Boolean functions as BDDs (Shannon cofactors); dynamic reordering on, as in CUDD | XOR = `apply("xor")`, product = conjunction, equality = node identity | monomials: `terms` is unavailable; ANF needs a Reed–Muller transform |
| idem | `cudd-zdd` | the same functions as ZDDs of their satisfying assignments | idem | idem; CUDD's family product (`Cudd_zddProduct`) is a unate cover product without parity cancellation, so CUDD has no native ANF ring |
| MQT QCEC 3.11.0 (`mqt.core` 3.11.0) | `qcec` | the circuits' unitaries; an X/CX/MCX circuit is a permutation matrix, so unitary equality (even up to global phase) is exactly functional equality | `equiv` and `nonequiv` verdicts only, alternating decision-diagram checker alone (no simulation, no ZX), so every conclusive verdict is a proof | output polynomials (`simulate` is `not_applicable`); no counterexample in this configuration |

All three native algebras implement symq's `Algebra` contract, so `simulate` and
`check_equivalence` run the same code. Non-equivalence witnesses are re-checked by concrete
execution, as for every backend.

## Correctness

- All 456 cells completed. Every native algebra produced the same output ANF as the symq
  backends (fingerprints of all 19 circuits × 3 workloads). QCEC returned 38 of 38 correct
  verdicts, all of them proofs (`equivalent` or `not_equivalent`, no `probably_*`).
- `tests/test_external.py` adds differential tests: 60 random circuits per algebra against
  `Circuit.symbolic()`, the whole corpus, equivalence verdicts with witnesses, and QCEC proofs.
  They run in the `external` CI job.

## Results

Median ms; ratios are paired per circuit (>1 means faster than the reference named).

| `c2_181` (pathological case) | `sparse-copy` | `zdd` | `zdd-native` | `polybori` | `cudd-bdd` | `qcec` |
|---|---:|---:|---:|---:|---:|---:|
| simulate | 160 | 2.72 | 0.250 | 0.327 | 4.51 | n/a |
| equiv | 4 554 | 5.44 | 0.523 | 0.942 | 14.0 | 6.95 |
| nonequiv | 321 | 2.89 | 0.325 | 0.701 | 14.6 | 3.42 |

1. **The `c2_181` speedup is a representation effect.** A native monomial ZDD reproduces it
   and amplifies it: PolyBoRi is 490× faster than `sparse-copy` (simulate), and symq's own
   native core 617× (equiv: 8 822×). Once both sides run compiled code with the same
   structure, the ratio stops being a language artefact.
2. **The native core is faster than PolyBoRi on this corpus.** Across the 19 circuits,
   `zdd-native` is 4.37× faster in simulate (1.31–9.12×), 4.38× in equiv (1.40–7.09×) and
   3.97× in nonequiv (2.16–8.69×). This is a single-machine, small-circuit result driven by
   the fused gate loop and does not establish general superiority (see Threats to validity).
3. **The Python ZDD lost to PolyBoRi for a measurable reason.** `zdd-native` is 11.1× faster
   than `zdd` in simulate (6.7–19.3×), 9.3× in equiv and 6.6× in nonequiv, with identical
   node tables (the diagrams are the same). Isolating the two changes, with the same
   `Algebra.simulate` driver on both sides: the C core alone is 1.96× faster than PolyBoRi
   (median, 1.07–5.12×); calling the whole gate list from C instead of per gate is another
   2.65× (1.41–3.79×). On `rd84_313`, `Algebra.simulate` takes 0.128 ms, the fused call
   0.060 ms, and PolyBoRi 0.500 ms.
4. **CUDD pays a fixed cost per run.** Creating a manager and declaring the variables cost
   1.7–4.6 ms on this machine, measured separately. That accounts for the 1.9 ms floor of
   `cudd-bdd` simulate (median 2.7 ms). `cudd-zdd` is slower again: a function ZDD does not
   share the monomial structure, and it has 2.6–12× more nodes than PolyBoRi on the same
   outputs.
5. **QCEC answers a different question.** It decides unitary equality without building
   output polynomials. Times range from 1.4 to 43 ms (equiv) and from 2.2 to 7.6 ms
   (nonequiv). It is 11–516× slower than `zdd-native` in equiv, but beats every polynomial
   representation on the few cases where the alternating checker is cheap. The binding adds
   0.8 ms (median) per call on top of QCEC's own check and preprocessing times. The
   conversion to `QuantumComputation` (0.2 ms median) is excluded from these timings.

### Conversion overhead

Converting the native outputs back to ANF is needed only for fingerprints and witnesses, so
it is timed separately (Native tools section of the report).

| adapter | conversion time / simulate time |
|---|---|
| PolyBoRi (term enumeration) | median 2.6× (0.19–38×) |
| CUDD BDD (Reed–Muller) | median 0.9× (0.26–5×) |
| CUDD ZDD (Möbius transform) | median 0.75× (0.33–1.8×) |

On `c2_181`, whose outputs have up to 4 866 terms, extracting PolyBoRi's ANF takes 12.6 ms,
39× the simulation. A pipeline that needs explicit monomials pays this cost; a pipeline that
only needs verdicts does not.

### Memory

tracemalloc sees only Python allocations, so its KiB columns are meaningless for the native
tools (4–11 KiB). Worker peak RSS is dominated by the interpreter and the imported
libraries. Median per worker: 98 MiB for `sparse` and `zdd`, 106 MiB for `qcec`, 128 MiB
for `polybori`, 131 MiB for `cudd-zdd` and 139 MiB for `cudd-bdd`. No memory comparison is
claimed.

## Failure modes found

- **Slow equality through Sage.** `==` on `BooleanPolynomial` compares term by term: 11.3 ms
  for the 35 outputs of `c2_181`, against 0.02 ms for `(a + b).is_zero()`. The first sealed
  run (`20261027T131026Z_5bd6e66607be_external/`) still used `==`, giving 11.8 ms instead of
  0.92 ms for `c2_181` equiv. Both runs produced the same outputs on all 456 cells, and the
  medians of the other backends moved by at most ±2%. `a.set() == b.set()` is not a substitute: it compares wrappers and returns
  False for equal polynomials.
- **`dd.cudd_zdd` substitution.** After a partial `let`, it can return constants that are not
  `manager.true`/`manager.false`, and `node.var` need not be in the support. A Reed–Muller
  transform based on `let` therefore produced wrong ANFs; the concrete re-check raised
  `InternalInconsistency`. The ZDD adapter reads the diagram through `succ` instead
  (Möbius transform, one factor (1 + y) per skipped level).
- **Crash at teardown.** During development, `dd` crashed (segmentation fault) while freeing
  a manager after an exception in the same process. Benchmark workers did not reproduce it:
  budget exhaustion on all three native algebras exits cleanly. A crash in a worker would be
  recorded as `error` with its stderr.
- **Budgets are coarse.** Native calls cannot be interrupted. Time and size budgets are
  checked between operations: terms after each PolyBoRi product, manager nodes after each
  CUDD product, and QCEC's own `timeout`.
- **No `ccx` in `mqt.core`.** Toffoli gates are emitted as `mcx`.

## Threats to validity

- One machine, sub-millisecond medians, small circuits: no confidence interval is claimed.
- `zdd-native` is measured with its fused gate loop; PolyBoRi and CUDD are driven gate by gate
  from Python, because their adapters implement the `Algebra` contract one gate at a time.
  Part of the ratio therefore compares an amortised call pattern with a per-gate one, which is
  why the isolation in point 3 is reported separately. A C++ driver for PolyBoRi, a reused
  manager or tuned CUDD orders could change the ranking.
- CUDD ran with its defaults (dynamic reordering on) and no tuned variable order; a tuned
  order could only help it.
- QCEC was limited to its complete alternating checker. Its default portfolio (simulation
  and ZX checkers, run in parallel) can be faster, but may return non-proof verdicts.
