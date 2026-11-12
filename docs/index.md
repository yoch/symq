# SymQ documentation

Start with the [project README](../README.md) for the task-first verifier table.

## Learn

- [Getting started](getting-started.md): installation, the optional native core, `doctor`, a first
  verification and the test markers.
- [Glossary](glossary.md): ANF, ZDD, witnesses, contracts, HMR, O1/O2, channels and instruments.
- [Architecture](architecture.md): the three layers and where correctness is checked.
- [Public demonstration](demo.md): a runnable 6–8 minute walkthrough.

## Guides

The guides follow the three installed layers described in the
[architecture](architecture.md): the maintained core, the opt-in `symq.experimental` API and
the `symq.labs` research modules, which carry no API promise.

### Core

- [Symbolic backends](guide/backends.md): representations, width limits, variable order, block
  verification, native cache and collection.
- [SAT decision engine and relational composition](guide/sat.md).
- [Explicit proof contracts](guide/proof-contracts.md): `verify_explicit` and its theorem names.
- [Resources](guide/resources.md): deadlines, sessions and isolated execution.
- [GF(2^n) multiplier synthesis](guide/gf2n-synthesis.md): bilinear factors, pivot
  emitters, tower factorizations, the 99-product GF(2^24) multiplier and the public KMB corpus.

### Opt-in experimental API

- [Experimental verification API and CLI](guide/experimental.md).
- [Experimental phases](guide/experimental-phases.md): dyadic phases, cyclotomic channels, QCEC.
- [Table-XOR loader contracts, public API](guide/table-xor-public-api.md):
  `symq.experimental.table_xor`, receipts and replay.

### Research (`symq.labs`, no API promise)

- [Choosing an engine and a budget](guide/engines-and-budgets.md): which research check answers
  which question, what each limit counts per engine, reading an `inconclusive`, running a check
  under hard process limits, and what a result does not say.
- [Local channel composition](guide/experimental-composition.md): transcripts, phase debt
  and proof graphs (`symq.labs.channel_composition`).
- [Table-to-loader XOR contracts (research)](guide/table-xor-contract.md): check an emitted
  reversible loader against an independent exact lookup table and source-bound receipt.
- [Boolean-first and shift-diagonal ancilla research](guide/shift-diagonal-ancilla.md): exact
  diagonal retention, coherent HMR promotion and adverse representation boundaries.
- [Backward clean-ancilla proofs (research)](guide/backward-ancilla.md): exact error observables,
  hybrid measurement/feedback, source-bound replay and controlled-expansion limits.
- [Affine dephasing phase derivatives (research)](guide/affine-phase.md): source-bound
  dyadic phase obligations on declared affine coherent supports.
- [Affine derivative basis and cache study](guide/affine-basis-study.md): bounded
  basis selection compared with canonical derivatives and a per-call lift cache.
- [Cut invariant discovery (research)](guide/cut-invariants.md): SAT refinement, fixed-dictionary completeness and source-bound replay.
- [Classical dependency cones (research)](guide/classical-cones.md): pinned backward slices,
  known cut predicates, arbitrary-cut diagnostics, bounded expansion and fresh SAT replay.
- [Contextual rewrites (experimental)](guide/rewrite.md): classical and coherent rewrites at an
  exact span under an explicit contract; the `locate` → `prepare-rewrite` → `rewrite` →
  `replay` workflow, receipts and declared costs. Preparation never proves anything.
- [Resource obligations at a substitution site (research)](labs/site-resources.md):
  conditional local proofs, actual-site clean preparation, borrowed correlations,
  lifetime/return obligations, classical SSA reads and unproved cache relations.
- [Portable classical rewrite bricks (research)](guide/rewrite-bricks.md): pinned
  declarative patterns, resource obligations and mutant examples; fresh proof at every site.
- [Kickmix text hybrid source windows](guide/kickmix-windows.md): exact source-byte SHA,
  physical line provenance and arbitrary prefix classical inputs; no proof.
- [Reusable classical KMX source index](guide/kmx-source-index.md): private disk-backed
  source snapshots, localized windows, versioned dependency cones and strict receipt replay.
- [Kickmix binary v2 source windows](guide/kmb-binary-windows.md): private
  size-capped byte-copy decoder, KMB packet validation, provenance and wire maps;
  no channel or rewrite proof.
- [Portable affine HMR channel certificates](labs/affine-hmr-portable.md):
  solver-free algebraic proof in a strict affine/low-degree grammar with a
  caller-declared coherent support, zero ancillas and forgotten classical records;
  not LRAT and not a general HMR verifier.
- [Functional HMR certificates (research)](guide/channel-certificates.md): one-copy full-channel identities with forgotten measurement outcomes.
- [Table loaders with measurement-based uncomputation](guide/hmr-table-contract.md): the
  finite-table XOR contract for HMR loaders, its branchwise criterion and a bounded checker.
