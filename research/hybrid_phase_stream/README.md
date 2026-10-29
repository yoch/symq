# Strict phase-stream importer — independent research pilot

A standalone, explicit compiler into **existing** sign-phase/HMR semantics.
No third-party runtime, private fixtures, external imports or default changes.
Research issue [#85](https://github.com/yoch/symq/issues/85) describes
the subsequent typed hybrid IR and full channel semantics.

## Accepted source vocabulary

The opt-in `parse_phase_stream(text, data=..., ancillas=...)` handles:

- Quantum value: `X`, `CX`, `CCX`, `SWAP`, `CSWAP` (last two
  decomposed exactly to existing CX/CCX).
- Sign phase: `Z`, `CZ`, `CCZ`, `NEG`, with optional `if bN`
  or `if !bN`. A classical XOR guard is split into a *product* of
  independent sign corrections; no approximation.
- X-basis measurement **and reset to |0>**:
  `HMR qN bM`. Each call introduces an immutable fresh measurement
  event, even when `bM` overwrites an earlier storage slot.
- Classical outcome registers: `BIT_STORE0/1 bN`, `BIT_INVERT bN`,
  `BIT_INVERT bN if bM`, `OXOR b_dest b_source`. Destinations must
  already be initialized for modification, unlike some permissive
  external text languages.
- `R qN` only after a **conservative static proof** that qN is
  already |0> for every input and outcome. Then reset is the
  *identity channel* on that wire; no semantic erasure of a dirty qubit.

The importer returns an ordinary `PhaseProgram`, not a new quantum
semantics, and is checked by the independent state-vector oracle. The
importer does **not** certify a full channel directly.

## Example — one temporary AND erased by HMR

```python
from importer import parse_phase_stream
from symq.phase import PhaseProgram, check_phase_equivalence

source = """
CCX q0 q1 q3
CX q3 q2
HMR q3 b7
R q3
CZ q0 q1 if b7
"""
candidate = parse_phase_stream(source, data=3, ancillas=1)
reference = PhaseProgram(3, 1).ccx(0, 1, 2)
assert check_phase_equivalence(candidate.program, reference).equivalent
```

To use this *research-only* module, put `research/hybrid_phase_stream` on
Python's module search path. The example uses the local name `importer`.

## Deliberately rejected

General H, Z-basis measurement, phase rotations, arbitrary gates,
quantum-value writes conditioned on measurement bits, PUSH/POP scopes,
metadata/register declarations, future/undefined classical bits,
nonlinear Boolean classical guards, and true reset of an unproven-zero
or entangled qubit. **These are unsupported**, not a failed proof.

In particular, a true reset on a dirty/entangled wire is a CPTP channel:
blindly setting the Boolean value to zero would erase off-diagonal
coherence and could falsely certify a non-equivalent circuit.
An outcome-conditioned X/CX makes value functions depend on outcomes;
it cannot be run through the current outcome-free-output HMR factoring.

## Validation and promotion gate

Run `python -m pytest -q tests/test_hybrid_phase_stream_research.py`.
The suite compares every basis input and measurement branch against the
*independent* state-vector oracle and checks positive/mutated temporary-AND
release, outcome XOR, reused measurement slot, negated conditions, global
sign, SWAP/CSWAP and fail-closed reset/unsupported operations.

This is **K0: useful import coverage**, not arbitrary hybrid quantum
verification. A subsequent milestone needs a typed quantum/classical IR,
explicit full Kraus/density semantics for guarded value updates and
true resets, and a separate full-versus-reduced channel proof contract.
Neither existing strict branch proofs nor performance gains are implied.
