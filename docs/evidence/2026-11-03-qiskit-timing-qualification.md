# Qiskit 2.6.1 → SymQ full-call timing qualification (research cohort)

**Source code:** Draft PR #185 at
`b01ab4db4c3d16248e985f9e0ab8b293fb723856`.
**GitHub Actions:** [dedicated run 41701010947](https://github.com/yoch/symq/actions/runs/41701010947), conclusion success.
**Raw data:** [artifact 13263531451](https://github.com/yoch/symq/actions/runs/41701010947/artifacts/13263531451), two JSONL files:
- `qiskit-source-manifest.jsonl`, SHA-256 `4bd30e5bbfdb2fc8771bcd3b98b1e1bcd3de789d0cd43324a9b980835e305628`
- `qiskit-rewrite-timings.jsonl`, SHA-256 `83d4c7c970d86cd2df57b4889ec6c6979465d12a4442a105530d06245f9dc3d1`

**Environment:** GitHub-hosted Linux, Python 3.12.15, Qiskit exactly
2.6.1; 15 paired repetitions, with order randomized deterministically.
Each observation launches a fresh Python subprocess and executes real
transpilation, QASM2 export + SymQ parse, exact structural preparation,
SAT proof and fresh replay. Wall and CPU times are observed, not calibrated.
`process_peak_rss_kib_linux` is a **process-wide high-water mark**, not
operation-attributable memory. Interpreter startup-inclusive time includes
the external Python process; in-process total excludes interpreter startup.
Each row's exact QASM SHA and `status=equivalent_replayed` was inspected.

## Descriptive results (15 samples per row, median / observed min–max)

| Metric | SWAP–CX–SWAP / candidate CX | double SWAP + CCX / candidate CCX |
| --- | --- | --- |
| Source gate count | 7 → 1 | 7 → 1 |
| Startup-inclusive wall, ms | 536.85 (530.00–560.77) | 537.97 (526.55–580.73) |
| In-process total, ms | 335.23 (330.10–350.36) | 336.19 (328.04–369.77) |
| Compiler + parser, ms | 324.33 (319.30–339.23) | 324.91 (317.04–358.73) |
| SymQ prepare, ms | 0.516 (0.506–0.550) | 0.529 (0.512–0.575) |
| SAT proof, ms | 8.759 (8.599–9.256) | 8.898 (8.578–9.349) |
| Fresh replay, ms | 1.628 (1.571–1.854) | 1.665 (1.626–1.881) |
| Process peak RSS, KiB | 114,640 (114,316–114,712) | 114,760 (114,468–115,404) |

The ~10–11 ms measured SymQ proof+replay on these 5-wire embedded
small examples is dwarfed by Qiskit import/transpilation and process
startup. This says **nothing** about scaling or comparative theorem
strength. Process CPU time can exceed in-process wall time due to
parallelized native libraries; it is logged in raw data but does not
replace the wall measurement.

## Boundaries / what has *not* been shown

- These are two closely related small development cases, no untouched
  holdout, no general compiler performance improvement, and no
  scientifically meaningful speedup over Qiskit or other verifiers.
- The alternatives were derived independently rather than produced by
  the Qiskit optimizer. The executable program is a fully reversible
  phase-free X/CX/CCX permutation; no hybrid/measurement/reset semantics.
- SAT equivalence is proved for each frozen source pair using SymQ's
  classical contextual theorem and an explicit contract. The converter
  and SAT encoding remain part of the trusted code; the independent
  basis evaluator is an additional small-width check, not a machine
  proof of the encoder.
- The benchmarks do not compare matched alternative certification
  engines and **must not** be advertised as comparative speedup.
- No package API promotion, default-engine change, merge or release
  is authorized. An independent review should reproduce at least one
  exact row and inspect raw source/receipt artifacts before publication.

**Reproduction:** on pinned Python/Qiskit setup, run
`python -m benchmarks.qiskit_rewrite_benchmark --benchmark --repetitions 15`.
The source-producing run must agree on the two exact QASM SHA values
in the artifact. CI run #41701010947 is evidence for source HEAD
`b01ab4db4c3d16248e985f9e0ab8b293fb723856` only.
