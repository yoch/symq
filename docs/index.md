# SymQ documentation

Start with the [project README](../README.md) for the task-first verifier table.

## Learn

- [Getting started](getting-started.md): installation, the optional native core, `doctor`, a first
  verification and the test markers.
- [Glossary](glossary.md): ANF, ZDD, witnesses, contracts, HMR, O1/O2, channels and instruments.
- [Architecture](architecture.md): the three layers and where correctness is checked.
- [Public demonstration](demo.md): a runnable 6–8 minute walkthrough.

## Guides

- [Boolean-first and shift-diagonal ancilla research](guide/shift-diagonal-ancilla.md): exact
  diagonal retention, coherent HMR promotion and adverse representation boundaries.
- [Backward clean-ancilla proofs (research)](guide/backward-ancilla.md): exact error observables,
  hybrid measurement/feedback, source-bound replay and controlled-expansion limits.
- [Affine dephasing phase derivatives (research)](guide/affine-phase.md): source-bound
  dyadic phase obligations on declared affine coherent supports.
- [Affine derivative basis and cache study](guide/affine-basis-study.md): bounded
  basis selection compared with canonical derivatives and a per-call lift cache.
- [Symbolic backends](guide/backends.md): representations, width limits, variable order, block
  verification, native cache and collection.
- [GF(2^n) multiplier synthesis](guide/gf2n-synthesis.md): bilinear factors, pivot
  emitters, tower factorizations, the 99-product GF(2^24) multiplier and the public KMB corpus.
- [SAT decision engine and relational composition](guide/sat.md).
- [Cut invariant discovery (research)](guide/cut-invariants.md): SAT refinement, fixed-dictionary completeness and source-bound replay.
- [Classical dependency cones (research)](guide/classical-cones.md): pinned backward slices,
  known cut predicates, arbitrary-cut diagnostics, bounded expansion and fresh SAT replay.
- [Table-to-loader XOR contracts](guide/table-xor-contract.md): check an emitted
  reversible loader against an independent exact lookup table and source-bound receipt.
  [Opt-in public API](guide/table-xor-public-api.md): `symq.experimental.table_xor`.
- [Contextual rewrites (experimental)](guide/rewrite.md): classical and coherent rewrites at an
  exact span under an explicit contract; the `locate` → `prepare-rewrite` → `rewrite` →
  `replay` workflow, receipts and declared costs. Preparation never proves anything.
- [Resource obligations at a substitution site (research)](labs/site-resources.md):
  conditional local proofs, actual-site clean preparation, borrowed correlations,
  lifetime/return obligations, classical SSA reads and unproved cache relations.
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
- [Explicit proof contracts](guide/proof-contracts.md): `verify_explicit` and its theorem names.
- [Functional HMR certificates (research)](guide/channel-certificates.md): one-copy full-channel identities with forgotten measurement outcomes.
- [Table loaders with measurement-based uncomputation](guide/hmr-table-contract.md): the
  finite-table XOR contract for HMR loaders, its branchwise criterion and a bounded checker.
- [Resources](guide/resources.md): deadlines, sessions and isolated execution.
- [Experimental verification API and CLI](guide/experimental.md).
- [Experimental phases](guide/experimental-phases.md): dyadic phases, cyclotomic channels, QCEC.
- [Phase quotient certificates (research)](guide/phase-quotient.md): exact modular identities under independently established prefix relations.
- [Program phase differences (research)](guide/phase-delta-binding.md): two dyadic programs proved equal up to a global phase on a prefix image, with an extracted and bound phase difference.
- [Experimental local composition](guide/experimental-composition.md): transcripts, phase debt
  and proof graphs.
- [Research labs index](labs/README.md): opt-in `symq.labs` guides (streaming Kraus routes,
  nonlinear phase certificates, wide affine targets, phase discovery and factored certificates,
  portable LRAT proofs of factored phase obligations, and the development-only Lean model of the
  Boolean-DAG CNF encoding).

## Reference

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
- [Research archive index](archive-index.md): material removed from the tree and where to find it.

## Maintainers

- [Release checklist](maintainers/release-checklist.md)
- [Changelog](../CHANGELOG.md)
- [Work plan (31 Oct 2026)](plans/2026-10-31-workplan.md)
- [Contextual substitution roadmap (1 Nov 2026)](plans/2026-11-01-substitution-roadmap.md)
