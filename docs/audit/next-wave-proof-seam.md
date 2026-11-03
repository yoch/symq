# Agent C mission — portable source-bound contextual SAT proof seam

**Repository:** `yoch/symq`.
**Owners:** [#167](https://github.com/yoch/symq/issues/167),
[#170](https://github.com/yoch/symq/issues/170),
[roadmap #179](https://github.com/yoch/symq/issues/179).
**Historical base:** `main@766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc`.

## Goal and boundary

Extend the now-integrated portable **formula** proof path beyond factored-phase
certificates to **one actual classical contextual rewrite** and establish a
source-bound SAT/CNF-to-claim chain.

Existing components: `src/symq/sat/{miter,encoding,composition,_solve}.py`,
`symq.labs.contextual_substitution` / `rewrite_request`,
`symq.labs.lrat_{rup,export}.py`, `phase_proof_bundle.py`,
`formal/symq_runtime` and `formal/portable_lrat`.

A valid RUP/LRAT refutation proves **the pinned CNF is UNSAT**. It does not
automatically prove that the source circuit, cut-domain, output preservation,
borrowed wire and high-level quantum semantics are correctly reduced to that
CNF. The Python LRAT checker is not formally verified. Keep this distinction
on each result object and in every guide.

## Milestones

**C0 — frozen obligation and CNF seam.**
Choose one syntactically nontrivial source-local rewrite where the cut
contract matters. Freeze both source streams, span, mapping, all input
conditions, observed output/restored wires, namespace, selector theorem,
gate-order normalization and resource budget. Authenticate every assumption
as an explicit CNF clause, no external unstated solver assumptions. Design a
versioned canonical `SourceObligation` or equivalent only if it avoids a
duplicate representation already in SymQ.

Read and verify the existing SAT encoding; if it does not provide a
deterministic export of the *exact proved miter*, add a narrowly owned
snapshot/export step. Different encoding or hidden SAT assumptions require
source requalification, not a byte hash copied from producer output.

**C1 — unchecked producer, independent checker.**
Use the existing standard-library strict RUP/LRAT checker on the externally
pinned deterministic CNF. Untrusted SAT solver and DRUP elaboration produce
hints. Unsupported RAT-only/deletion or excessive resource must return
unsupported/inconclusive without a positive source verdict. Consumer reruns
source validation, rebuilds the actual CNF from the trusted input, matches
exact bytes/algorithm version and checks LRAT without importing PySAT.

**C2 — theorem bridge.**
Use current abstract Lean GateCNF/DAG clause proofs in `formal/symq_runtime`.
Propose a narrowly checkable serialized-graph/source-to-CNF refinement seam,
not a claim the entire Python implementation is verified. Check that every
model definition and theorem statement is pinned in development CI. Separate
trusted source→IR reduction, graph simplification, proof-checker kernel,
Lean renderer and execution dependencies in an explicit trust table.

**C3 — adversarial and performance.**
Test false cut/nonempty domain, dirty scratch, partial observation, missing
restoration, wrong local gate, tampered source/candidate/CNF, changed witness
and order, forged proof, late budget expiry. Independently enumerate small
truth tables and compare the canonical CNF's satisfying assignments. If the
prove/not-prove interpretation is not sound for a local cut, refuse rather
than silently converting it to global inequivalence.

Demonstrate 1+ genuine nontrivial positive contextual rewrite, 1+ wrong
rewrite and at least 20 separate negative/forgery cases; pair with a second
public family when useful. Measure full proof generation/export/validation
overhead and report short and over-budget failures. Execute consumer in a
fresh environment without SymQ/PySAT (formula-only) and with SymQ but no
solver (source-level, where supported).

## External references / existing tools

- [LRAT standard](https://arxiv.org/abs/1612.02353)
- [Lean standard-library verified LRAT checker](https://leanprover-community.github.io/sphere-eversion/docs/Std/Tactic/BVDecide/LRAT/Checker.html)
- [Mathlib LRAT proof integration](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Tactic/Sat/FromLRAT.html)

Prefer existing verified technology, with pinned versions and assessed license,
to new unverified checker code. Heavy/proof-generating SAT is optional at
runtime and does not change the current default checker.

## Exit deliverable

One research Draft PR (if technically viable) with source→CNF contract, small
standalone check, independent truth oracle and proof tampering tests, exact
CI/head/evidence and transparent trust boundaries. If the solver cannot emit
the chosen RUP subset efficiently, report an explicit negative bound rather
than altering the proof format to accept unverified steps.

No default engine, no package release, no unproven Python refinement claim,
no merge without separate maintainer authorization.
