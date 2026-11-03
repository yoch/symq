# C1 research — source-recomputed classical SAT-miter LRAT proof

**Issue owners:** #167 (portable proof), #170 (formal model), #179 (research
coordination). The C0 pilot is in Draft PR #184, extended **in place**.

## Scope of the new result

`src/symq/labs/miter_proof_bundle.py` uses the existing
`miter_cnf.export_classical_miter_cnf` snapshot. Given a consumer-supplied
pair of reversible `Circuit` objects, a restricted `symq.sat.Contract` and
an **independently obtained lowercase source SHA-256**, the consumer:
1. Freezes and validates source and contract at entry, including legal
   input constants, observed output map and restored wires.
2. Reconstructs the deterministic **normalized** Tseitin miter CNF, with
   all domain/difference conditions encoded as actual formula clauses.
3. Compares the independent source identity, closed bundle schema, exact
   CNF bytes/digest and proof bytes/digest.
4. Runs the existing solver-free strict positive-hint RUP checker.
5. Reports `proved` only after checking the final empty clause before the
   shared deadline. `invalid`/`inconclusive` never authorize application.

The optional producer uses the already integrated proof-logging SAT solver
and DRUP elaboration. Producer success is **not proof authority**:
the consumer must independently regenerate and check. A satisfiable miter
gives `not_proved`, never an applicable candidate.

Both paths use inherited deadlines and `lrat_rup.Limits`.
The consumer imports neither PySAT nor the proof producer or Lean.

## Trust and theorem limits

- The Python source→Tseitin reduction remains **trusted**, not formally
  proved equivalent to the original source; `test_miter_cnf` supplies
  an independent small truth-table oracle as partial evidence.
- This does **not** prove a complete **contextual substitution** with
  arbitrary prefix, cut invariant or dirty borrowed ancillas. That needs
  a separate source-bound contextual obligation C2 or existing checker.
- Not an arbitrary quantum channel, HMR or measurement theorem.
- The independent source fingerprint must come from a trusted caller;
  a hash inside the proof bundle does not authenticate its source.
- The strict Python RUP verifier is existing, not new and not machine
  formally verified. No broader LRAT/RAT or default SAT guarantee.

## Independent and negative tests

`tests/test_miter_proof_bundle.py` exercises:
- A handcrafted positive empty-clause proof on a trivial contradictory
  miter formula, checked with PySAT hidden/unavailable.
- Rejection of forged source/candidate/contract, formula, SHA, hints,
  proof, trailing steps, fields, versions and theorem.
- An exhausted proof-size budget returning `inconclusive`.
- A genuinely nontrivial two-CCX cancellation under optional Glucose
  proof logging and separate consumer rechecking; a wrong replacement
  cannot obtain an accepted positive bundle.

## Exit criteria

Require exact HEAD 14/14 CI, independent diff/soundness review,
successful SAT-marked producer test, full producer+consumer runtime
and reproducible negative cases. Source-level contextual C2 remains
research, not automatically a consequence of C1.

No public API, default engine, merge or release authorization.


## Additional proof scenario: global contextual, not a cut lemma

The SAT-marked regression also builds a **complete four-wire circuit** with
an actual common prefix, a middle CCX, and a common suffix. Under the
explicit *global input* restriction `q1=0`, the CCX is inert, and a
source-recomputed positive RUP certificate is produced and consumed.

Removing this input restriction makes the source and candidate genuinely
different; altering the prefix or presenting the same proof under a
different contract must not produce an accepted positive. Thus the
tested C1 mechanism supports full-circuit **classical equivalence on a
restricted input domain**, including a contextual occurrence.

It still does **not** prove the separate local-cut interface obligations
of `symq.labs.contextual_substitution`, nor the coherent channel theorem
for hybrid circuits. Domain obligations remain caller-authenticated.
