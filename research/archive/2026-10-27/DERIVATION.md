# Derivation from the delivered archive

This directory is derived from the `anf_corpus_optimization_2026-10-27` ZIP delivered on
27 Oct 2026. The ZIP stays the authoritative original and is kept outside this repository.
Its own `MANIFEST.sha256` (SHA-256 `e57f90dacf43462c661d203ea58b6fe213f08ebc8cfa494ee4cc0f1a97a54060`,
28 entries) was fully verified before any change.

symq is self-contained, so every reference to, and dependency on, an external private
repository was removed. Nothing else was changed.

## Changes

- Removed a handoff memo addressed to another project's agent (delivered SHA-256
  `ef676a8202057fd9d3130f75398f1ced26ffdb8e56690c4e33a152cad4a3855c`).
- Replaced the replay tool (delivered SHA-256
  `a9b51b091643433e4eb3e86d06b084fa2bb1e925ed55cb4436a673ac18d57adc`) with
  `tools/replay_gate_file.py`. That tool pinned a file and a commit of the external repository.
  The new tool keeps the same differential `run` API, but the caller now supplies the expected Git
  blob SHA.
- `provenance/sources.json`: removed the block describing the external repository.
- `src/circuits.py`: the line-oriented gate-text parser is now `parse_gate_text`.
- The baseline engine label is now `copy_set`, the copy-on-XOR counterpart of `fast_set`. The
  rename applies in code, results, logs and docs. The GF12 synthetic cases are labelled
  `NOT a real-world circuit`.
- Comments, docstrings and prose that named the external project are reworded neutrally:
  `README.md`, `docs/COMPARAISON_EXISTANT.md`, `docs/CORPORA_RECENTS.md`, `src/optimized.py`,
  `src/anf_backends.py`, `benchmarks/run_corpus.py` and `tools/verify_qcec_sources.py`.

## Unchanged

These files are byte-identical to the delivery:

- `corpus/`
- `src/zdd.py`, `src/corpus.py`, `src/field_phase.py` and `src/__init__.py`
- `tests/test_symbolic.py`
- `benchmarks/selector_sensitivity.py`
- `results/selector_sensitivity.json`, `results/quantumsemeval_sample.json` and
  `results/tests_final.log`

Every measured value is unchanged. After undoing the label rename, `results/*.json` and
`results/benchmark_run_v3.log` are equal to the delivered files.

## Checks run on the derived tree

- The 24 archived tests pass: `PYTHONPATH=. python -m pytest -q tests`.
- `PYTHONPATH=. python tools/summarize.py` regenerates `results/summary.json` exactly.
- `tools/verify_qcec_sources.py --offline-dir` was run against a tree built from
  `benchmarks/corpus/qcec/` (the byte-exact upstream files). All 11 circuits match their Git blob
  SHA-1 and their gate sequences.
- `MANIFEST.sha256` lists the derived tree. `python research/verify_archive.py` checks it,
  and so does the repository test suite.
