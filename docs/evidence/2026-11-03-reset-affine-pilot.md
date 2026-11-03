# B0 research pilot: coherent affine-support reset identity

Source: issue #140; coordination #179; base main 766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc.

## New restricted theorem, not a general hybrid checker

A prefix comprised exclusively of computational-basis permutations
(X/CX/CCX/MCX/SWAP/CSWAP) and diagonal sign phases
(Z/CZ/CCZ/NEG) is a monomial unitary. On an independently supplied
affine legal computational basis domain
D = {origin XOR sum_j(u_j column_j)}, an exact ANF polynomial
for the reset wire can be calculated without enumerating 2^rank states.

If that polynomial is identically zero on every u, each basis output
of the prefix is in |0>_q. By linearity the output on every legal
superposition (including arbitrary reference entanglement) has the same
|0>_q factor. The CPTP reset of this qubit is therefore identity on
the legal input subspace. This is NOT a theorem about general
measurements/HMR, or about the full source and ideal channel.

A nonzero ANF polynomial has a concrete witness: set exactly the bits
of any *minimum-degree monomial* to one and all others to zero.
No proper submonomial can cancel its evaluation. Thus an allowed basis
input reaches q=1 and the reset is not clean.

## Implementation and limitations

- src/symq/labs/reset_support.py: research-only, source/support SHA-256 pins,
  checked independent GF(2) affine-column rank, guarded ANF terms/products/time,
  concrete nonclean basis witness, closed statuses and unsupported refusal.
- tests/test_reset_support.py: independent dense/Kraus matrix-unit oracle on
  widths 2..4 and randomized reversible/phase prefixes, explicit entangled
  superposition linearity test (all x,y matrix units), negative witness,
  malformed contract, measurement/feed-forward refusals, and synthetic 40
  wires / 35 independent coordinates / 89 definitely clean resets.

The synthetic shape is intentionally easy (89 zero resets on a free
clean target). It is NOT evidence for a real loader or a new 40-bit
HMR theorem. Existing affine_table already has a more sophisticated
synthetic 40-target/35-rank/89-reset qualification: this new pilot
instead targets *explicit input coherent span and individual reset
cleanliness*. No promise of best-in-class performance or broad
CPTP equivalence.

## Before an integration decision

This draft is not yet qualified until its **exact HEAD** test workflow
finishes. Independent review must inspect the ANF algebra, source
snapshot, affine rank proof, input witness derivation, all refusal paths
and self-contained small density oracle. A non-clean reset halts
analysis: no state after it is interpreted as a unitary ANF state.
No API/default engine change, merge, or release is authorized.


## B1: verified candidate generation (still a research API)

`build_clean_reset_candidate` freezes the HybridProgram once,
calls the *same* coherent affine-domain proof again on that exact frozen
program, and creates a reset-free candidate **only** for a complete
`proved_clean` result. The proof is relative to the declared legal
affine input subspace and the restricted monomial unitary grammar.
No source-independent provenance is established by the input SHA.

After a non-clean counterexample, unsupported measurement or failed
budget, it returns `candidate=None`. It does not extract or trust
an executable candidate from serialized result JSON. The returned
candidate is independently compared on every small matrix unit,
including before and after caller-side source mutation.

This is a real transformation of a proven legal subspace, but no
generic source-reachable compiler cut inference, no HMR generalization
and no automatic stable API or merge permission.


## Budget preflight hardening (post-B1 review)

Input mutation and resource caps are not proof obligations, but an
implementation accepting arbitrary untrusted objects must fail closed
without copying/serializing unbounded gate lists. Both verification
and candidate construction now enforce `max_operations` before copying
the operation sequence or invoking `dataclasses.asdict`.

An oversized input returns `inconclusive` and **no candidate**;
`source_sha256` and `support_sha256` are null because no frozen identity
was computed. It must never be treated as a source-bound or replayable
proof. The accompanying regression replaces `asdict` with a function
that raises, to confirm no expensive snapshot occurs before the cap.

This is a narrow resource preflight guard, not a claim of process-wide
memory bounds: Python object memory, validation, and hashing remain
outside an OS-enforced memory limit.


## Independent audit hardening (3 Nov 2026)

An independent audit of head `1552cc0` found no unsound positive: an
exact-fraction density/Kraus oracle written outside SymQ agreed on
503,136 exhaustive width-3 checks, 9,000 random and 3,000
compute/copy/uncompute circuits, comparing every matrix unit |x><y| of
the legal span. It confirmed three input/resource defects, fixed here
with regressions:

- `ops` that is not an exact `list` (a tuple, a generator or a list
  subclass assigned after construction) skipped the `max_operations`
  preflight and was copied, serialized and hashed, so an over-cap source
  received a `source_sha256`. Both entry points now refuse it with
  `UnsupportedOperation` before any copy.
- A `str` subclass as `kind` could serialize as one gate while comparing
  equal to `reset`, so the fingerprint named a different program than the
  one analyzed. `HybridProgram.validate` now requires `kind` to be an exact
  built-in `str`; slots, conditions and sources were already checked there.
- A `max_nodes` or `max_bytes` limit inherited from an enclosing
  `VerificationSession` was silently ignored. It is now refused, as an
  explicit one already was.

- The owner's review note (pre-budget snapshot work): the guard and its
  deadline are now created before any copy, validation or hashing, and an
  already expired deadline returns `inconclusive` with null fingerprints
  (regression traps `validate`, `asdict` and `_pin`). Both entry points share
  one frozen snapshot, so the input is copied and validated once.

Known limits that remain: the snapshot, validation and hashing themselves
are not interruptible, so a deadline that expires during them on an at-cap
input is only noticed afterwards (100,000 MCX operations on 40 wires with a
50 ms budget: about 1.5 s, then `inconclusive`); the support is caller-declared,
not a reachability theorem, so a candidate is valid only on that span;
`source_sha256` identifies serialized values, not authenticated objects.
