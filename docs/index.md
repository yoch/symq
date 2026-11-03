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
- [Table-to-loader XOR contracts](guide/table-xor-contract.md): check an emitted
  reversible loader against an independent exact lookup table and source-bound receipt.
  [Opt-in public API](guide/table-xor-public-api.md): `symq.experimental.table_xor`.
- [Contextual rewrites (experimental)](guide/rewrite.md): classical and coherent rewrites at an
  exact span under an explicit contract; the `locate` → `prepare-rewrite` → `rewrite` →
  `replay` workflow, receipts and declared costs. Preparation never proves anything.
- [Explicit proof contracts](guide/proof-contracts.md): `verify_explicit` and its theorem names.
- [Portable affine HMR channel certificates (research)](labs/affine-hmr-portable.md):
  source-bound solver-free Kraus-scalar proof for a strict affine/output grammar, on a
  caller-declared affine support with zero ancillas and forgotten measurement records; not LRAT.
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
- [Comparative development pilot (1 Nov 2026)](evidence/comparative-pilot-2026-11-01.md):
  SymQ against MQT QCEC and an independent Kraus oracle on 13 public development cases
- [Research archive index](archive-index.md): material removed from the tree and where to find it.

## Maintainers

- [Release checklist](maintainers/release-checklist.md)
- [Changelog](../CHANGELOG.md)
- [Work plan (31 Oct 2026)](plans/2026-10-31-workplan.md)
- [Contextual substitution roadmap (1 Nov 2026)](plans/2026-11-01-substitution-roadmap.md)
