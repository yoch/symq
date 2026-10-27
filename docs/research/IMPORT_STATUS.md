# Source archive and import status

Source: user-supplied `anf_corpus_optimization_2026-10-27(1).zip`, root `anf_corpus_optimization_2026-10-27/`. The ZIP is the authoritative original and is kept outside this repository.

## Imported

The archive lives under `research/archive/2026-10-27/` with its original relative tree:

- experimental engines (`src/`), with their 24 tests (`tests/`);
- benchmark scripts and tools;
- the 11-circuit QCEC corpus with its MIT attribution;
- provenance records and historical results.

References to an external private repository were removed; [DERIVATION.md](../../research/archive/2026-10-27/DERIVATION.md) lists every change and the delivered digests of the replaced files. Every measured value is unchanged.

## Verified (`tests/test_research_archive.py`, run in CI)

1. **Integrity.** `MANIFEST.sha256` covers exactly the archived tree (`research/verify_archive.py`).
2. **Archived tests.** The 24 archived tests pass in a separate process. Before derivation, they passed on the delivered tree (Python 3.12) and on the derived tree (Python 3.10 and 3.12).
3. **Ported outputs match the frozen engines.** On the 5 DEV and 6 holdout circuits, symq's `sparse` and `zdd` backends produce the same output polynomials, wire by wire, as the archived `copy_set`, `fast_set`, `zdd` and `auto_zdd` engines (13 066 monomials).
4. **Corpus authenticity.** The archive's own `tools/verify_qcec_sources.py --offline-dir` was run against `benchmarks/corpus/qcec/`. All 11 circuits match the archived Git blob SHA-1 and gate sequences. The corpus re-imported in `benchmarks/corpus/qcec/` is therefore the archive's corpus, at upstream commit `98d6784`.

## Mapping and reproduction

- Archived engine names map to symq backends as listed in [BACKENDS.md](BACKENDS.md).
- Historical timings are compared with new, isolated measurements in [BENCHMARK_FINDINGS.md](BENCHMARK_FINDINGS.md). Archived results stay historical: they are not new measurements and were produced on another machine.

## Not ported

- The GF(2¹²) synthetic laboratory (`src/field_phase.py`, `src/circuits.py`).
- The packed/mixed engines' phase ledger. symq's phase fragment is specified separately in [PHASE_HMR_SPEC.md](PHASE_HMR_SPEC.md).

These parts remain runnable inside the archive only.
