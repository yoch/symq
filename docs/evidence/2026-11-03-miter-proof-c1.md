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
different; presenting the same proof under a different contract must not
produce an accepted positive. The mutated-prefix negative toggles q1 in the
*common* prefix of both circuits, which activates the CCX under `q1=0`; the
pair differs from the proved one only by that shared X, so the negative is
caused by the CCX. (An X on q1 added to one side only would be refuted by the q1
output alone and would not exercise the CCX.) Thus the
tested C1 mechanism supports full-circuit **classical equivalence on a
restricted input domain**, including a contextual occurrence.

It still does **not** prove the separate local-cut interface obligations
of `symq.labs.contextual_substitution`, nor the coherent channel theorem
for hybrid circuits. Domain obligations remain caller-authenticated.


## Independent audit notes (3 Nov 2026)

An independent audit of head `11a3aee` found no false positive, no proof
accepted for another source or CNF and no altered contract accepted:

- An oracle written outside the SymQ encoder compared, for 29,000 random
  miters (widths 1–7, every combination of input constants, partial observed
  outputs, partial output maps and restored wires), the per-input SAT result of
  both the normalized and the raw clause lists against brute-force circuit
  evaluation: 467,430 checks, 0 mismatches. Normalization changed the clause
  list in 15,585 of them, so proofs must target the normalized formula.
- Bundles produced with python-sat were replayed with python-sat absent;
  neither `pysat` nor `lrat_export` was imported. The Lean 4.19 verified
  checker accepted 6 of 6 exported proofs and rejected one with a hint removed.
- 45 bundle tampering cases: none accepted except the untouched baselines,
  a dropped step no later hint cites (still a valid proof), a CRLF variant
  with its own recomputed hash, and a non-string label object, now refused.

Fixed with this note: the mutated-prefix negative now toggles q1 on both
sides, so it actually exercises the CCX (a one-sided X(1) is refuted by the
q1 output alone); `kind` and `theorem` must be exact strings.

Known limits that remain: the CNF size caps and the deadline are checked
after `build_miter` finishes, not during encoding; the producer's Glucose
interrupt can overrun its deadline (the status stays `inconclusive`); some
malformed contracts raise instead of returning a status; the source document
carries no encoder version, so a future encoder change makes stored bundles
fail closed rather than re-pin.
