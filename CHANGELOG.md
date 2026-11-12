# Changelog

All notable changes to SymQ are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The compatibility promise
that applies from the first release is the [stability policy](docs/stability.md).

## [0.2.1] — 2026-11-12

A patch release of the 0.2 series. It corrects two defects found by a downstream user, both in
how a computation that cannot conclude is reported; no verdict changes, and no stable interface
changes. It makes no performance claim.

### Fixed

- `symq.labs.shared_table.verify_shared_table` accepted and documented tables of up to 16
  address bits, but the verifier behind it refused anything above 12 with a bare
  `ValueError('table width cap')`, on both backends (reported by a downstream user). A
  well-formed table wider than the verifier supports now returns `status="unsupported"`,
  `obligation="capacity"`, with a reason naming the width and the limit (12 address bits, and
  the verifier's target limit); the guides state 12. The same applies to
  `verify_affine_table`, `anchored_kraus.verify` and `anchored_stream.verify_stream`.
  Malformed contracts still raise, whatever their width: the whole contract is validated
  before its size is compared with the limits.
- A deadline that had already passed when a computation started was reported as a negative
  time limit (`limit -14598.26...`). The Python deadline checks (`Guard`,
  `VerificationSession`) now raise `ResourceLimitExceeded` with a limit of 0 and the hint
  "the deadline had already passed when this computation started"; a positive limit is
  reported exactly, never rounded to 0.

## [0.2.0] — 2026-11-12

### Summary for users of the classical core

0.2.0 is the first release. Most entries below describe research modules of `symq.labs`,
which carry no API promise. What matters to a user of `symq`, `symq.sat`, `symq.backends` and
the commands `check`, `anf`, `doctor`:

- **A compatibility promise**: the [stability policy](docs/stability.md), enforced by a
  recorded snapshot of the public interface.
- **A wrong verdict fixed in the OpenQASM reader**: a `//` inside a block comment could drop
  statements silently. The readers also refuse malformed input they used to accept.
- **Exit codes of the command line**: 1 is reserved for a proved difference; a usage error is
  3 (was 2); an internal error is 4 (was 1, through a traceback).
- **Budgets**: `check_sat_equivalence` honours its deadline while it encodes, not only around
  it. Memory stays unbounded, and `symq.sat.composition` is not covered.
- **The native core**: tested under injected allocation failures (in the sanitizer build) and
  seeded fuzzing; refused, with a clear message, on free-threaded CPython and on Windows.
- **Verdicts compared with an independent checker** (MQT QCEC) in the required CI, on generated
  pairs: agreement on a sample, not a proof.
- **Packages**: binary wheels for Linux and macOS, a pure-Python package elsewhere.
- **Removed**: the deprecated aliases left by the reorganisation of the modules; they were never
  in a released package.

None of this is a performance claim.

### Fixed

- The text importers no longer let internal exceptions escape. `parse_qasm` and `load_qasm` now
  raise only `QasmSyntaxError` or `UnsupportedOperation`: an out-of-range or repeated qubit, a
  zero-width register, a number longer than Python's integer-conversion limit and a file that is
  not UTF-8 were bare `ValueError`s. `parse_kmx`/`load_kmx` are bounded the same way, and
  `parse_circuit` reports deeply nested JSON as a named `ValueError` instead of `RecursionError`,
  and `circuit_from_dict` refuses non-integer gate qubits with `ValueError` instead of letting
  `Gate`'s `TypeError` through.
  Refused OpenQASM statements are prefixed with their line number.
- **Wrong verdict fixed in the OpenQASM reader** (an old defect, not introduced by this release): a `//` inside a
  `/* */` comment removed the closing `*/`, and every statement up to the next `*/` was silently
  dropped, so a file could be reported equivalent to a circuit it differs from. Comments are now
  stripped in one left-to-right pass, and an unterminated block comment is a syntax error. Found
  by an independent review.
- **Narrower accepted grammar** in the OpenQASM and kickmix readers, previously accepted by
  accident: numbers must be ASCII decimal digits (`\d` also matched the digits of other scripts,
  which `int` converted silently), widths and indices are limited to 2^31 - 1, and `ctrl(0) @`
  is refused instead of being read as no modifier. A RevLib `// i` or `// o` annotation written
  with non-ASCII digits is refused as well, not skipped as a comment.

- `check_sat_equivalence` now honours its deadline while the miter is encoded and loaded, not only
  before and after (#193). With a deadline it polls every 64 gates and hands the clauses to the
  solver in chunks of 50 000; an expiry gives `inconclusive` with the size of the partial
  encoding. Input validation still completes first and still raises whatever the budget. Without
  a deadline the clauses, the variables and the single solver construction are unchanged. Memory
  stays unbounded and `symq.sat.composition` is not covered; hard limits still need an isolated
  process.

- POSIX isolated workers no longer lose an exit status when another thread's
  process startup concurrently reaps the same child. Per-child synchronization
  keeps joins within their original deadline and cleanup grace. Termination
  requests blocked by a paused reaper continue in daemon cleanup after that
  grace; an unknown exit status or expired deadline never authorizes a value.

- Native core: `NativeZDDManager.rename` checked that its manager was idle only before converting
  its map. A map given as an iterator could let another thread start a simulation on the same
  manager in between, and `rename` then modified tables that were being reallocated. It now
  checks again after the conversion, like the other methods. Found by an independent review; the
  busy-manager tests now cover all 18 methods and arguments that run Python while converted.
- Native core: `NativeZDDManager.rename_many` raised `SystemError` instead of `TypeError` when
  its roots were not a sequence and its map was an iterator or a mapping (the second argument
  was converted while the first error was pending). Found by the new fuzz of the native
  interface; no result was affected.
- CI: every commit pushed to `main` or a release branch now gets its own run of the required
  workflow. The runs shared one concurrency group per branch; a group keeps one running and one
  waiting run, so a newer push replaced the waiting one, and merges in quick succession left
  the commits in between without a result.

### Added

- **Release workflow** (`.github/workflows/release.yml`). A tag `vX.Y.Z` on `release/X.Y` builds
  the source distribution, a pure-Python wheel and 30 binary wheels (CPython 3.10 to 3.14 on
  Linux glibc and musl, x86-64 and arm64, and macOS Intel and Apple silicon), every wheel from
  the source distribution and every binary wheel tested where it is built; checks that the
  files are exactly one release, each binary wheel with its native core and none requiring a
  newer system than supported (`tools/release_check.py`); installs them with pip on five kinds
  of runner, including where only the pure wheel applies; then publishes to PyPI through
  Trusted Publishing (no stored token, environment `pypi`), attests build provenance and
  creates the GitHub Release from the changelog section. The publishing jobs check the files
  against the checksums the verification recorded, and that the tag still points at the commit
  that was built; they run no code of the repository. A manual run rehearses the same build,
  optionally up to TestPyPI.
- **Nightly workflow** (`.github/workflows/nightly.yml`): on `main` and every release branch,
  the core tier against freshly resolved dependencies, a non-blocking run on the next Python,
  and on Mondays the whole wheel matrix. Publishes nothing.

- **Required cross-check against MQT QCEC.** A new CI job, part of the required `ci-ok` check,
  compares the verdicts of `zdd`, `sparse`, `zdd-native` and the SAT miter with MQT QCEC, an
  independent implementation, on generated pairs (`tests/test_qcec_crosscheck.py`): random
  circuits, also checked against exhaustive execution; Cuccaro adders of 4 to 30 wires with
  sound rewrites and mutants of every kind at random positions; adders of 34 and 50 wires with
  a rewrite and a trailing mutant only, because QCEC's verdict, which the test needs, did not come
  within the test's time limit on harder pairs at that width; gates with 1 to 16 controls; random circuits with up to 12 controls. `zdd`,
  `zdd-native` and SAT must each answer; every `different` is replayed on its witness; the
  translation to QCEC's circuit type is checked gate by gate. In that job a missing QCEC, C
  core or SAT solver is an error; elsewhere the file is skipped with the reason (new `qcec`
  test capability, new `crosscheck` extra bounded to one QCEC minor series). Agreement on a
  sample is not a proof; the comparative campaign with PolyBoRi and CUDD stays advisory.
- **Platforms.** The macOS job now runs the whole core tier instead of seven test files, and a
  new Windows job runs the core tier as pure Python. Both are part of the required check. The
  native build now refuses Windows explicitly instead of trying whatever `gcc` is on PATH (the
  C core is written for GCC and Clang on POSIX systems), so an installation there is pure
  Python without any setting. New pytest option `--collect-tier` collects the modules of one
  tier only, for platforms where the research modules cannot be imported. Windows is declared
  in the package classifiers.

- **Stability policy** ([docs/stability.md](docs/stability.md)), applying from the first release.
  Three tiers: *stable* (the classical core: `symq`, `symq.sat`, `symq.backends`,
  `symq.generators` and the commands `check`, `anf`, `doctor`), *provisional* (14 exported names:
  the sign-phase entry points, the strategy selector, the SAT encoding blocks, four comparison
  backends and their value type) and *no promise* (`symq.experimental`, `symq.labs`, `symq.external`, the other
  commands). It states what a patch and a minor release may change, the exit codes, the rules for
  JSON outputs and what is not part of the interface (messages, the engine `auto` picks, digests,
  performance).
- **API snapshot.** `tests/data/api_snapshot.json` records the public surface of the core
  (exported names, tiers, signatures, dataclass fields and defaults, declared attributes, public
  members, backend and theorem names, arguments of the stable commands, exit code and outcome of
  26 command lines, keys and types of each JSON output). `tests/test_api_snapshot.py` rebuilds it on every run and compares exactly, on
  every supported Python version. `python tools/api_snapshot.py --write` regenerates it
  together with the new [core API reference](docs/reference/api-core.md).
- CI enforces a floor on the branch coverage of the core by the core-tier tests: 85 %, the
  measured 87 % minus two points.

- Research `symq.labs.kmb_affine_resources`: bounded computational-support
  proofs for reclaiming an existing wire with an affine relation to preserved
  parents. Explicit affine preparation and inverse restore the borrowed graph
  and its correlations; source reservations, phase-proof boundaries, full replay
  and inconclusive resource guards stay separate from a substitution authority.
  Resource batches reject cross-resource parents, keeping joint preparation
  compatible while allowing shared parents outside the requested resource set.

- Research `symq.labs.reset_cache`: bounded signed-column proof for a monomial
  replacement with explicit fresh-wire reset and one private HMR result. Both
  branch signs, original classical outputs and pure-zero return are checked;
  replay and independent Kraus matrix-unit qualification remain separate from
  any source splice, allocation, independent certificate or economic claim.
  Complete KMB candidates stage privately and publish exclusively only after
  verification finishes; failed publication never deletes a concurrent output.
  A failed signed-column criterion reports `not_proved`, without claiming
  channel inequivalence from a possibly harmless global phase.
  Candidate replay refuses nonregular files and bounds reads to the freshly
  reconstructed size before checking the complete content hash.

- Optional research `symq.labs.kmb_resource_frontier` proves sufficient pure-bit
  facts at a cut and separate non-use reservations in complete pinned KMB v2
  sources. Arbitrary unwritten inputs remain unknown; conditional writes erase
  facts. Fresh full-source replay, vector budgets and independent scalar/coherent
  oracles accompany the NumPy `source` extra. No allocation, external preparation,
  classical SSA, cache relation or global substitution theorem is issued.

- Research site-resource dossier v2 proves extended reservations only when all
  outside-window operations are disjoint from the leased wire, with separate
  clean-entry and conditional return obligations. Dirty, unknown, interference
  and inconclusive states stay distinct; cache relations still require proofs.

- Research strict KMB-v2 dependency indexing reuses the existing binary layout
  reader and indexed composition rule, with raw coordinates including INFO_TAG
  and reverified operand byte spans. Hybrid/phase/reset/classical-control
  instructions remain unsupported across the complete source. Declared widths,
  including register-only qubits, obey the global wire-index limit.

- Research `symq.labs.indexed_substitution` composes origin-only strict KMX
  cones and complete windows with fresh contextual SAT/restoration proofs.
  Initial correlations outside the cone remain explicit identity inputs.
  Source/request/dependency-pinned plans replay by rebuilding the index; the
  reduced support is never presented as a complete candidate or global cost.

- Research shared-column wide tables combine existing predicate address domains
  with the affine/HMR theorem, while preserving maintained table-XOR limits.
  A separate exact-prefix helper proves address, target-image and clean-workspace
  support under its explicit input domain; loader correctness alone proves no
  surrounding preparation.

- Research contextual rewrites accept `SubstitutionContract.initial_assumption`,
  a closed Boolean predicate on original input wires, conjoined with the existing
  constants. Relational domains survive cut-invariant handoff, local preparation,
  CLI proof and replay; empty domains never authorize candidates. The predicate
  is source-contract-bound, while omission preserves existing receipt hashes.
  This remains a declared classical domain, not a proof of quantum preparation.
- Research `symq.labs.classical_cone`: source-pinned exact backward slices for
  selected classical outputs, known Boolean cut-predicate proofs, bounded
  expansion of arbitrary starting cuts, and fresh SAT replay. Local cut
  counterexamples remain distinct from replayed legal source counterexamples.
  The first API accepts a bounded materialized Circuit and initial constants;
  it adds no large-file index, quantum theorem or automatic rewrite permission.
- Research `symq.labs.site_resources`: a source-bound substitution dossier that
  separates conditional local equivalence from actual-site preparation, resource
  reservation and clean/borrowed restoration. It reuses the coherent transcript
  checker and hybrid SSA, keeps observations and unproved cache relations explicit,
  and reports resource exhaustion as inconclusive. Dossiers never authorize a
  candidate and do not constitute independently checked certificates.
- Compact nonempty address and target predicates for the opt-in phase-free
  table-XOR adapter, with physical wire rebinding, strict version-2 documents
  and fresh replay. Listed-only contract identities remain compatible; a
  shallower exact Boolean lowering removes the former 64-value SAT depth
  limitation. Synthetic 1,220-address and adversarial regressions are included;
  no real-loader performance, wider-output or preparation theorem is implied.
- Research `symq.labs.kmx_source_index`: build an owned, source-pinned disk
  index once and reuse it for localized classical KMX windows and versioned
  dependency cones. It accepts unconditional X/CX/CCX throughout the source,
  rejects other semantics, keeps cut inputs arbitrary, and replays complete
  source/position/mapping/dependency receipts. Handles cannot be reopened from
  untrusted manifests; no prepared-state theorem or 56M-operation qualification
  is claimed.
- Research `symq.labs.rewrite_bricks`: closed, byte-pinned declarative classical
  patterns/replacements with local cut and restoration obligations, explicit
  source/license records, and executable positive/mutant examples. Every site
  supplies its own global input domain and reruns preparation plus contextual
  SAT proof. Saved results never authorize another use; HMR/phase/measurement
  contracts are outside this first grammar.
- Licensed, research-only **public compiler handoff regression**: pinned Qiskit
  2.6.1 transpilation to OpenQASM2, full `locate → prepare-rewrite → SAT
  rewrite → replay`, independent small truth-table checking, source-drift refusal at
  generation (pinned QASM SHA-256), wrong/forged candidate refusals, and a 15-observation-per-task timing artifact.
  Includes two public-source development fixtures (Veri-Q MIT and qsyn
  Apache-2.0) with their complete upstream license notices. These small
  rewrites are already found by standard Qiskit optimization and do **not**
  establish a new optimizer, a production compiler API or performance wins.
  Qiskit remains solely an opt-in CI research dependency.
- Research source-bound Kickmix hybrid windows: `symq kmx-window` reads strict
  text with exact physical line provenance, while `symq kmb-window` reads
  documented binary KMB v2 through a private bounded byte copy (512 MiB
  default). Both require independent SHA-256 provenance and return advisory
  unproved fragments; conditioned gates are admitted only where the hybrid
  interface represents them. The external-audit hardening includes line
  separator/FIFO refusals, canonical JSON receipt replay, packet/metadata
  conformance and prevention of mutable-mmap ABA/SIGBUS.
- Research `symq.labs.affine_hmr_portable`: standalone solver-free algebraic
  channel rechecker for an explicitly affine coherent support and low-degree
  HMR sign phase with fully retained quantum outputs and forgotten classical
  records. No general reset, C39/invsqrt, LRAT or formally verified runtime
  guarantee is implied. Independent audit found no false positive within
  tested supported cases; deadline and typed-receipt hardening included.
- `symq prepare-rewrite` and research `symq.labs.rewrite_prepare` (#135, #173):
  lower a unique, complete local occurrence of a small original block and its replacement to a
  full-width `symq rewrite` request in a new directory. Strictly preparatory: the output is
  `ready_for_proof`, `proved=false`, `candidate_authorized=false`; only `symq rewrite` and
  `symq replay` prove a substitution. Publication never replaces an existing path (exclusive
  `mkdir` and file creation); it is not atomic, and `preparation.json` is an advisory record of
  the emitted hashes. The audit fixed a check-then-`os.rename` race that could silently replace a
  concurrently created empty directory.
- Research LRAT proof path for factored phase obligations (#168, #174):
  `symq.labs.lrat_rup` (standalone positive-hint RUP LRAT checker against a pinned CNF),
  `lrat_export` (untrusted proof-logging producer and DRUP elaboration), `phase_proof_bundle`
  (export and solver-free consumption bound to rebuilt sources) and `lrat_lean` (data-only
  export to Lean's verified LRAT checker). A positive certifies the literal CNF, not the
  source-to-CNF encoding or the quantum semantics. Lean and the reference C checker run in
  research CI only. The audit hardened the Lean qualification against `sorry` warnings and
  forged axiom reports and pinned the gate-lemma statements.
- Development-only Lean model `formal/symq_runtime` (#169, #175): 54 theorems on
  Tseitin clauses, typed acyclic DAG evaluation, unconditional UNSAT soundness of the solver
  query shape, completeness under unique input keys, ripple-carry addition and Boolean
  rewrite identities, with statement contracts (`Contracts.lean`) and a hardened axiom checker
  (`tools/check_formal_axioms.py`). Lean is not a runtime dependency; the Python code is
  tested against the model, not formally refined.

- Research `symq.labs.phase_discovery`, `phase_adaptive`, `phase_separator` and
  `phase_factored` (#163): counterexample-guided discovery of source-bound phase certificates
  with a fixed monomial dictionary, obstruction-guided feature growth (greedy or logarithmic
  halving separators, optional source-monomial seeds) and weighted XORs of products of affine
  signature forms with a strict supplied-certificate checker. Every positive is re-checked
  afresh on the frozen sources; dictionary exhaustion, a missed structural factorization or a
  wrong candidate is never reported as a channel difference. Defaults are unchanged.
- Research `symq.labs.anchored_kraus`, `anchored_stream` and `kraus_graph` (#160): anchored,
  streaming ANF and Boolean-DAG/SAT obligations for HMR-uncomputed XOR loaders;
  `symq.labs.nonlinear_phase_bits` (#161): aggregate supplied phase-bit certificates on
  nonlinear signature fibres; `symq.labs.affine_table` (#162): wide affine target images.
- Opt-in maintained `symq.experimental.table_xor` (also exported from
  `symq.experimental`): the audited finite-table XOR contract checker, byte-identical to the
  former labs engine. `symq.labs.table_xor_contract` remains a compatibility alias whose
  public names are the same objects; private helpers are no longer re-exported there.
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
- Four `affine_basis_study` research methods that reuse modular lifts within one
  proof (`canonical_precompute`, `canonical_complement`, `canonical_split`,
  `canonical_factorized`). They come with an algebra note proving each identity
  (`docs/labs/affine-lift-reuse.md`), labelled generated variations, an untimed
  operation-count companion and the measured results, including negative ones.
  Receipts stay byte-identical to the published checker. Nothing becomes a default.
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
  algebra. No performance claim: the only measurement of it is exploratory, without raw records.
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
- `symq.labs.hmr_table_contract` (research, issue #144): a bounded exact check that a
  `HybridProgram` using HMR uncomputation, phase corrections and classical control implements
  the finite-table XOR isometry on the legal support. Every quantum output is retained and
  every record is forgotten. The branchwise criterion it decides is proved necessary and
  sufficient for that contract. Refusals carry a legal coherence witness. The check is
  qualified against an independent dense oracle (`tests/testkit/table_channel_oracle.py`)
  by tests and by `python -m benchmarks.hmr_table_contract` (dedicated workflow and artifact).
  Contract and program are detached, strictly typed snapshots; deadlines and inherited
  budgets are enforced; see the [guide](docs/guide/hmr-table-contract.md).

### Changed

- The source distribution does not contain `benchmarks/corpus/bilinear_kmb`. The corpus stays
  in the repository; its licence is known from the declared field of its dataset page alone,
  which is not enough to publish it to a package index. The tests that read it carry the new
  `corpus_bilinear` marker: they run in a checkout (CI requires them there) and are skipped,
  with the reason, in a source distribution, where the benchmarks that need it stop with a
  message saying where to get it. CI and the release check refuse an sdist that contains the
  directory.

- Development status "Alpha". 0.2.0 is the first public release; 0.1.0 remains the untagged
  internal baseline.
- The messages for a missing or stale native core (`make_algebra`, the import error of
  `symq.backends.zdd_native`, `symq doctor`) no longer send every user to
  `python tools/build_native.py`, a file that only a source checkout has. A checkout is still
  told to use it; an installed package is told how to rebuild from the source distribution with
  `SYMQ_REQUIRE_NATIVE=1`; Windows is told that the core does not exist there.
- `symq doctor` reports the SAT engine in its text output (it was in `--json` only).
- The native build honours `ARCHFLAGS` on macOS, as wheel builders set it; it was ignored, so a
  cross-architecture build would have produced a core for the host under a wheel tag for the
  target.
- The long description published to a package index is `README.md` with its relative links
  rewritten to the file on GitHub at the tag of the version being built (the default branch for
  a development version); every one of them would be a dead link on PyPI.
  `python tools/pypi_readme.py --check` verifies built distributions, and CI runs it.
- Packaging metadata: wheel matrix declared for cibuildwheel (CPython 3.10 to 3.14, Linux glibc
  and musl, macOS; no free-threaded build, no Windows binary wheel), core metadata version held
  at 2.4.

- **Exit code 1 is reserved for a proved difference.** An exception that no command anticipated
  left through a traceback, and Python's exit status for that is 1, which `symq check` documents
  as "different": a crash could be read as a verdict. Every command now catches it and exits
  with the new code **4** (internal error, with the traceback on stderr). Running out of memory
  exits with 2 (no verdict), and an integer too large for the platform with 3 (input error).
- `symq anf` no longer prints an unversioned JSON object on stdout when a budget runs out. With
  `--json` it prints `{"schema_version": 1, "kind": "symq_anf", "outcome": "inconclusive",
  "reason": ...}`; without it, one line on stderr. The exit code is still 2.
- **A command-line usage error now exits with 3, not 2.** An unknown command, a missing argument
  or an invalid option value used argparse's exit code 2, which SymQ documents as
  "inconclusive"; the help text already said 3. Scripts that treated 2 as "no verdict" are
  unaffected; scripts that tested for 2 to detect a bad command line must test for 3.
- `symq --help` states the tier of each command: `[experimental]` or `[labs, no API promise]`
  before the description of every command other than `check`, `anf` and `doctor`.
- `symq check --json` builds its output from a fixed list of keys instead of every field of the
  verification record. The output is unchanged in this release; a field added to the record later no
  longer appears in the command's JSON unless it is added to that list.

- New cross-engine differential tests (`tests/test_cross_engine.py`): every symbolic backend,
  the SAT miter, the `verify` facade and `symq check` must agree with exhaustive execution on
  Hypothesis-generated pairs; SAT contracts (observed outputs, output maps, restored wires and
  input constants, not assumptions) are compared with their truth-table projection; and
  the native engines are checked on both sides of their 64- and 128-wire limits, where they must
  decide correctly or refuse. No disagreement was found when the tests were introduced.
- Every test now carries one tier marker (`core`, `experimental` or `labs`), set automatically
  from the imports of its module, so `pytest -m core` selects the tests of the maintained
  package. A CI job publishes the branch coverage of the core by those tests (86 % when
  introduced; CI now enforces the floor described under Added). `pytest-cov` joins the `test` extra and the unused
  `slow` marker is removed.
- The native core is no longer built for free-threaded CPython: its concurrent-use guard is only
  safe under the GIL. `tools/build_native.py` reports the reason (and fails when
  `SYMQ_REQUIRE_NATIVE=1`), `_zdd.c` refuses to compile, and the installation falls back to the
  pure-Python backends. The thread model of the native core is now documented in the backend
  guide.
- New seeded fuzz of the native core (`tests/test_native_fuzz.py`), run in the ordinary suite and
  under the sanitizers: 240 random cases compared with the pure-Python ZDD (same polynomials,
  same node count, same refusals under small budgets) and 6 000 random invalid calls of the
  manager's methods.
- The sanitizer build of the native core (`tools/sanitize_native.py`) now also injects allocation
  failures. In that build only, compiled with `-DSYMQ_FAULT_INJECT`, each of the 50 allocation
  sites of `_zdd.c` is made to fail, one allocation at a time and under simulated exhaustion,
  across 21 scenarios: every failure must surface as `MemoryError` and leave the manager usable.
  No defect was found; the package build contains none of the hooks, and a test checks that in
  both builds.
- The `dev` extra holds ruff and mypy to one minor series (`ruff>=0.17.4,<0.18`,
  `mypy>=2.4,<2.5`), so the enforced lint rules no longer change with each tool release.
- CI is split in two workflows. `ci.yml` holds the checks of the maintained package (Python
  matrix, type check, macOS, pure Python, wheel and sdist, sanitizers), also runs on `release/**`
  branches, and ends with an aggregate job `ci-ok` meant to be the single required check.
  `research.yml` holds the research evidence, the external-engine comparisons and the
  informational timings, on `main` and on every pull request. Every GitHub Action is pinned to a full commit SHA, a
  test enforces it on all workflows, and Dependabot keeps the pins current.
- Added `CODE_OF_CONDUCT.md`, issue forms and `CODEOWNERS`.
- Tests that assert a ceiling on real elapsed time now carry a `timing` marker and run in a serial
  CI step instead of under `pytest -n auto` (13 tests, mostly process-isolation limits); a guard
  test fails for an unmarked real-time ceiling. Two SAT-composition tests moved to an injected
  clock, and Hypothesis no longer applies its 200 ms per-example deadline. No test was removed
  or skipped.
- Documentation index regrouped by layer (core, opt-in experimental, `symq.labs` research); every
  guide, evidence page and dated review is now reachable from it or from the labs index. New
  `THIRD_PARTY_NOTICES.md` summarizes the licenses of the redistributed test and benchmark
  inputs, and `examples/README.md` states which layer and extra each example needs. `.gitattributes` disables line-ending
  conversion so SHA-pinned corpus files survive a Windows checkout.
- Every public class, function, method and property of the core (`symq`, `symq.sat`,
  `symq.backends`, `symq.generators`) now has a docstring and a fully annotated signature, and a
  test enforces it. The `Algebra` operations are documented once on the base class.
  `symq.generators` declares `__all__`. No behaviour changes.
- The two French-language working documents (`docs/plans/2026-10-31-workplan.md`,
  `docs/audit/phase_discovery_163.md`) were retired from the tree; the archive index links a
  commit that contains them. Remaining reviewer briefs are labelled as historical.

- Code-review fixes for the `symq.labs` modules added by #141 to #146:
  - `channel_certificate.discover_certificate(degree=0)` still proves pairs whose measured
    functions are all constant, as before; when a non-constant function would need a
    feature it now says that degree 1 or more is needed instead of a generic `not_proved`.
    The dictionary span grows by the new products when a feature is selected instead of
    being rebuilt; the span is the same (no committed benchmark: no speed figure is claimed).
  - `phase_quotient` (and `phase_delta_binding`, which shares its guard): **behaviour change**,
    an omitted budget is now bounded (`max_terms=100_000`, 10 s) like the other labs
    modules; pass `Budget()` explicitly for the previous unbounded behaviour. The default
    also applies to `certificate_to_dict`/`certificate_from_dict`/`verify_phase_identity`
    and, inside a `VerificationSession`, caps a larger session budget unless one is passed.
    `replay_prefix_phase` checks the untrusted receipt's key count, exact keys, types and
    integer/string/array bounds before any proof work; prefix-state term counting is O(1)
    per gate; digests use `symq.hashing.canonical_sha256` (identical bytes); witness replay
    uses `Circuit.run(..., check=...)` with a time check per gate.
  - Core, additive: `Circuit.snapshot()` and `PhaseProgram.snapshot()` rebuild and detach
    every gate or instruction with exact type checks (`cut_invariants`, `phase_quotient` and
    `channel_certificate` use them instead of their own copies), and `Circuit.run` and
    `Circuit.validate` accept an optional per-gate `check` callback. Without it they behave
    exactly as before. Exception classes for deliberately tampered gate fields (reachable only
    through `object.__setattr__`) now come from the snapshot: `discover_cut_invariants` raises
    `TypeError` for non-`int` qubits (was `ValueError`) and `check_prefix_phase` raises
    `ValueError` (was `TypeError`).
  - The affine-phase evidence harness records construction and oracle failures as failed
    trials and always writes its JSON; the backward-ancilla workflow fails when no evidence is
    uploaded.
- A positive phase-certificate answer revoked by a late deadline no longer keeps nested
  `fresh_metrics`, discovered certificate hashes or `checked_bits` (`phase_discovery`,
  `phase_adaptive`, `phase_factored`, `nonlinear_phase_bits`; audit #166).
- `symq doctor` exits with code 0 in pure-Python mode, labels `zdd-native-wide` as native and
  reports why the native core could not be loaded (for example a stale ABI).
- `symq.generators` is now a package; existing imports are unchanged.
- Research modules without an API promise moved from `symq.experimental` to `symq.labs`:
  `classical_transcript`, `composition` → `channel_composition`, `cyclotomic`, `importers`,
  `ledger`, `phase` → `dyadic_phase`, `proof_graph`, `qasm3`, `qcec` → `qcec_adapter`, `qualtran`,
  `rename`. The old module paths are gone (see Removed).
- The remaining research modules graduated into the installed `symq.labs` package (`xag`,
  `bitset_anf`, `finite_domain`, `linear_certificate`, `hmr_repair`, `verification_contracts`,
  `corpus_qualification`); the `research/` directory is gone and its notes are in `docs/labs/`.
- In `symq.labs.dyadic_phase`: `PhaseProgram` → `DyadicPhaseProgram`, `PhaseGate` → `DyadicGate`,
  `PhaseVerdict` → `DyadicVerdict`, `check_equivalence` → `check_dyadic_equivalence`. The former
  names and the `*8` aliases are gone (see Removed).
- `symq.experimental.contracts.BACKENDS` → `CONTRACT_BACKENDS`, and `check_full_channel` →
  `check_channel(..., backend=...)`. Both former names are gone (see Removed).
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
  hashed and X gates are literal negations. The paired measurements made on one machine, raw
  records included, are in the [performance evidence](docs/evidence/performance-2026-10-31.md);
  they are not a performance claim.
- Packaging: PEP 639 license metadata, project URLs, classifiers, and `test` and `dev` extras
  built on `sat`; the empty `native` extra is removed. macOS builds link with
  `-undefined dynamic_lookup`. The sdist is the tracked repository (less one corpus, see the
  entry on `bilinear_kmb` above), and CI runs the test suite inside the extracted tarball against
  the installed package. Provenance tests that need a git
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
- The deprecated aliases that were kept during the `symq.labs` reorganisation. They were the
  names of the untagged 0.1.0 state and were never in a released package:
  - the eleven `symq.experimental` module paths that forwarded to `symq.labs`
    (`classical_transcript`, `composition`, `cyclotomic`, `importers`, `ledger`, `phase`,
    `proof_graph`, `qasm3`, `qcec`, `qualtran`, `rename`);
  - the former names in `symq.labs.dyadic_phase`: `PhaseProgram`, `PhaseGate`, `PhaseVerdict`,
    `check_equivalence` (new names under Changed), and `Program8` → `DyadicPhaseProgram`,
    `Gate8` → `DyadicGate`, `Verdict8` → `DyadicVerdict`, `Symbolic8` → `SymbolicPhase`,
    `Poly8` → `Poly`;
  - `symq.experimental.contracts.BACKENDS` and `symq.experimental.channel.check_full_channel`.
    `check_full_channel` defaulted to the `zdd-native` backend and `check_channel` defaults to
    `zdd`: pass `backend="zdd-native"` to keep the former engine.

  A removed path or name now raises `ImportError` (`ModuleNotFoundError` for
  `import symq.experimental.<name>`) or `AttributeError`. `symq.phase.PhaseProgram` (the core
  Boolean-phase program) is a different object and is unaffected.

## [0.1.0] — 2026-10-30

Internal baseline: the state of the public repository on 30 October 2026, developed between
27 and 30 October. It was never tagged as `v0.1.0` and never published as a package; the first
release is 0.2.0.

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

[0.2.1]: https://github.com/yoch/symq/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/yoch/symq/compare/d18e0183f8a3279e79757ffd75bd285da5323bb3...v0.2.0
[0.1.0]: https://github.com/yoch/symq/tree/d18e0183f8a3279e79757ffd75bd285da5323bb3