- [Phase quotient certificates (research)](guide/phase-quotient.md): exact modular identities under independently established prefix relations.
- [Program phase differences (research)](guide/phase-delta-binding.md): two dyadic programs proved equal up to a global phase on a prefix image, with an extracted and bound phase difference.
- [KMB resource frontiers](guide/kmb-resource-frontier.md): pure-bit facts and source reservations.
- [Reset-prepared HMR caches](guide/reset-cache.md): bounded signed-column channel proof.
- [Affine resource graphs](guide/affine-resources.md): existing wires, preparation and correlated restoration.
- [Indexed classical substitution plans (research)](guide/indexed-substitution.md): origin-only
  KMX cones and complete windows composed with fresh contextual proofs.
- [Strict classical KMB-v2 indexing (research)](guide/kmb-source-index.md): dependency indexing
  of pinned binary sources in raw coordinates.
- [Shared wide tables and predicate addresses (research)](guide/shared-affine-tables.md):
  shared-column tables with predicate address domains and an explicit preparation helper.
- [Research labs index](labs/README.md): opt-in `symq.labs` guides (streaming Kraus routes,
  nonlinear phase certificates, wide affine targets, phase discovery and factored certificates,
  portable LRAT proofs of factored phase obligations, and the development-only Lean model of the
  Boolean-DAG CNF encoding).

## Reference

- [Stability policy](stability.md): what is kept compatible between releases, the three tiers,
  exit codes and JSON rules.
- [Core API reference](reference/api-core.md): every exported name of the core with its tier
  and signature (generated).
- [Sign-phase HMR specification](reference/phase-hmr-spec.md): semantics, obligations O1/O2 and
  theorems.

## Evidence

Recorded measurements, with their sources and limitations. They describe specific commits and
workloads, not general performance.

- [QCEC corpus findings (27 Oct 2026)](evidence/qcec-findings-2026-10-27.md)
- [External baselines: PolyBoRi, CUDD, MQT QCEC](evidence/external-baselines.md)
- [Automatic strategy](evidence/strategy.md)
- [Performance changes (31 Oct 2026)](evidence/performance-2026-10-31.md)
- [Experimental roadmap status](evidence/roadmap-status.md) and
  [evidence](evidence/roadmap-evidence.md)
- [Public HMR qualification (30 Oct 2026)](evidence/hmr-qualification-2026-10-30.md)
- [Reproducible public-source contextual rewrites (3 Nov 2026)](evidence/2026-11-03-compiler-handoff-seed.md):
  two development families (Veri-Q generator and qsyn benchmark), constrained classical
  source/contract proofs and negative controls; not an independently proved adder.
- [Pinned Qiskit 2.6.1 compiler handoff (3 Nov 2026)](evidence/2026-11-03-qiskit-transpiler-pilot.md):
  actual third-party transpiler output through QASM, SAT and replay; Qiskit itself
  finds both selected rewrites at its usual optimization levels.
- [Qiskit timing qualification](evidence/2026-11-03-qiskit-timing-qualification.md):
  tiny two-case development timings, source and license receipts, no comparative
  speedup or holdout claim.
- [Comparative development pilot (1 Nov 2026)](evidence/comparative-pilot-2026-11-01.md):
  SymQ against MQT QCEC and an independent Kraus oracle on 13 public development cases
- Research checkpoints of 2 Nov 2026:
  [affine target tables](evidence/affine-target-table-2026-11-02.md),
  [nonlinear phase bits](evidence/nonlinear-phase-bits-2026-11-02.md),
  [phase discovery](evidence/phase-discovery-2026-11-02.md) and
  [adaptive phase dictionaries](evidence/phase-adaptive-2026-11-02.md).
- SAT-miter proof pilots of 3–4 Nov 2026:
  [CNF snapshot](evidence/2026-11-03-miter-cnf-pilot.md),
  [source-recomputed LRAT proof](evidence/2026-11-03-miter-proof-c1.md),
  [in-encoding limits](evidence/2026-11-04-bounded-miter-encoding.md),
  [isolated producer](evidence/2026-11-04-isolated-miter-worker.md) and
  [two isolated processes](evidence/2026-11-04-double-isolated-miter.md).
- [Coherent affine-support reset pilot (3 Nov 2026)](evidence/2026-11-03-reset-affine-pilot.md).
- [Research archive index](archive-index.md): material removed from the tree and where to find it.

## Maintainers

- [Releasing](../RELEASING.md): branches, rehearsal, tag, what to do after a bad release
- [Public presentation checklist](maintainers/release-checklist.md) (30 Oct 2026, for demonstrations)
- [Changelog](../CHANGELOG.md)
- [Contextual substitution roadmap (1 Nov 2026)](plans/2026-11-01-substitution-roadmap.md)
- Dated reviews: [independent review of the 3 Nov 2026 wave](audit/2026-11-03-next-wave-independent-review.md)
  and the [integration decision of 4 Nov 2026](audit/2026-11-04-next-wave-integration-decision.md).
- Historical reviewer briefs, kept for provenance:
  [#159–#162](audit/research_159_162.md) and [#169](audit/formal_runtime_169.md).
