# Native baselines: PolyBoRi, CUDD and MQT QCEC (issue #5)

Source: `benchmarks/results/20261027T142608Z_b599319c814e_audit-qcec-timing/` (symq `b599319`,
CPython 3.12.3, 4 vCPU Intel Xeon, single-threaded workers; 1 warmup + median of 7; 19
supported circuits × 3 workloads × 9 backends = 513 cells). It supersedes
`20261027T135651Z_b7f604567098_native-core/`, whose QCEC timings mixed conversion and
verification (see the audit note below). Reproduce with:

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

- All 513 cells completed (19 circuits × 3 workloads × 9 backends). Every native algebra
  produced the same output ANF as the symq backends. QCEC returned 38 of 38 correct verdicts,
  all of them proofs (`equivalent` or `not_equivalent`, no `probably_*`).
- `zdd-native` reproduces the pure-Python `zdd` exactly: same outputs, same term counts and
  the same node tables (diagram sizes are identical on all 19 circuits), so the speed
  comparison isolates the implementation, not the algorithm.
- `tests/test_external.py` adds differential tests: 60 random circuits per algebra against
  `Circuit.symbolic()`, the whole corpus, equivalence verdicts with witnesses, and QCEC proofs.
  They run in the `external` CI job. `tests/test_zdd_native.py` does the same for the core.

## Results

Median ms; ratios are paired per circuit (>1 means faster than the reference named).

| `c2_181` (pathological case) | `sparse-copy` | `zdd` | `zdd-native` | `polybori` | `cudd-bdd` | `qcec` |
|---|---:|---:|---:|---:|---:|---:|
| simulate | 161 | 2.73 | 0.245 | 0.329 | 4.51 | n/a |
| equiv | 4 793 | 5.50 | 0.541 | 0.950 | 14.0 | 6.71 |
| nonequiv | 316 | 2.90 | 0.345 | 0.699 | 14.6 | 2.80 |

1. **The `c2_181` speedup is a representation effect.** A native monomial ZDD reproduces it
   and amplifies it: PolyBoRi is 489× faster than `sparse-copy` (simulate), and symq's own
   native core 656× (equiv: 8 857×). Once both sides run compiled code with the same
   structure, the ratio stops being a language artefact.
2. **The native core is faster than PolyBoRi on this corpus.** Across the 19 circuits,
   `zdd-native` is 4.32× faster in simulate (1.34–8.73×), 4.03× in equiv (1.32–7.13×) and
   3.60× in nonequiv (2.03–8.31×). This is a single-machine, small-circuit result driven by
   the fused gate loop and does not establish general superiority (see Threats to validity).
3. **The Python ZDD lost to PolyBoRi for a measurable reason.** `zdd-native` is 11.0× faster
   than `zdd` in simulate (4.6–14.5×), 8.6× in equiv and 6.3× in nonequiv, with identical
   node tables (the diagrams are the same). Isolating the two changes, with the same
   `Algebra.simulate` driver on both sides: the C core alone is 1.96× faster than PolyBoRi
   (median, 1.07–5.12×); calling the whole gate list from C instead of per gate is another
   2.65× (1.41–3.79×). On `rd84_313`, `Algebra.simulate` takes 0.128 ms, the fused call
   0.060 ms, and PolyBoRi 0.500 ms.
4. **CUDD pays a fixed cost per run.** Creating a manager and declaring the variables cost
   1.7–4.6 ms on this machine, measured separately. That accounts for the 2.0 ms floor of
   `cudd-bdd` simulate (median 2.5 ms). `cudd-zdd` is slower again: a function ZDD does not
   share the monomial structure, and it has 2.6–12× more nodes than PolyBoRi on the same
   outputs.
5. **QCEC answers a different question.** It decides unitary equality without building
   output polynomials. Times range from 1.3 to 44 ms (equiv) and from 1.5 to 8.1 ms
   (nonequiv). It is 11–516× slower than `zdd-native` in equiv (median 46×) and slower than
   `zdd-native` on all 19 circuits in both workloads; it still returns a verdict without
   building any polynomial, which the polynomial backends cannot do.
   Three timings are now measured separately, because an earlier version of this document
   quoted a single number while claiming the conversion was excluded from it:
   `conversion` (building both `QuantumComputation`s) has median 0.117 ms; the native check
   on pre-built objects has median 3.28 ms; the end-to-end helper has median 3.19 ms, i.e.
   1.036× the native time (0.47–1.19×). Subtracting the two gives an implied conversion of
   0.120 ms, consistent with the measured 0.117 ms. Within the native time, QCEC's own
   reported check is 1.23 ms (median) below the wall clock, which is the binding overhead.

### Conversion overhead

Converting the native outputs back to ANF is needed only for fingerprints and witnesses, so
it is timed separately (Native tools section of the report).

| adapter | conversion time / simulate time |
|---|---|
| PolyBoRi (term enumeration) | median 2.49× (0.23–39×) |
| CUDD BDD (Reed–Muller) | median 0.81× (0.29–4.9×) |
| CUDD ZDD (Möbius transform) | median 0.84× (0.32–1.9×) |

On `c2_181`, whose outputs have up to 4 866 terms, extracting PolyBoRi's ANF takes 12.9 ms,
39× the simulation. A pipeline that needs explicit monomials pays this cost; a pipeline that
only needs verdicts does not.

### Memory

tracemalloc sees only Python allocations, so its KiB columns are meaningless for the native
tools (2–17 KiB). Worker peak RSS is dominated by the interpreter and the imported
libraries. Median per simulate worker: 98 MiB for `sparse`, `zdd` and `zdd-native`, 128 MiB
for `polybori`, 131 MiB for `cudd-zdd`, 139 MiB for `cudd-bdd`; the QCEC workers peak at
106 MiB. The native core adds no measurable Python-side allocation: its tables are `malloc`ed
outside tracemalloc. No memory comparison between tools is claimed.

## Failure modes found

- **Slow equality through Sage.** `==` on `BooleanPolynomial` compares term by term: 11.3 ms
  for the 35 outputs of `c2_181`, against 0.02 ms for `(a + b).is_zero()`. The first sealed
  run (`20261027T131026Z_5bd6e66607be_external/`) still used `==`, giving 11.8 ms instead of
  0.92 ms for `c2_181` equiv. Both runs produced the same outputs on all 456 cells, and the
  medians of the other backends moved by at most ±2%. `a.set() == b.set()` is not a
  substitute: it compares wrappers and returns False for equal polynomials.
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

## Audit corrections

The independent audit of `5bfd6f0` found that the QCEC row of an earlier version of this
document was mis-timed: the harness rebuilt both `QuantumComputation`s inside the timed call
while the text said the conversion was excluded. The three timings above replace it, and
`docs/research/AUDIT_2026-10-27.md` records every finding with its resolution.
