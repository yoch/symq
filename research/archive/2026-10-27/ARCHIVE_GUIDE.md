# Guide to the 27 October 2026 research archive

This file is authored for symq and is **not** part of the original archive
(`anf_corpus_optimization_2026-10-27`, 29 files including `MANIFEST.sha256`).

## What is preserved here

| File | Origin | Path status |
|---|---|---|
| `docs/COMPARAISON_EXISTANT.md` | delivered separately by the author on 27 Oct 2026 | path confirmed by `AGENT_QANT.md` ("Fichiers à consulter") |
| `docs/CORPORA_RECENTS.md` | delivered separately by the author on 27 Oct 2026 | path confirmed by `AGENT_QANT.md` |
| `AGENT_QANT.md` | delivered separately by the author on 27 Oct 2026 | **inferred** (archive root) |

They are byte-for-byte copies; their SHA-256 digests are in `RECEIVED.sha256`. Because
the archive's own `MANIFEST.sha256` has not been delivered, these digests are not yet
cross-checked against it.

## What is still missing

The remaining files of the archive, named in the documents above, include `README.md`,
`MANIFEST.sha256`, `src/anf_backends.py`, `src/optimized.py`, `src/zdd.py`,
`src/circuits.py`, `src/corpus.py`, `src/field_phase.py`, `tests/test_symbolic.py`,
`tests/test_legacy_anf.py`, `benchmarks/run_corpus.py`, `benchmarks/selector_sensitivity.py`,
`results/bench_public_final_v3.json`, `results/selector_sensitivity.json`,
`corpus/qcec_packed.tsv`, `corpus/LICENSE_QCEC.txt`, `tools/replay_qant_fixture.py` and the
`provenance/` records. The original ZIP is the only authoritative source: none of these may
be reconstructed or re-downloaded in its place.

## Verification

```bash
python research/verify_archive.py          # also run by tests/test_research_archive.py
```

Without `MANIFEST.sha256` it checks the received files only. Once the payload is
committed it checks all manifest digests, reports missing files, and fails if a received
file sits at a path or with a digest the manifest does not list. Historical tests and
benchmarks stay out of routine CI.

## How the archive informs the maintained code (without importing it)

- Backends: `sparse-copy`, `sparse`, `zdd`, `auto-zdd`, `packed`, `packed-fallback` and
  `truthtable` reconstruct the archived `qant_set`, `fast_set`, `zdd`, `auto_zdd`,
  `packed_only`, `adaptive` and `truth` from their descriptions
  (`docs/research/BACKENDS.md`, issue #4).
- Corpus: the 11 archived QCEC circuits and their 5 DEV / 6 holdout split are re-imported
  from upstream commit `98d6784176bfeb6ef923d4d0220e8d486dc1982f` with verified Git blob
  SHA-1s (`benchmarks/corpus/qcec/`, issue #3).
- Measurements: the table of `docs/COMPARAISON_EXISTANT.md` is transcribed to
  `benchmarks/historical/handoff_2026-10-27.json` and compared, as ratios, in every
  benchmark report.

Parity of these reconstructions with the archived code remains **unverified** until the
payload is imported and its 24 tests are replayed (issue #2).
