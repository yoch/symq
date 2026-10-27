# Research materials

Historical handoffs are stored under `archive/`, each with a `MANIFEST.sha256`. These are frozen experimental snapshots, distinct from the maintained Python package under `src/symq/`.

- `archive/2026-10-27/`: the ANF/ZDD handoff of 27 Oct 2026. Its original relative tree is kept, with references to an external private repository removed ([DERIVATION.md](archive/2026-10-27/DERIVATION.md)). The delivered ZIP stays the authoritative original.
- `python research/verify_archive.py` checks a snapshot against its manifest and rejects unlisted files. `tests/test_research_archive.py` runs it, along with two more checks:
  - the 24 archived tests, in a separate process;
  - a comparison of the archived engines' output polynomials with symq's on the 11 QCEC circuits.

Do not rewrite archived files in place. Port behaviour into `src/symq/` with differential tests, and keep historical measurements separate from new ones (`benchmarks/results/`).
