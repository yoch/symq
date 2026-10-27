# Research archive — 2026-10-27

This directory preserves the user-supplied research handoff verbatim.

- `src/`: original experimental ANF, ZDD and phase engines (not part of the supported `symq` API).
- `tests/`: original tests; run independently from the package suite.
- `benchmarks/`: archived benchmark harnesses.
- `corpus/`: QCEC source fixtures and their original attribution/license.
- `results/`: historical experiment data and logs, **not** newly reproduced measurements.
- `provenance/`: upstream source declarations.
- `docs/`: original handoff documentation.
- `tools/`: original replay, reporting and provenance utilities.
- `MANIFEST.sha256`: SHA256 values for each original archived file (except itself).

From this directory run `sha256sum -c MANIFEST.sha256` to verify all 28 listed payload files. Do not rewrite historical files in-place; port implementations under `src/symq/` with differential tests.
