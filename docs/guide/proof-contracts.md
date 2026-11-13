# Explicit proof contracts for SymQ (issue #81)

**Standalone, opt-in** classical/sign-phase entry point: `from symq.verification import verify_explicit`.

**Status after #122 (ABI 6):** the unified `symq.verify(..., theorem=..., engine=...)` facade
also routes the **installed but experimental** `full_channel`, `reduced_channel`, and `instrument`
theorems through `symq.experimental.verify`. They are **not** supported by
`verify_explicit`. Refer to [the experimental API](experimental.md) and
[local composition](experimental-composition.md) for their supported backends and limits.
This page's table below describes only `verify_explicit`.
No changes to `symq.check_equivalence`, `symq.sat`, `symq.phase`, or the
existing default engines. This module has **no imports from any other project**.

A caller must explicitly supply a **theorem class** and **engine**, rather than
allow an automatic strategy to dispatch a checker onto a different semantic
contract. Every result records the exact normalized input-IR hashes, the theorem,
the selected engine, an optional contract hash, and typed input witness.

| Theorem | Engines | Contract and significance |
| --- | --- | --- |
| `classical_full` | Any registered ANF backend, SAT, optional QCEC | All wires/all assignments; no dirty-wire cleanup requirement by omission |
| `classical_contract` | SAT only | Explicit input constants, observed outputs, restored wires and maps |
| `sign_phase_exact` | `phase-reference` | Strict ±1 phase/HMR obligations O1 and O2 |
| `sign_phase_up_to_global` | `phase-reference` | Same obligations but permits global minus sign |
| `full_channel` | `channel-sat` (reserved) | Explicit **unsupported here**: call `symq.verify` (experimental coherent channel) instead |

The diagonal Z/8 research work is not silently selected by this classical/sign-phase
facade; the installed exact dyadic/cyclotomic reference engines have their own bounded
experimental contracts. See [experimental phases](experimental-phases.md). A future promotion must add a type-safe API and
independent tests, not a string alias that can certify the wrong theorem.

`equivalent` is the ONLY status for which `result.certified` is true.
Other statuses are `different`, `inconclusive`, `unsupported`,
or `precondition_failed` (for O1/O2). A failed prerequisite is not a
counterexample to a promised unitary transformation.

`result.equivalent` is `True` only for `equivalent`, and `result.different` only for
`different`. `not result.equivalent` is therefore **not** a proof of difference: it is also true
for `inconclusive`, `unsupported` and `precondition_failed`. Branch on `result.outcome`, or on
`result.different` when a difference is what matters.

### Safety / runtime notes

- Unsupported gates fail at the existing validated IR boundary; unknown theorem
  and mismatched IR/engine pairs raise explicit errors.
- SAT `equivalent` is relative to the checked CNF encoding, with no external
  LRAT proof. A SAT `different` witness must be concretely replayed.
- QCEC is optional and can return inconclusive. It is used only on the
  **unitary permutation** classical subset, not on measurements or partial outputs;
  it does not provide a counterexample to replay.
- Symbolic resource limits produce `inconclusive`, never a false proof.
  Term/node budgets are rejected for SAT/QCEC; time budgets are **not**
  silently passed into the unbudgeted sign-phase engine.
  The same rejection applies to `symq check --engine sat --max-nodes` and
  `--max-terms`, including `--observe`/`--restore` contracts: the command exits 3
  without a verdict. Use `--timeout` for the SAT deadline.
- Experimental channel and Z8 work (#83, #82) remains isolated until independently
  promoted. No private fixture or private dependency.

### Example

```python
from symq import Circuit
from symq.sat import Contract
from symq.verification import verify_explicit

result = verify_explicit(
    Circuit(3), Circuit(3).x(2),
    theorem="classical_contract", engine="sat",
    contract=Contract(observed_outputs=(0, 1)),
)
assert result.certified  # this DOES NOT establish equality of wire 2
```

### Acceptance

`python -m pytest -q tests/test_verification_portfolio.py`

Tests cover partial vs full semantic separation, dirty-wire restoration,
cooperative SAT timeout, sign-phase global-phase distinction, cleanup violations,
unsupported H/T, solver absence, fingerprint drift and invalid budget combinations.
