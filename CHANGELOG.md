# Changelog

All notable changes to SymQ are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). SymQ is experimental: no stable API is
promised before 1.0.

## [Unreleased]

### Added

- `symq.generators.arithmetic`: the Cuccaro ripple-carry adder with an exact integer reference
  (`cuccaro_adder`, `cuccaro_expected_output`, `cuccaro_legal_inputs`).
- `symq.generators.gf2n`: reversible GF(2^n) multipliers (`schoolbook`, `karatsuba`,
  `rank_floor` decompositions) over pinned irreducible moduli up to n = 24, with an integer
  reference (`multiplier`, `multiplier_expected_output`, `gf_mul`, `is_irreducible`).
- `symq.backends.NATIVE_IMPORT_ERROR`, and `symq doctor --require-native`.
- Documentation: index, getting started, glossary, SAT and relational composition guide,
  strategy evidence, research archive index.
- Test capability markers `native` and `sat`, and `SYMQ_TEST_REQUIRE` to turn their skips into
  errors.
- `symq.verify(left, right, theorem=..., engine=...)`: one entry point routing every theorem to
  its owning engine; results satisfy the `symq.Verdict` protocol.
- `symq.errors` with a `SymqError` base for every SymQ exception.
- CLI: `symq check` (classical equivalence from QASM or JSON, optional SAT contract),
  `symq anf` (output polynomials), `symq --version`; exit codes are documented in `--help`.
- `check_phase_equivalence(..., budget=)` and witness replay through the independent state-vector
  oracle.
- `symq.__version__`, readable `str(ANF)`, `Stats.merge()`, `symq.hashing.canonical_sha256`.
- `Budget.max_bytes`: a bound on the native manager's arrays, enforced at every table growth and
  carried through collection; backends that cannot measure their memory refuse it.
- `src/symq/py.typed`; mypy runs in CI on the core package.
- `check_equivalence(..., order=)` / `verify(..., order=)` / `symq check --order`: variable order
  for the ZDD engines, including `"auto"` from the structural rule; `symq check` uses `auto`.
- `symq.kickmix`: strict importer for Qualtran kickmix `.kmx` circuits (classical gates, sign
  phases, HMR and measurement-conditioned phases; everything else refused with its line), with a
  public Apache-2.0 corpus; `symq check` accepts `.kmx` files.
- `linear` backend: affine functions as bit masks, exact and linear-time on X/CX circuits of any
  width (refuses degree two).
- `Contract(assumption=...)`: SAT preconditions as Boolean expressions over the inputs (affine
  relations, finite domains), with witness replay against them.
- `symq.ReferenceChecker`: one reference simulated once, many candidates checked in the same
  algebra (7-15x faster than independent checks in a measured search loop).
- `symq doctor --json`: version, ABI, native binary SHA-256 and per-file source SHA-256.
- `Circuit.counts()` and `KmxProgram.counts()` with Toffoli-like totals.
- `python -m benchmarks.quick`: in-process regression benchmark with a `synthetic` family
  (adders, dense random circuits) and `--compare`.
- CI jobs for macOS (native core required), type checking and sdist installation.

### Changed

- `symq doctor` exits with code 0 in pure-Python mode, labels `zdd-native-wide` as native and
  reports why the native core could not be loaded (for example a stale ABI).
- `symq.generators` is now a package; existing imports are unchanged.
- Research modules without an API promise moved from `symq.experimental` to `symq.labs`:
  `classical_transcript`, `composition` → `channel_composition`, `cyclotomic`, `importers`,
  `ledger`, `phase` → `dyadic_phase`, `proof_graph`, `qasm3`, `qcec` → `qcec_adapter`, `qualtran`,
  `rename`. The old module paths still import, with a `DeprecationWarning`.
- The remaining research modules graduated into the installed `symq.labs` package (`xag`,
  `bitset_anf`, `finite_domain`, `linear_certificate`, `hmr_repair`, `verification_contracts`,
  `corpus_qualification`); the `research/` directory is gone and its notes are in `docs/labs/`.
- In `symq.labs.dyadic_phase`: `PhaseProgram` → `DyadicPhaseProgram`, `PhaseGate` → `DyadicGate`,
  `PhaseVerdict` → `DyadicVerdict`, `check_equivalence` → `check_dyadic_equivalence`; the `*8`
  aliases are removed.
- `symq.experimental.contracts.BACKENDS` → `CONTRACT_BACKENDS`; `check_full_channel` is removed
  in favour of `check_channel(..., backend=...)`.
- Internal-consistency failures raise `InternalInconsistency` instead of `AssertionError` or a
  bare `RuntimeError`.
- `verify_explicit` accepts a time/term budget for the sign-phase theorems and points full-channel
  requests at the experimental API.
- SAT solvers are probed on first use; `import symq` loads neither the SAT engine nor the external
  baselines.
- The native core enforces `max_terms` on every gate of `simulate` and `simulate_hmr` (previously
  only on export), refuses table growth past the 32-bit id range with `ResourceLimitExceeded`
  instead of wrapping, and has ABI version 6.
- The Python ZDD backend chooses the same minimum-degree witness as every other backend under any
  variable order (ties were broken on levels instead of variables), iteratively.
- `check_sat_equivalence` and `verify_explicit` honour the deadline of an enclosing
  `VerificationSession`; the miter and the composition engine share one deadline-bound solve.
- Receipts, profiles and proof-graph cache entries are written atomically.
- SAT miter: both circuits share their input variables, AND/XOR definitions are structurally
  hashed and X gates are literal negations; about 2× faster on the QCEC splits and 4× on the
  synthetic family, with one recorded regression (see `docs/evidence/performance-2026-10-31.md`).
- Packaging: PEP 639 license metadata, project URLs, classifiers, a lean sdist, `test` and `dev`
  extras built on `sat`; the empty `native` extra is removed. macOS builds link with
  `-undefined dynamic_lookup`.
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
