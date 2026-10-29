# Proof-carrying late HMR feedback (research-only, #91)

A **constructive** counterpart to the exact sign-phase/HMR verifier:
given a `PhaseProgram` with X-basis measurement/reset and outstanding
measurement-phase debts, produce Z/CZ/CCZ corrections **at the end** of the
program from the quantum values still available there.

## Exact and deliberately narrow theorem

The existing strict `PhaseProgram` outputs are independent of the HMR
outcomes, and its sign phase is affine in each unique event:
```text
phi(x,m) = phi0(x) XOR (m0 & g0(x)) XOR ... XOR (mM & gM(x)).
```
For each outstanding `g_j(x)`, enumerate candidate nonconstant live-wire
products of degree <= `max_arity` (1..3). Solve an **exact GF(2) linear
system** for XOR combinations realizing that debt. Append one classically
conditioned phase gate for each selected combination, then recompute the
complete phase semantics with SymQ's existing independent implementation.
The result is returned only if **all** ancillas are zero, every output
function is unchanged, and the entire residual phase equals the original
measurement-free `phi0(x)`. This proves the strict O1/O2 unitary theorem
within the existing zero-ancilla input assumptions; it does **not** prove
an arbitrary CPTP channel, and it does not choose cost-optimal corrections.

The correction is applied **after** all reversible value operations. No
incorrect commutation of a pending Z phase through a non-diagonal gate
is assumed: the final live functions determine the actual corrected
phase. If the available live products cannot span a debt, the solver
refuses. An outcome-only global sign is deliberately not regarded as
strict branch equivalence without a constant-1 live correction wire.
A non-clean ancilla is also rejected. The HMR events are immutable and
separate from mutable classical storage names of future hybrid grammars.

Use:
```python
p = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
m = p.hmr(3)
repaired, proof = synthesize_feedback(p, max_arity=2)
assert repaired.measurements == 1
proof.assert_fresh(p, repaired)
```

## Native option and boundaries

`audit_backend="zdd-native"` is an **explicit, optional C/ZDD audit of
the Boolean coefficient equations** on data inputs. It is not a native
quantum-channel solver and is not used automatically if the extension
is absent. Core phase propagation and the GF(2) span solver currently
run in Python; CPython's bigint elimination is native arithmetic.
The pilot pre-limits program size, candidate count and recorded term
count; the existing `phase_semantics` construction itself is not
preemptible by a hard timeout. Keep workloads small until a budgeted
engine is independently reviewed.

A receipt pins the before/after IR hashes, event count, correction
selection, base phase and audit backend; `assert_fresh` rejects
post-proof mutation. This is provenance, **not** a self-verifying
external proof certificate.

Tests: `pytest -q tests/test_hmr_feedback_research.py`. Test the
correct AND erasure and an intentionally missing CZ, delayed correction
past a noncommuting CX, wrong/insufficient arity, uncorrectable global
phase, dirty ancilla, random small circuits and replay on every data
input and outcome against SymQ's independently written Kraus branch
interpreter. Native-audit behavior is explicitly opt-in.

**No performance advantage claimed**; promotion needs independent,
redistributable real HMR fragments, complete CPU/RSS measurements,
mutation-resistant proof receipts and a strict physical import contract.
