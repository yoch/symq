# A1 — actual Qiskit 2.6.1 transpiler input, source receipts and SymQ rewrites

This is a distinct follow-on to the Veri-Q *generator* and DVLab/qsyn
benchmark in `2026-11-03-compiler-handoff-seed.md`. Unlike those existing
seeds, this experiment actually **runs a pinned public transpiler**.

## Reproducible source and licenses

- Compiler: [Qiskit 2.6.1 release](https://github.com/Qiskit/qiskit/releases/tag/2.6.1),
  published 22 October 2026; Apache-2.0, Copyright 2017 IBM and contributors
  ([Qiskit LICENSE](https://github.com/Qiskit/qiskit/blob/2.6.1/LICENSE.txt)).
- Compiler invocation: `transpile(qc, basis_gates=["x","cx","ccx"],
  optimization_level=0, seed_transpiler=20261103)`, Python 3.12.
- Generator: `benchmarks/qiskit_transpiler_pilot.py`, original operations
  are an actual SWAP–CX–SWAP conjugation and double SWAP + CCX.
- The entire lowered circuit is read from Qiskit's actual transpiled
  `QuantumCircuit.data` and round-tripped through the strict OpenQASM2
  output `qiskit.qasm2.dumps` and SymQ's own parser. Unknown gates, unexpected
  phase or wire count are rejected rather than dropped.
- The compact alternatives (respectively CX and CCX) are **independently
  derived**, not claimed to be output from Qiskit's optimizer, and do
  not depend on its pass settings.

The isolated GitHub Actions workflow
`.github/workflows/qiskit-transpiler-pilot.yml` installs exactly
`qiskit==2.6.1` in CI without adding a runtime or optional-package
dependency. It records deterministic output SHA-256 and gate counts
as a downloadable JSONL artifact.

## SymQ statement and tests

The actual transpiled reversible `Circuit` is embedded at a unique span
inside a larger circuit with unrelated dirty-frame wires. Tests use the
existing `prepare_local_classical` → `run_request` → `replay_report` chain
under a **total** classical contract and the configured SAT backend.
Every legal global computational-basis assignment is compared using
a distinct bit-list evaluator, not SymQ's own Circuit.run.
Because these X/CX/CCX programs are pure basis permutations with no
relative phases, this total theorem also implies coherent equivalence
of the two unitary permutations for the selected examples, but neither
SymQ's general HMR/instrument theorem nor an intended algorithmic spec.

Negative alternatives deliberately remove the actual CX/CCX effect and
must not be accepted. Conversion cost, Python/Qiskit import overhead,
build environment and full proof/replay should be measured separately
before making any performance claims.

## Required qualification

No results are claimed for this workflow before the exact-head GitHub CI
executes and the generated artifact is inspected. Version pinning, stable
QASM and strict SAT test non-skipping are mandatory. This is a tiny
compiler-generated corpus and does **not yet satisfy** the independent
holdout, 15 paired benchmark runs or two substantial compiler families
requested by issue #180. Keep the PR in Draft; no stable API or merge.
