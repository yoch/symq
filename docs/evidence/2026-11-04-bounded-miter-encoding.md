# SAT-miter CNF resource preflight and in-encoding limits (4 November 2026)

**Scope:** [issue #193](https://github.com/yoch/symq/issues/193).
**Base under development:** `main@8977314c66404b9d59ba668151f928be82f66525`.
**Status:** research patch; no API promotion, security-grade limits or merge authorization.

## Why this exists

On the original `miter_cnf.export_classical_miter_cnf` code, the call to
`build_miter` constructed all Tseitin variables and clauses *before*
checking `max_variables` and `max_clauses`. An independent audit measured a
400,000-gate CCX input with a 0.05-second deadline and
`max_variables=10` consuming about 0.95 seconds and 175 MB before a
correct, **non-positive** refusal. The checker did not produce false
proofs; it violated the desired resource envelope.

## Narrow change to the source-bound labs exporter

The existing normal `symq.sat.Encoder`, `check_sat_equivalence` and their
semantics remain the default. New optional `encoder` and `checkpoint`
arguments to the internal `build_miter` and `encode_circuit` functions let
the **labs-only** exporter use a distinct `_BoundedEncoder`:

- `new` checks the exact variable ceiling before allocation.
- `add` checks the **raw** clause count before append.
- `add` tracks the exact textual byte cost of **normalized** non-tautological
  clauses as they are emitted, so an exact source + output DIMACS byte cap
  can be enforced during encoding, not after it. Duplicate literals
  collapse and tautological clauses do not count towards normalized
  *output* bytes; they still consume the raw-clause budget.
- Every variable/row allocation polls the inherited monotonic deadline.
  The guarded gate iterator also checks once per 64 operations in both
  source streams, including X-only cancellations that allocate no
  additional Tseitin nodes.
- The exporter rejects unsupported inherited node/term budgets. It now
  also honours inherited byte budgets from `VerificationSession`.
- `max_source_gates=100_000` is an explicit, conservative research
  envelope (sum of both circuit gate list lengths), checked **before**
  source snapshots, validation, hash construction or miter encoding.
  This is a research resource *refusal*, not a proof of inequivalence.
- The existing closed source/contract documents, canonical CNF bytes,
  positive-hint RUP prover and solver-free consumer are unchanged.
  A guard breach must never produce a positive source-level certificate.

## Exact promise and remaining gaps

This patch bounds **logical SAT variables, raw clauses and serialized
source+CNF output bytes** as construction progresses. It does **not**
enforce a hard cap on CPython process RSS. Memory for the structural
hashing dictionary, input gate objects, source snapshot/JSON, solver
bootstrap and LRAT proofs can exceed nominal serialized bytes.
A C/C++ or Python call already executing is not preempted by a
cooperative guard.

Importantly, validation, snapshot copying and source serialization
still have some uninterruptible operations; and proof-logging Glucose's
interrupt can exceed its deadline. The guard reports no decisive
result after expiry. **For adversarial remote inputs, a separate
killable worker with OS-level memory/time controls is still required.**
Keep issue #193 open until that architecture is independently audited.

## Evidence and adversarial exit criteria

`tests/test_miter_encoding_limits.py` checks that variable/row caps
abort inside the miter builder, a huge source list is rejected before
validation, cancellation-only long gate streams actually poll the guard,
inherited byte caps/refused unsupported ceilings are enforced, byte
accounting treats tautologies correctly, and the unchanged default
SAT path still uses the ordinary `Encoder`. The new source-bound
producer must remain `inconclusive` on cap exhaustion, never `proved`.

Retain the independent small Boolean-oracle and LRAT-mutant suites from
the audited #194 tree. Before integration, run Python 3.10–3.14,
pure/native, optional solver present/absent, installed wheel/sdist and
macOS CI **on the exact new HEAD**. Review the actual diff and verify
that the default SAT corpus's formula/verdicts remain unchanged.
No claim about hard resource protection or benchmark speedup is warranted.
