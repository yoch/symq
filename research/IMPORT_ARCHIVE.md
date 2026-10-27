# Import the complete research snapshot

Expected destination: `research/archive/2026-10-27/` containing the original relative tree, 29 files including `MANIFEST.sha256`, plus one separately authored `ARCHIVE_GUIDE.md`.

Preserve original `src/`, `tests/`, `tools/`, `benchmarks/`, `corpus/`, `docs/`, `results/` and `provenance/` directories **without renaming or rewriting their contents**. This includes the third-party QCEC attribution `corpus/LICENSE_QCEC.txt`.

From the archive directory, run `sha256sum -c MANIFEST.sha256` (28 digests checked). Do not mix historical test results with current CI, and do not run potentially expensive experiments as part of routine PR tests.

This PR supplies import documentation only; the individual archived files must be published separately before this ticket may be marked complete. The original user-supplied ZIP is the authoritative source; no network retrieval is a substitute for byte-for-byte matching.
