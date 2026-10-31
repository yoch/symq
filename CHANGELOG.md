# Changelog

All notable changes to SymQ are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). SymQ is experimental: no stable API is
promised before 1.0.

## [Unreleased]

### Added

- `symq.generators.arithmetic`: the Cuccaro ripple-carry adder with an exact integer reference
  (`cuccaro_adder`, `cuccaro_expected_output`, `cuccaro_legal_inputs`).
- `symq.backends.NATIVE_IMPORT_ERROR`, and `symq doctor --require-native`.
- Documentation: index, getting started, glossary, SAT and relational composition guide,
  strategy evidence, research archive index.
- Test capability markers `native` and `sat`, and `SYMQ_TEST_REQUIRE` to turn their skips into
  errors.

### Changed

- `symq doctor` exits with code 0 in pure-Python mode, labels `zdd-native-wide` as native and
  reports why the native core could not be loaded (for example a stale ABI).
- `symq.generators` is now a package; existing imports are unchanged.
- Documentation moved under `docs/guide/`, `docs/reference/`, `docs/evidence/` and
  `docs/maintainers/`; see the [docs index](docs/index.md).
- CI covers Python 3.10–3.14, requires the native core and the SAT solver in the main job, and
  selects pure-Python tests by marker instead of a hand-maintained ignore list.
- Benchmark harnesses share one machine description (`benchmarks/environment.py`) and run as
  modules (`python -m benchmarks.run`).

### Removed

- Research prototypes, recorded benchmark results and dated audit reports from the tree. They
  remain byte-identical at commit `d18e0183`; see the [archive index](docs/archive-index.md).
- Tests and workflows that audited code on other branches by fetching pinned commits.

## [0.1.0] — 2026-10-30

First public state, developed between 27 and 30 October 2026.

### Classical verification

- Exact ANF algebra with interchangeable backends (`reference`, `sparse`, `zdd`, adaptive,
  packed, truth table) and an optional native C ZDD core (64 variables, explicit 128-variable
  wide mode).
- `check_equivalence` with concretely replayed witnesses; `check_equivalence_by_blocks` for
  circuits whose joint interaction graph is disconnected.
- Strict reversible OpenQASM 2/3 import.
- Optional SAT decision engine with explicit contracts and relational composition.
- Pinned MQT QCEC corpus (MIT) with fixed development, holdout and extension splits.

### Experimental quantum extensions

- Sign-phase programs with X-basis measure-and-reset and the strict O1/O2 branch checker.
- Full and reduced channel, observed instrument, coherent domains and prepared references.
- Bounded exact hybrid Kraus oracle, dyadic and cyclotomic phases, optional QCEC adapter.
- Transcript-bound local composition, phase-debt ledger and replaying proof graphs.
- Installed CLI: `inspect`, `verify`, `profile`, `replay`, `doctor`.

### Audits integrated before 0.1.0

- **Independent audit of `5bfd6f0` (27 Oct).** Fixed: unvalidated `PhaseProgram.ops`, packed
  products materialised before budget checks, QCEC timing that included conversion, silently
  accepted OpenQASM `include` directives, miscounted `Stats.products`, `--allow-dirty` runs
  without a recorded patch, and a mutable `ANF(set)`. Regression tests live in
  `tests/test_audit_regressions.py`.
- **Corrective integration audit of PRs 106–112 (29 Oct).** Fixed: deadlines lost twice in block
  and transcript checks, worker results reconstructed outside the hard wall-clock limit,
  zero-coefficient phase terms dispatched before normalisation, and a seven-wire hybrid
  inspection that claimed support. The independent assertions run as ordinary tests in
  `tests/test_stack106_112_adversarial.py`.
- **Import of the 27 Oct 2026 ANF/ZDD handoff.** The archived engines' output polynomials matched
  `sparse` and `zdd` on the 11 DEV and holdout QCEC circuits; the GF(2¹²) laboratory and the
  packed phase ledger were not ported.

[Unreleased]: https://github.com/yoch/symq/compare/d18e0183f8a3279e79757ffd75bd285da5323bb3...HEAD
[0.1.0]: https://github.com/yoch/symq/tree/d18e0183f8a3279e79757ffd75bd285da5323bb3
