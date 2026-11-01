# SymQ documentation

Start with the [project README](../README.md) for the task-first verifier table.

## Learn

- [Getting started](getting-started.md): installation, the optional native core, `doctor`, a first
  verification and the test markers.
- [Glossary](glossary.md): ANF, ZDD, witnesses, contracts, HMR, O1/O2, channels and instruments.
- [Architecture](architecture.md): the three layers and where correctness is checked.
- [Public demonstration](demo.md): a runnable 6–8 minute walkthrough.

## Guides

- [Symbolic backends](guide/backends.md): representations, width limits, variable order, block
  verification, native cache and collection.
- [SAT decision engine and relational composition](guide/sat.md).
- [Contextual classical substitution (experimental)](guide/contextual-substitution.md).
- [Explicit proof contracts](guide/proof-contracts.md): `verify_explicit` and its theorem names.
- [Resources](guide/resources.md): deadlines, sessions and isolated execution.
- [Experimental verification API and CLI](guide/experimental.md).
- [Experimental phases](guide/experimental-phases.md): dyadic phases, cyclotomic channels, QCEC.
- [Experimental local composition](guide/experimental-composition.md): transcripts, phase debt
  and proof graphs.

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
- [Research archive index](archive-index.md): material removed from the tree and where to find it.

## Maintainers

- [Release checklist](maintainers/release-checklist.md)
- [Changelog](../CHANGELOG.md)
- [Work plan (31 Oct 2026)](plans/2026-10-31-workplan.md)
