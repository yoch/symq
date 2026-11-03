# Agent B mission — relational coherent supports and safe reset elimination

**Repository:** `yoch/symq`. **Existing owners:**
[#140](https://github.com/yoch/symq/issues/140) (backward ancilla effect),
[#144](https://github.com/yoch/symq/issues/144) (emitted table source contract),
[#100](https://github.com/yoch/symq/issues/100) (real-workload qualification).
[Coordination #179](https://github.com/yoch/symq/issues/179).
**Historical starting main:** `766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc`.
Re-read current refs, tests and AGENTS.md. Never depend on a private repo.

## Specific obstacle

The repository already has:
`src/symq/labs/anchored_stream.py` (eliminate provably irrelevant events),
`affine_table.py` (target constraints as an injective affine image),
`hmr_table_contract.py` (bounded necessary-and-sufficient branchwise oracle),
`channel_composition.py` (dirty quantum frame), and the experimental
`HybridProgram` plus independent exact density/Kraus calculations.

A circuit with many *provably clean* resets should not trigger enumeration of
all hypothetical reset outcomes. A genuine non-clean reset **cannot** simply
be erased, and a measured input-dependent outcome cannot be forgotten if it
carries distinguishing information. A Boolean value proof is not an arbitrary
channel or instrument proof.

## First mathematical contract

Let `P` denote the projector on an independently proved coherent legal input
span. Let `Φ` be the CPTP prefix up to a proposed reset of wire `q`, and
`Q_1 = |1⟩⟨1|_q ⊗ I` the local error projector.

Prove the exact obligation `P Φ*(Q_1) P = 0`, or an explicitly equivalent
source-bound exact statement, for all admissible density operators on that
span. This is the Heisenberg-picture zero-error condition; by positivity it
certifies zero population in `|1⟩` and implies the output qubit is in a clean
`|0⟩` factor (including external-reference coherence). Only **then** may
a reset-known-zero be erased or its outcome branch fixed.

Beware: a mere diagonal Boolean test is sufficient only when the selected
fragment's exact basis/Kraus structure justifies its coherent extension.
For other circuits use a complete coherent check or return unsupported.

## Experiments

**B0: theorem, oracle, error-mutant.** Choose a closed, documented subset of
X/CX/CCX/MCX, phase signs, HMR, Z-measure, classical control and reset. If one
gate type requires unsupported semantics, refuse it explicitly. For width <=5
quantum wires check every admitted `|x⟩⟨y|` with an independent Kraus/density
oracle. Include clean and dirty borrowed registers, false preparations,
entangled input, omitted/doubled phase correction and a reset of a nonzero wire.

**B1: relational support.** Build supports of the form `z = c ⊕ B u` with
independently validated GF(2) rank and a source-bound proof of reachability.
Never assume a named set of 35 independent bits makes an arbitrary 40-bit
state legal without checking the actual domain. Distinguish actual physical
target width from independent parameter rank and from the HMR table checker
that currently caps targets to 12 bits. Reuse `affine_table` rather than
enumerating `2^35` target values.

**B2: reset factorization and guards.** Compare a forward affine/Boolean
prefix analysis with backward error-projector propagation (#140). For each
reset report one of `proved_clean`, `proved_nonclean`, `inconclusive`,
`unsupported`, with source/event identity and a replayable checked obligation.
A failed sufficient proof does not imply a non-clean reset. Count actual
symbolic nodes/terms/queries and prevent hidden branch enumeration.

**B3: synthetic stress shape.** Construct repository-owned deterministic
circuits with **40 physical target wires, 35 independent target coordinates
and 89 reset sites** (not a claimed real compiler proof). Start with a family
where each reset is actually provably clean; vary number of resets (0, 8, 16,
32, 64, 89) and show resource curves. Mutate a selected site to be genuinely
nonclean and a phase event to change coherence while leaving basis outputs
unchanged. A test that merely raises width caps or accepts a declared contract
without checking its origin does not count.

If current models do not support the shape, produce a smaller valid theorem
plus an exact capacity blocker; do not fake 40-bit success. Work out whether
independent target/measurement factors can be quotient out without loss of
coherence; source identity and outcome-event SSA must remain immutable.

**B4: cost and evidence.** Compare `anchored_stream` and `affine_table` on the
same supported theorem, including preparation, branch reduction, proof and
fresh replay. Record wall/CPU/RSS, accepted/refused counts and >=15 paired
repetitions on feasible representative cases. A negative ROI result is
acceptable.

## Acceptance and boundaries

- No false positive under the independent small coherent oracle.
- A clean reset can be removed only with a checked source-bound proof.
- Any unproved nonclean reset, future/out-of-scope outcome, alias, observed
  instrument record or exhausted resource is refused or inconclusive, never
  upgraded to equivalent.
- Borrowed dirty qubits require full coherent identity on the retained frame;
  output equality only on computational basis is insufficient.
- New code, if justified, remains `symq.labs` in its own Draft PR.
- No default-engine/API promotion, generalized HMR guarantee, private fixture
  or merge without maintainer authorization.

Background: [Hoare meets Heisenberg](https://doi.org/10.22331/q-2026-07-23-2172),
[compile-time simplification of dynamic control](https://arxiv.org/abs/2605.28439).
These are prior-art design references, not license to import unchecked theorems.
