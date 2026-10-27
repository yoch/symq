# Benchmarks

## Corpus

`corpus/qcec/` holds the 20 files of `test/circuits/original` from
[MQT QCEC](https://github.com/munich-quantum-toolkit/qcec) at commit
`98d6784176bfeb6ef923d4d0220e8d486dc1982f`, byte for byte, with the upstream MIT license in
`corpus/qcec/LICENSE_QCEC.txt`. `MANIFEST.json` records for each file the upstream path,
the Git blob SHA-1 checked against the upstream tree at import time, the SHA-256, the size,
the width, the gate count and the split. `python benchmarks/import_qcec.py` re-imports it
(network required); `pytest tests/test_corpus.py` re-verifies every hash offline.

Splits are fixed:

| split | circuits | use |
|---|---|---|
| `dev` | `c2_181`, `mod5adder_306`, `rd73_312`, `rd84_313`, `sym9_317` | the 5 circuits on which the archived `auto_zdd` threshold (850) was tuned |
| `holdout` | `5xp1_194`, `alu1_198`, `dk27_225`, `cm150a_210`, `pcler8_248`, `mlp4_245` | the 6 circuits reserved in the 27 Oct 2026 handoff |
| `extension` | the 9 remaining files | never used for tuning; widens the corpus beyond the handoff |

`c2_182` contains controlled-V gates (`ctrl @ U(pi/2, ±pi/2, ∓pi/2)`), outside the
X/CX/CCX/MCX model: it is recorded as `unsupported`, never converted.

All benchmark inputs are fully symbolic (`full_input`). Restricted-input and synthetic
workloads of the archive (for example the GF(2¹²) fragments) are not reproduced here.

## Running

```bash
python -m pip install -e ".[dev]"
python benchmarks/run.py                       # all splits, all backends, 7 repetitions
python benchmarks/run.py --splits dev --backends sparse zdd auto-zdd --repetitions 3
```

The tracked tree must be clean (the commit SHA is recorded) unless `--allow-dirty` is
given. Each run writes `results/<UTC timestamp>_<commit>_<label>/`, which is never
overwritten:

- `environment.json`: commit, dirty flag, Python, platform, CPU model and count, RAM,
  corpus manifest digest, full protocol and command line;
- `results.jsonl`: one row per (circuit, workload, backend) with every repetition time,
  status (`ok`, `resource_limit` with the refused resource, `timeout`, `error`,
  `wrong_verdict`, `unsupported`), generation time, `tracemalloc` peak, worker RSS, backend
  counters (conversions, ZDD nodes, `auto-zdd` switch gate) and an output fingerprint;
- `REPORT.md`: tables per workload, paired speedups against `sparse-copy` (the archived
  `qant_set`) per split with `c2_181` reported separately, memory, and the comparison with
  the historical handoff numbers in `historical/handoff_2026-10-27.json`;
- `SHA256SUMS`: digests of the files above; `tests/test_corpus.py` checks them.

Workloads: `simulate` (symbolic outputs), `equiv` (against a variant built only from sound
rewrites, expected equivalent) and `nonequiv` (against the circuit with one inserted MCX
gate, which can never be equivalent). A wrong verdict or a disagreement between backends is
reported at the top of `REPORT.md`.

## Interpreting results

Python-only timings on one machine. They compare representations implemented in the same
language; they say nothing about native tools (CUDD, PolyBoRi, MQT QCEC), which need a
matched semantic contract and their own measurements (issue #5). Medians under 1 ms are
noisy. A single pathological circuit (`c2_181`) must not be generalized.
