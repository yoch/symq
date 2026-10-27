# Research archive — 2026-10-27

This directory preserves the research handoff of 27 Oct 2026. It differs from the delivered ZIP
only where references to an external private repository were removed; see
[DERIVATION.md](DERIVATION.md).

- `src/`: original experimental ANF, ZDD and phase engines (not part of the supported `symq` API).
- `tests/`: original tests; run independently from the package suite.
- `benchmarks/`: archived benchmark harnesses.
- `corpus/`: QCEC source fixtures and their original attribution/license.
- `results/`: historical experiment data and logs, **not** newly reproduced measurements.
- `provenance/`: upstream source declarations.
- `docs/`: original handoff documentation.
- `tools/`: replay, reporting and provenance utilities.
- `MANIFEST.sha256`: SHA-256 of every file in this directory except itself.

From this directory, run `sha256sum -c MANIFEST.sha256`. Alternatively, run
`python research/verify_archive.py` from the repository root; it also rejects unlisted files.
Run the archived tests with `PYTHONPATH=. python -m pytest -q -p no:cacheprovider tests`.
Do not rewrite historical files in place. Port implementations under `src/symq/` with
differential tests.
