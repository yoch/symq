# Lean-kernel-checked LRAT witnesses: a distinct, bounded trust milestone

Continuation of #167/#168. The existing Python checker and source consumer are
unchanged. This adds a data-only emitter to an existing formally verified checker,
not a claim to have invented or formally verified a new LRAT algorithm.

## Exact authority boundary

Lean4 v4.19.0 is pinned (leanprover/lean4 commit
6caaee842e9495688c1567e78c0e68dbb96942aa). Its standard library provides
`Std.Tactic.BVDecide.LRAT.check_sound`: acceptance of its LRAT checker implies
unsatisfiability of the literal CNF. See the pinned [checker source](https://github.com/leanprover/lean4/blob/6caaee842e9495688c1567e78c0e68dbb96942aa/src/Std/Tactic/BVDecide/LRAT/Checker.lean).
The original LRAT format already has certified Coq/ACL2 checkers; this is reuse
of established work, not a new SAT proof system.

The emitter writes only validated numerals, lists, literal Booleans and a fixed
proof skeleton. DIMACS variable n becomes CNF Nat variable n-1; Lean's verified
conversion increments it back before checking unmodified LRAT literals. A pinned
formula digest is required. An emitted file is **not** a proof result and its
`verified_unsat` field remains false. Only successful Lean elaboration/typechecking
establishes the generated theorem `SymQPortable.claim : formula.Unsat`.

The proof uses ordinary `by decide`, not `native_decide`, `bv_decide`, unchecked
native reflection, user axioms, `sorry`, or bypasses of kernel type checking.
Axiom reports are retained and allow only Lean's ordinary foundational axioms
propext, Quot.sound and Classical.choice; extra native-computation axioms are
refused. This choice can be much slower than native reflection: speed and large
proof scalability are deliberately not claimed at this milestone.

## What is still NOT formally proved

The theorem is about the literal CNF that appears in the generated Lean file.
The data emitter and DIMACS parser are not proven to preserve the original bytes;
the source-to-obligation compiler, graph simplifications, phase/channel theorem
implementation and caller source identities remain outside this formal proof.
Consumers must still regenerate and bind the CNF from their trusted actual source
objects. Hash comments are metadata, not logical axioms or proof of semantics.
The pinned Lean binary, its imported library/kernel, runtime and hardware remain
trusted execution components. This does not formally verify all SymQ/Python.

`GateLemmas.lean` separately formalizes the AND and XOR CNF truth-table equivalences
and the elementary implication from an aggregate candidate identity to constancy
on signature fibres. Those are useful beginning lemmas, NOT a refinement proof
of the actual Python encoder or the full quantum Kraus theorem. Each is checked
by Lean without an external evaluation oracle.

## Qualification and mutations

The dedicated workflow builds the small Lean package, exports eight selected
source-derived phase formulas, one non-unit pigeonhole refutation, an original
empty clause and a sparse variable-numbering formula. It also emits three
well-typed but invalid proof claims: a missing conflict, non-unit hints on a
satisfiable formula, and a changed literal polarity. Lean must accept all eleven
positives and semantically reject all three negatives. Environment/import/syntax
failures cannot stand in for the expected rejection.

Python-sat is uninstalled before checking. The source consumer re-extracts each
selected source/candidate obligation without a solver, while Lean independently
checks the formula proof. Generated Lean bytes are regenerated and compared before
execution; arbitrary uploaded Lean scripts are never accepted as this data format.
The archive retains CNF, LRAT, generated Lean, olean for accepted proofs, logs,
axiom lists, source and toolchain identities, commit/tree and every result.

Unit tests cover exact literal mapping, unused variables/empty clauses, unsafe
text injection, wrong pins, partial hints, unsupported formats, forged primitives
and deadline failure at every meter checkpoint. Generation never invokes the
Python proof-inference kernel. A valid-looking emitter status cannot become proof.

## Reproduction

```bash
python -m pytest -q tests/test_lrat_lean.py
python -m benchmarks.lean_phase_proofs generate --output-dir evidence/lean
# Install the pinned Lean toolchain, then remove python-sat for the independent check.
python -m pip uninstall -y python-sat
python -m benchmarks.lean_phase_proofs check --output-dir evidence/lean
```

The original 256-case Python/source qualification remains a separate campaign.
Do not describe these eleven selected formal proofs as formal verification of all
256 source cases, a holdout, a large-scale benchmark or qant/KMB certification.
At initial publication, Python emitter tests have run locally on authenticated
kernel bytes; actual Lean/compiler qualification is pending dedicated CI.
No default/API promotion or merge authorization is given by this experiment.
