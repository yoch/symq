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
