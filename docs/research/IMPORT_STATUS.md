# Source archive and import status

Source: user-supplied `anf_corpus_optimization_2026-10-27(1).zip`, root `anf_corpus_optimization_2026-10-27/`.

The supplied archive contains experimental modules (`src/anf_backends.py`, `optimized.py`, `zdd.py`, `circuits.py`, `corpus.py`, `field_phase.py`), benchmark scripts, tests, a QCEC corpus with accompanying MIT attribution, source provenance records, and measurements.

**This initial PR is a newly authored minimal library core, not a full import of the archive.** It does not claim to reproduce its 24 tests or historical benchmark results. No archive dataset, results, or external experimental backend is included yet.

The handoff reports: 11 public QCEC circuits, 44 controlled experiments, a ~99× pathological case (`c2_181`), a ~1.25× median improvement for in-place sparse XOR on the remaining ten full circuits, and poor median performance for a Python ZDD backend. These are unverified historical claims, **not new measurements**.

Next migration tasks:
1. Import the exact archived reference engines and regression tests (with historical behavior unchanged), then run tests.
2. Import corpus/provenance records and retain the original QCEC MIT attribution text.
3. Independently verify the upstream per-file hashes before asserting source authenticity.
4. Reproduce historical benchmarks in a recorded environment and distinguish local results from the archive.
5. Incrementally integrate adaptive/ZDD backends only after differential correctness and resource-bound checks.

The initial release must not be described as a complete replacement for the research archive.
