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
python -m benchmarks.run                       # all splits, all backends, 7 repetitions
python -m benchmarks.run --splits dev --backends sparse zdd auto-zdd --repetitions 3
```

The tracked tree must be clean (the commit SHA is recorded) unless `--allow-dirty` is
given. Each run writes `results/<UTC timestamp>_<commit>_<label>/`, which is never
overwritten and is ignored by Git: publish it as a CI artifact or a release asset rather
than committing it. Results recorded before 31 October 2026 are preserved at the archive
commit listed in the [archive index](../docs/archive-index.md).

- `environment.json`: commit, dirty flag, Python, platform, CPU model and count, RAM,
  corpus manifest digest, full protocol and command line;
- `results.jsonl`: one row per (circuit, workload, backend) with every repetition time,
  status (`ok`, `resource_limit` with the refused resource, `timeout`, `error`,
  `wrong_verdict`, `unsupported`), generation time, `tracemalloc` peak, worker RSS, backend
  counters (conversions, ZDD nodes, `auto-zdd` switch gate) and an output fingerprint;
- `REPORT.md`: tables per workload, paired speedups against `sparse-copy` (the archived
  `copy_set`) per split with `c2_181` reported separately, memory, and the comparison with
  the historical handoff numbers in `historical/handoff_2026-10-27.json`;
- `SHA256SUMS`: digests of the files above; `tests/test_corpus.py` checks any local run.

Every harness (`run.py`, `roadmap_campaign.py`, `hmr_qualification.py`) records the same
machine description from `benchmarks/environment.py`.

Workloads: `simulate` (symbolic outputs), `equiv` (against a variant built only from sound
rewrites, expected equivalent) and `nonequiv` (against the circuit with one inserted MCX
gate, which can never be equivalent). A wrong verdict or a disagreement between backends is
reported at the top of `REPORT.md`.

## Interpreting results

Python-only timings on one machine. They compare representations implemented in the same
language; they say nothing about native tools (CUDD, PolyBoRi, MQT QCEC), which need a
matched semantic contract and their own measurements (issue #5). Medians under 1 ms are
noisy. A single pathological circuit (`c2_181`) must not be generalized.

## Contextual substitution qualification

The [substitution matrix](substitution_qualification.md) checks 28 separately labeled
classical, relational and coherent substitution obligations, using public sources
and controlled synthetic mutations. These are previously explored QCEC/Qualtran
fixtures and **not** a fresh holdout or an external performance comparison.


## Public Kaggle bilinear KMB agent-evaluation corpus

The separate [VQCC bilinear dataset source and license record](corpus/kaggle_bilinear/SOURCE.md)
documents a **public Apache-2.0 corpus by James Barlow**, its exact archive/manifest/KMB
SHA-256 provenance, independently rederived GF(16)/GF(64) factor candidates, original
evaluator crosschecks, and all-state classical tests. The uploaded archive is pinned;
the Kaggle revision identifier was not independently available. Unlike the 28-case
substitution corpus, this set has **14 real third-party KMB starts**, but it is
**an exposed development benchmark, not a sealed external holdout**. SymQ's new
candidate syntheses use previously published 9/15 bilinear targets; their 14/14
success does not measure a blind agent or the official Kaggle competition score.

Run `python -m pytest -q tests/test_kaggle_bilinear.py` and
`python -m benchmarks.kaggle_bilinear_eval --output /tmp/kaggle.json --candidate-dir /tmp/candidates`.

## Reusable GF(2) bilinear lowerings (opt-in)

The [general emitter guide](../docs/guide/bilinear-synthesis.md) explains
`gf2n.emit(strategy="pivot"|"pivot-scheduled")` and exact field-tensor
certification. The default incidence emitter remains unchanged. On the
pinned *public development* Kaggle KMB corpus, the new scheduled lowering
reduces the prior 62/174 CX candidate figures to 30/82 while keeping
the same 9/15 CCX counts and dirty-register semantics. Results from
earlier versions remain historical and should not be relabeled.

## Experimental GF(2^24) rank-99 tower and explicit gate proxy

The independent [GF24 research guide](../docs/guide/gf24-tower-research.md)
documents an exact 99-product GF(16)-tower tensor, the pinned GF24 modulus
`0x100001B`, source and factor fingerprints, an independent integer oracle,
and gate counts against schoolbook and scheduled Karatsuba. The declared
integer cost selector is intentionally opt-in; it does not provide a new
bilinear-rank lower-bound, HMR theorem, guaranteed quantum resource saving,
official Kaggle competition score or a sealed holdout. CI publishes a
machine-readable cost receipt with SHA-256 sidecar.

Run `python -m pytest -q tests/test_gf24_tower.py`, then
`python -m benchmarks.gf24_tower_qualification --output /tmp/gf24.json`.
