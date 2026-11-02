# Changelog

All notable changes to SymQ are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). SymQ is experimental: no stable API is
promised before 1.0.

## [Unreleased]

### Added

- Research `symq.labs.shift_diagonal_ancilla`: exact Boolean-first clean-ancilla effects,
  bounded promotion to coherent shift-polynomial operators, independent matrix tests and
  development qualification retaining both controlled-gate gains and adverse parity growth.
  This opt-in prototype provides no portable certificate or replay API.
- Research `symq.labs.backward_ancilla`: exact backward error-observable proofs of one clean
  ancilla in the closed hybrid grammar, source-bound replay, positive-probability witnesses,
  independent coherent-oracle tests and public Qualtran development qualification.
- Opt-in `symq.labs.affine_basis_study` and a reproducible development harness
  comparing complete kernel-basis selection costs with bounded modular-lift
  caching, independent coherent oracles, adversarial budgets and canonical replay.
- Opt-in `symq.labs.affine_phase`: source-bound dyadic phase proofs after a real
  affine dephaser, guarded directional checks, portable replay and development
  qualification against exact coherence oracles and paired sign-channel checking.
- `symq.labs.table_xor_contract`: source-bound exact lookup-table XOR specifications
  for emitted X/CX/CCX/MCX loaders, with legal address/target domains, clean and dirty
  workspace restoration, SAT/exhaustive certification and independently pinned replay.
  This opt-in theorem does not cover HMR or phase-corrected loaders (issue #144).


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
- `symq.labs.phase_quotient`: explicit modular phase certificates and a source-bound prefix
  checker. Conditional algebraic identities are separate from proven prefix assumptions; the
  result concerns the supplied phase polynomial and does not authorize a circuit substitution.
- `symq.labs.phase_delta_binding`: `check_program_phase_difference` proves that two
  `DyadicPhaseProgram`s differ only by a global phase on the image of a frozen reversible prefix:
  outputs by exact ANF composition through the prefix, the phase difference extracted exactly at
  `k = max(k_left, k_right)` and required to equal the certificate's delta, and constancy through
  the unchanged `check_prefix_phase`. Outcomes `proved`, `not_proved` and `inconclusive`; strict
  receipts and `replay_program_phase_difference` with a consumer-pinned constant. No controlled
  substitution is authorized. Qualification: `benchmarks/phase_delta_binding.py`.
- `symq.__version__`, readable `str(ANF)`, `Stats.merge()`, `symq.hashing.canonical_sha256`.
- `Verdict.different` on verification records and results: true only for a proved difference.
  `equivalent` is documented as true only for a proved equivalence, so `not equivalent` is not a
  proof of difference. `different` is a member of the runtime-checkable `Verdict` protocol: a custom result class
  must define it to pass `isinstance(result, Verdict)`.
- `Budget.max_bytes`: a bound on the native manager's arrays, enforced at every table growth and
  carried through collection; backends that cannot measure their memory refuse it. It is not a
  process memory limit (temporary buffers, Python objects and RSS are not counted).
- `src/symq/py.typed`; mypy runs in CI on the core package.
- `check_equivalence(..., order=)` / `verify(..., order=)` / `symq check --order`: variable order
  for the ZDD engines, including `"auto"` from the structural rule; `symq check` uses `auto`.
  Each backend declares the option that takes the order (`Algebra.order_option`).
- `symq check --engine auto` picks `linear` for X/CX-only circuits, then the narrowest native ZDD
  core that holds the width (`zdd-native`, `zdd-native-wide`), then the Python `zdd`.
- `symq.kickmix`: strict importer for Qualtran kickmix `.kmx` circuits (classical gates, sign
  phases, HMR and measurement-conditioned phases; everything else refused with its line), with a
  public Apache-2.0 corpus; `symq check` accepts `.kmx` files. The grammar is closed: names
  with an `_IF` suffix and names that only start like a metadata line are refused, never dropped.
- `linear` backend: affine functions as bit masks, exact and linear-time on X/CX circuits of any
  width (refuses degree two).
- `Contract(assumption=...)`: SAT preconditions as Boolean expressions over the inputs (affine
  relations, finite domains), with witness replay against them.
- `symq.labs.cut_invariants`: opt-in SAT discovery and fresh replay of source-bound Boolean
  cut invariants, complete within a fixed monomial dictionary. Learned predicates still require
  the contextual substitution checker; no automatic rewrite or solver-independent UNSAT proof.
- `symq.ReferenceChecker`: one reference simulated once, many candidates checked in the same
  algebra (an exploratory measurement without raw records; see the performance evidence).
- `symq doctor --json`: version, ABI, native binary SHA-256 and per-file source SHA-256.
- `Circuit.counts()` and `KmxProgram.counts()` with Toffoli-like totals.
- `symq.labs.channel_certificate`: bounded one-copy functional certificates for strict sign/HMR
  full-channel equality, including nonlinear signature dependencies. Failed search means
  `not_proved`; all quantum outputs are retained and all measurement outcomes are forgotten.
- Example scripts for classical checks, SAT contracts, circuit import, search loops and wide
  circuits, each run by `tests/test_examples.py`.
- `python -m benchmarks.quick`: in-process regression benchmark with a `synthetic` family
  (adders, dense random circuits) and `--compare`.
- CI jobs for macOS (native core required), type checking and sdist installation.
- Quick-benchmark records carry raw per-repetition times and a receipt of the measured code
  (commit, clean state, source digest, native binary SHA-256, ABI); `python -m benchmarks.paired`
  summarizes paired rounds and refuses records from different machines, interpreters or
  python-sat versions. A commit is claimed only when git tracks the imported package, and no
  absolute path is recorded. The 31 October records are committed with checksums, their
  measurement-time paths redacted.
- Recorded output digests of the archived engines on the QCEC DEV and holdout circuits, checked
  against `sparse`, `zdd`, `reference`, `auto-zdd` and `zdd-native` (`tests/test_archived_parity.py`).
- Contextual rewrites in `symq.labs` (no API promise), described in the
  [rewrite guide](docs/guide/rewrite.md):
  - `contextual_substitution.check_substitution` proves a classical rewrite at an exact span
    under an explicit contract, with the SAT theorem `classical`, or with `engine=` set to a
    symbolic engine (`packed`, `sparse`, `zdd`, `zdd-native`) for the context-free theorem
    `classical_total`;
  - `hybrid_substitution.check_hybrid_substitution` proves a bounded local coherent channel or
    instrument rewrite, and its receipt records which of the two theorems ran;
  - `rewrite` is the shared core: outcomes, `Weights` keyed by operation name and arity,
    `CostReport`, receipts and `ReceiptMismatch`. Each rewrite is proved once. An `equivalent`
    result carries a private seal over all its compared fields, so only the checker that proved
    it can issue it or attach the rewritten candidate; typed replays refuse a receipt that
    contradicts a decisive fresh result.
- `symq rewrite --engine` (or `"engine"` in a classical request): `sat` by default; `auto`
  picks `linear`, `packed` or `zdd` for the stronger total theorem only when the contract is
  empty, from the actual block and replacement, and SAT otherwise. The choice is pinned in the
  report and recomputed on replay. `linear` joins the total-theorem engines.
- `symq locate SOURCE REFERENCE --theorem classical|coherent`: advisory exact contiguous span and
  injective wire-map discovery (`symq_rewrite_locations`), never a proof or an automatic rewrite.
- `symq rewrite` and the replay of rewrite reports print one `symq_rewrite_cli_result` JSON object
  on every runtime path, including early timeouts (`inconclusive`), invalid input (`invalid`) and
  contradicted reports (`receipt_mismatch`). Verification-artifact replay is unchanged.
- A missing native extension is reported as not installed instead of Python's "partially
  initialized module" wording.
- CLI: `symq rewrite REQUEST.json [--report R.json] [--isolate]` (exit 0 proved, 2 not proved,
  3 invalid input) and `symq replay` for its reports. Reports (schema 2) separate the
  reverifiable request, result, application and candidate from unverifiable provenance; replay
  refuses any stored field that contradicts a decisive fresh proof, and
  `replayed_candidate` is the only way to obtain a report's rewritten stream. `Circuit.to_dict`, `circuit_from_dict` and `load_circuit` read and write the JSON
  circuit format.
- The `not_proved` outcome in the `Verdict` protocol, for checkers that cannot report a proved
  difference.
- GF(2^n) synthesis, described in the [synthesis guide](docs/guide/gf2n-synthesis.md):
  - `gf2n.emit(strategy="pivot"|"pivot-scheduled")`, `certify_decomposition`, `gf2n.tensor`,
    and `gf_mul`/`is_irreducible` for any binary modulus (Rabin test);
  - `gf2n.tower_factors` and `tower_multiplier`: certified 9- and 15-product GF(16)/GF(64)
    factorizations for any irreducible modulus;
  - `symq.labs.gf24_tower`, `gf24_order` and `gf24_choice`: a 99-product GF(2^24) factorization,
    its pinned 2634-CX order and a choice under declared weights;
  - `symq.labs.bilinear_substitution.gf24_rewrite`: a GF(2^24) multiplier rewrite proved on
    every input with the packed engine.
- `benchmarks/corpus/bilinear_kmb`: 14 public GF(16)/GF(64) multiplier circuits (Apache 2.0)
  with their provenance, a strict KMB v2 codec, and `python -m benchmarks.bilinear_kmb`, which
  proves each one equal to the tower multiplier.
- `python -m benchmarks.rewrite_kmb_context`: the classical rewrite of the public `gf16-07.kmb`
  in a 13-wire context with a clean ancilla, qualified through `symq rewrite --isolate` and
  `symq replay` on versioned files, with an independent field oracle and three required refusals.
- `python -m benchmarks.rewrite_qualtran_hmr`: coherent rewrites of public Qualtran
  decompositions, qualified through `symq rewrite --isolate` and `symq replay` on versioned
  request files in `benchmarks/corpus/qualtran/rewrite`, and checked against the independent
  Kraus oracle in `tests/testkit`.
- `python -m benchmarks.comparative`: a development pilot against MQT QCEC and the Kraus oracle,
  with raw records and checksums in `docs/evidence/data/2026-11-01/`.
- One CI job, `research-evidence`, regenerates the rewrite, KMB, GF(2^24) and substitution
  reports and uploads them as artifacts.

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
  `PhaseVerdict` → `DyadicVerdict`, `check_equivalence` → `check_dyadic_equivalence`. The former
  names and the `*8` aliases are deprecated: they still resolve, with a `DeprecationWarning`.
- `symq.experimental.contracts.BACKENDS` → `CONTRACT_BACKENDS`, and `check_full_channel` →
  `check_channel(..., backend=...)`. Both former names are deprecated and still work with a
  `DeprecationWarning`.
- Internal-consistency failures raise `InternalInconsistency` instead of `AssertionError` or a
  bare `RuntimeError`.
- `verify_explicit` accepts a time/term budget for the sign-phase theorems and points full-channel
  requests at the experimental API.
- SAT solvers are probed on first use; `import symq` loads neither the SAT engine nor the external
  baselines.
- `max_terms` means the same on every backend: it bounds each intermediate state of a simulation
  and each `xor`/`product` result, not only the export to `ANF`. This holds for the native core
  (`simulate`, `simulate_hmr`, `xor`, `product`), the Python ZDD and the `linear` backend.
  A circuit whose intermediate states exceed the limit now raises during simulation.
- The native core refuses table growth past the 32-bit id range with `ResourceLimitExceeded`
  instead of wrapping, and has ABI version 6. Rebinding a budget is all-or-nothing: a refused
  `max_bytes` or an already expired deadline leaves the previous limits in force.
- `Algebra.bind_guard` rebinds the algebras a composite backend wraps (`auto-zdd`,
  `adaptive-wire`, `packed-fallback`), so `ReferenceChecker` gives each check a fresh deadline
  on those backends too.
- The Python ZDD backend chooses the same minimum-degree witness as every other backend under any
  variable order (ties were broken on levels instead of variables), iteratively.
- `check_sat_equivalence` and `verify_explicit` honour the deadline of an enclosing
  `VerificationSession`; the miter and the composition engine share one deadline-bound solve.
  The `verify_explicit` deadline starts before validation and hashing.
- Receipts, profiles and proof-graph cache entries are written atomically.
- SAT miter: both circuits share their input variables, AND/XOR definitions are structurally
  hashed and X gates are literal negations. In a paired measurement on one machine with retained
  raw records and receipts, the geometric-mean time ratio was 0.48–0.54 on the QCEC splits and
  0.25 on the synthetic family, with one cell 1.45× slower (see
  `docs/evidence/performance-2026-10-31.md`).
- Packaging: PEP 639 license metadata, project URLs, classifiers, and `test` and `dev` extras
  built on `sat`; the empty `native` extra is removed. macOS builds link with
  `-undefined dynamic_lookup`. The sdist is the tracked repository, and CI runs the test suite
  inside the extracted tarball against the installed package. Provenance tests that need a git
  checkout carry the `checkout` marker and skip there.
- Documentation moved under `docs/guide/`, `docs/reference/`, `docs/evidence/` and
  `docs/maintainers/`; see the [docs index](docs/index.md).
- CI covers Python 3.10–3.14, requires the native core and the SAT solver in the main job, and
  selects pure-Python tests by marker instead of a hand-maintained ignore list.
- Benchmark harnesses share one machine description (`benchmarks/environment.py`) and run as
  modules (`python -m benchmarks.run`).
- `symq replay` dispatches on the report kind (`symq_rewrite` or a verification receipt).
- The benchmark harnesses share `benchmarks.environment.machine()` and `receipt()`; no absolute
  path is recorded.

### Removed

- Research prototypes, recorded benchmark results and dated audit reports from the tree. They
  remain byte-identical at commit `d18e0183`, named by the annotated tag `archive/2026-10-31`;
  see the [archive index](docs/archive-index.md).
- The `research` package: `import research...` no longer works. Modules still under test are
  `symq.labs.*`; the rest are at the archive tag. Historical pull requests #26 and #27 keep their
  ABI 4/5 identities (see the archive index).
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
