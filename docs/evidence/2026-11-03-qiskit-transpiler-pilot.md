# A1 — actual Qiskit 2.6.1 transpiler input, source receipts and SymQ rewrites

This is a distinct follow-on to the Veri-Q *generator* and DVLab/qsyn
benchmark in `2026-11-03-compiler-handoff-seed.md`. Unlike those existing
seeds, this experiment actually **runs a pinned public transpiler**.

## Reproducible source and licenses

- Compiler: [Qiskit 2.6.1 release](https://github.com/Qiskit/qiskit/releases/tag/2.6.1),
  published 22 October 2026; Apache-2.0, Copyright 2017 IBM and its contributors
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

> **Update (4 Nov 2026, PR #205 at `f8f3fe5`).** The paragraph above records the
> state after A1 (3 Nov). The 15 paired benchmark runs were then delivered by A2
> below. The independent holdout and the two substantial compiler families of
> #180 remain open. The dedicated workflow ran on the #205 head in
> [run 41789683805](https://github.com/yoch/symq/actions/runs/41789683805)
> (artifact 13302009422, 30 timing records, both pins matched).


## A2: full-call isolated measurement harness (additional qualification)

The source generator can now target an individual named compiler case,
allowing `benchmarks/qiskit_rewrite_benchmark.py` to execute **15 randomized
paired repetitions** of both source families in fresh Python subprocesses.
Each observation includes a freshly executed pinned Qiskit transpilation,
strict QASM roundtrip, global context construction, structural preparation,
SAT contextual proof, and fresh proof replay.

The benchmark emits *raw JSONL records* containing source QASM SHA,
theorem/status, gate counts, total startup-inclusive wall-clock time,
in-process wall and CPU time, split compiler/preparation/proof/replay
durations, and Linux process high-water RSS (KiB). This high-water mark
is **not** marginal RSS of one operation. A dedicated CI job persists
the raw 30 observations alongside the source receipts. No arbitrary
wall-clock speedup is claimed: the two tasks differ, the compiler was
run at optimization_level=0, and the optimized candidate was independently
derived. This is primarily a reproducibility/usability benchmark.

The CI run 41702145314 at `3328283` produced these records
(artifact 13263981205); see the timing qualification page. That commit belongs
to the historical #185 branch and is not an ancestor of the squashed #205 commit
`f8f3fe5`, whose own run is 41789683805 (artifact 13302009422). A real independent source/holdout
cohort, matched-baseline comparisons and cross-machine replication
remain future work, with no API promotion authorized.


## Independent audit notes (3 Nov 2026)

- **Qiskit already finds both rewrites.** A fresh `transpile` of the same
  inputs at `optimization_level=2` gives exactly `cx(1,2)` for the first case,
  and at `optimization_level=1` exactly `ccx(0,1,2)` for the second. The
  candidates are therefore not optimizations the compiler misses; this pilot
  qualifies the *handoff and proof path* on real compiler output, not the
  utility of the rewrites.
- `seed_transpiler` has no effect at level 0 (several seeds give identical
  digests).
- The QASM digests `312b1320…5849` and `3269ab93…2e4b` are now pinned in the
  test (checked even without python-sat) and in the workflow, so a change of
  Qiskit lowering fails CI instead of passing a self-comparison.
- Replay re-proves the request embedded in a report; it does not tie that
  request back to the pinned QASM. Three guarantees are distinct: (1) the
  proof of the embedded request, (2) its fresh replay, and (3) that the
  request came from a particular external QASM file. Only (1) and (2) are
  provided; `provenance` is copied with `reverified: false`. A consumer that
  needs (3) must, from QASM bytes it trusts: check their SHA-256 against the
  pin, parse them, and require that the report's embedded source block at the
  rewritten span equals the parsed (mapped) block, or rerun `prepare-rewrite`
  from those bytes and compare the request digest. The embedded source is a
  circuit, not QASM bytes, so its digest never equals the QASM pin.
