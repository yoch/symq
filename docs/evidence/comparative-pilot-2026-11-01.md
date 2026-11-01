# Comparative development pilot of 1 November 2026

## Scope and limitations

- **What is compared.** SymQ's SAT and ZDD engines against MQT QCEC 3.11 on classical full
  permutations, and SymQ's ZDD channel checker against the independent exact Kraus oracle
  (`hybrid-exact`) on measurement-based HMR channels. Each comparison uses the same theorem on
  both sides. QCEC is not run on HMR channels (its unitary adapter does not prove them), and PyZX
  is not run (no verified adapter for the same theorem).
- **The cases are development material.** The 13 cases come from the QCEC `dev` split (MIT), the
  public bilinear KMB corpus (Apache 2.0) and the Qualtran GF2MulMBUC decompositions (Apache
  2.0), plus synthetic dirty-register controls. All were seen during development; none is a
  holdout, and the synthetic variants are not independent compiler outputs.
- **One machine, small circuits.** Every trial runs in a fresh process with hard wall-clock, CPU
  and address-space limits (`run_isolated`). On circuits this small, decision times are
  milliseconds and the process start dominates the worker wall time.
- **No ranking.** The paired ratios below describe four selected cases. They do not show that
  either tool is faster in general.

## Requalification on every commit

The CI job `external` reruns the whole campaign on the exact commit under test and keeps the
results in the `external-evidence` artifact, whether the job passes or fails:
- `comparative-coverage.json`: the 13 cases and 35 cells, once;
- `comparative-paired.json`: the four preregistered cases, `kmb-gf16-original-vs-tower`,
  `borrowed-dirty-missing-uncompute`, `qualtran-m1-hmr-cleanup` and
  `qualtran-m1-hmr-missing-correction`, with 15 paired repetitions;
- a `.sha256` sidecar for each JSON file, and a Markdown rendering of each.

Each JSON file records:
- the tested commit, whether the tree was dirty, the source digest and the native binary digest;
- the versions of python-sat and of the external tools;
- cold imports apart from decisions;
- CPU and wall time, peak RSS, and every censored cell.

The job fails on an incorrect decision, an invalid witness or a worker error. These runs are
development requalifications on the same public material, not a holdout. The records below,
from 1 November, are kept as historical data.

## Records

Two runs of `python -m benchmarks.comparative` on commit
`63a864205c0851999813b83fea77b7c5daba3f79` (clean tree, native ABI 6, python-sat 1.9.dev17,
mqt.qcec 3.11.0), recorded in [`data/2026-11-01/`](data/2026-11-01/) with a `SHA256SUMS` file:

- `coverage.json`: all 13 cases, one repetition: **35 of 35** eligible engine trials returned
  the expected decision.
- `paired.json`: four cases, 15 repetitions each, engines in randomized order: **150 of 150**
  trials returned the expected decision.

```bash
python -m benchmarks.comparative --output coverage.json --repetitions 1 --wall-seconds 12
python -m benchmarks.comparative --output paired.json --repetitions 15 --wall-seconds 10 \
    --case kmb-gf16-original-vs-tower --case borrowed-dirty-missing-uncompute \
    --case qualtran-m1-hmr-cleanup --case qualtran-m1-hmr-missing-correction
```

## Paired cohort

Medians over the correct trials. "Decision" includes converting the circuit for the engine;
cold imports are measured separately; worker wall time and peak RSS cover the whole process.
The tables are produced by `benchmarks.comparative_report` from `paired.json`, and
`tests/test_evidence.py` checks that they still are.

<!-- comparative:cases -->
| Case | Theorem | Expected | Engine | Correct/eligible | Incomplete or wrong | Cold import (s) | Decision+conversion (s) | Worker wall (s) | Peak RSS (MiB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kmb-gf16-original-vs-tower | classical | equivalent | qcec | 15/15 | none | 0.0382 | 0.0122 | 0.1730 | 56.0 |
| kmb-gf16-original-vs-tower | classical | equivalent | sat | 15/15 | none | 0.0000 | 0.0838 | 0.2013 | 47.9 |
| kmb-gf16-original-vs-tower | classical | equivalent | zdd | 15/15 | none | 0.0000 | 0.0007 | 0.1128 | 47.9 |
| borrowed-dirty-missing-uncompute | classical | different | qcec | 15/15 | none | 0.0385 | 0.0044 | 0.1531 | 53.8 |
| borrowed-dirty-missing-uncompute | classical | different | sat | 15/15 | none | 0.0000 | 0.0074 | 0.1089 | 47.8 |
| borrowed-dirty-missing-uncompute | classical | different | zdd | 15/15 | none | 0.0000 | 0.0001 | 0.0988 | 47.8 |
| qualtran-m1-hmr-cleanup | hmr | equivalent | hybrid-exact | 15/15 | none | 0.0040 | 0.0012 | 0.1061 | 48.1 |
| qualtran-m1-hmr-cleanup | hmr | equivalent | zdd | 15/15 | none | 0.0000 | 0.0056 | 0.1075 | 48.1 |
| qualtran-m1-hmr-missing-correction | hmr | different | hybrid-exact | 15/15 | none | 0.0041 | 0.0007 | 0.1052 | 47.8 |
| qualtran-m1-hmr-missing-correction | hmr | different | zdd | 15/15 | none | 0.0000 | 0.0057 | 0.1052 | 47.8 |
<!-- /comparative -->

Ratios are medians over the repetitions where both engines decided correctly:

<!-- comparative:ratios -->
| Case | Ratio label | Complete matched pairs | Median | p10–p90 |
| --- | --- | ---: | ---: | --- |
| kmb-gf16-original-vs-tower | sat / qcec decision wall seconds | 15 | 6.9031 | 6.4640–7.3231 |
| borrowed-dirty-missing-uncompute | sat / qcec decision wall seconds | 15 | 1.7023 | 1.4177–1.8466 |
| qualtran-m1-hmr-cleanup | zdd / hybrid-exact decision wall seconds | 15 | 4.6003 | 4.4835–4.8128 |
| qualtran-m1-hmr-missing-correction | zdd / hybrid-exact decision wall seconds | 15 | 8.6301 | 7.9102–9.2807 |
<!-- /comparative -->

On these four cases SymQ's SAT engine takes 1.7 to 6.9 times QCEC's decision time, and SymQ's
ZDD channel checker 4.6 to 8.6 times the Kraus oracle's, in milliseconds either way. SymQ's ZDD
decides the classical cases faster than QCEC (0.7 ms against 12 ms on the GF(16) multiplier), but
QCEC's 38 ms cold import and the process start make all worker wall times similar (0.1 to 0.2 s).
