# Explicit proof contracts for SymQ (issue #81)

**Standalone, opt-in** API: `from symq.verification import verify_explicit`.
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
| `full_channel` | `channel-sat` (reserved) | Explicit **unsupported**: research-only #83 is not installed |

The diagonal Z/8 proof engine in #82 is likewise *research-only*, not silently
available in this facade. A future promotion must add a type-safe API and
independent tests, not a string alias that can certify the wrong theorem.

`equivalent` is the ONLY status for which `result.certified` is true.
Other statuses are `different`, `inconclusive`, `unsupported`,
or `precondition_failed` (for O1/O2). A failed prerequisite is not a
counterexample to a promised unitary transformation.

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
- Experimental channel and Z8 work (#83, #82) remains isolated until independently
  promoted. No private fixture, no qant imports, no Kaggle dependency.

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
