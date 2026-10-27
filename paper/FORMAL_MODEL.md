# Formal model (paper A) and proof obligations

Scope: exact functional equivalence of classical reversible circuits over X, CX, CCX and MCX
gates with fully symbolic inputs. Everything in this file is a **paper proof** written for
the manuscript; none of it is machine-checked. Section 6 lists, for each statement, which
evidence exists in the repository and of what kind.

## 1. Ring and canonical form

Let `B_n = GF(2)[x_0, …, x_{n-1}] / (x_i^2 - x_i)`. Every element has a unique
representation as a sum of distinct square-free monomials (the algebraic normal form, ANF,
also called the Reed–Muller or Zhegalkin expansion). A monomial is identified with its
support `S ⊆ {0..n-1}`, encoded LSB-first as the mask `Σ_{i∈S} 2^i`; a polynomial with the
finite family `F ⊆ 2^{[n]}` of its monomials.

- Addition is symmetric difference of families: `F + G = F △ G`.
- Multiplication is `F · G = △_{S∈F, T∈G} {S ∪ T}` (parity of the number of pairs producing
  each union).
- Evaluation at an assignment `a ∈ {0,1}^n`, viewed as the set `A = {i : a_i = 1}`:
  `p(a) = |{S ∈ F : S ⊆ A}| mod 2`.

**Fact 1 (canonicity).** The map from `B_n` to Boolean functions `{0,1}^n → {0,1}` is a
ring isomorphism; hence two polynomials denote the same function iff their monomial
families are equal. (Standard; the Möbius inversion on the subset lattice.)

## 2. Circuits and their symbolic semantics

A circuit of width `n` is a list of gates `g = (C, t)` with control set `C ⊆ [n]` and target
`t ∉ C` (`X`: `C = ∅`; `CX`: `|C| = 1`; `CCX`: `|C| = 2`; `MCX`: any `|C|`). Concrete
semantics on a state `s ∈ {0,1}^n`: `s_t ← s_t ⊕ Π_{c∈C} s_c`.

Symbolic semantics: a state is a vector `f = (f_0..f_{n-1}) ∈ B_n^n`, initially `f_i = x_i`,
and gate `(C, t)` performs `f_t ← f_t + Π_{c∈C} f_c` (the empty product is 1).

**Proposition 1 (soundness and completeness of symbolic simulation).** After processing
the gate list, for every input `a`, `(f_0(a), …, f_{n-1}(a))` equals the concrete output of
the circuit on `a`.

*Proof.* Induction on the gate list. Initially `f_i(a) = a_i`. If `f(a)` equals the concrete
state `s` before gate `(C, t)`, then evaluation is a ring homomorphism, so
`(f_t + Π f_c)(a) = s_t ⊕ Π s_c`, and the other wires are unchanged. ∎

**Corollary 1 (decision procedure).** Circuits `L` and `R` of equal width are functionally
equivalent iff their output families are equal wire by wire (Proposition 1 and Fact 1).

## 3. Witnesses

**Proposition 2 (minimum-degree witness).** Let `p ≠ 0` with family `F`, and let `M ∈ F`
have minimum cardinality. Then `p(χ_M) = 1`, where `χ_M` is the assignment with ones
exactly on `M`.

*Proof.* `p(χ_M) = |{S ∈ F : S ⊆ M}| mod 2`. Any `S ∈ F` with `S ⊆ M` and `S ≠ M` would have
`|S| < |M|`, contradicting minimality. So only `S = M` contributes: `p(χ_M) = 1`. ∎

With `p = f^L_i + f^R_i` for the first differing output `i`, `χ_M` is an input on which the
circuits differ. The implementation re-executes both circuits concretely on `χ_M` and
raises `InternalInconsistency` if they agree, so an incorrect backend cannot produce an
unchecked counterexample. (An equivalence verdict has no such independent check: it rests
on Proposition 1, Fact 1 and the correctness of the backend, which is why differential tests
matter, see §6.)

Note: any monomial `M` of `p` that is minimal for inclusion (not only for cardinality)
works; minimum cardinality is a convenient way to pick one and gives a sparse witness.

## 4. Monomial ZDDs

Fix a variable order `π` (a permutation of `[n]`, level `ℓ` holds variable `π(ℓ)`). A ZDD
node is either a terminal `⊥` (empty family) or `⊤` (the family `{∅}`), or a triple
`(ℓ, lo, hi)` with children at levels `> ℓ`, denoting
`⟦(ℓ, lo, hi)⟧ = ⟦lo⟧ ∪ { S ∪ {π(ℓ)} : S ∈ ⟦hi⟧ }`. The zero-suppression rule forbids
`hi = ⊥`; nodes are hash-consed on `(ℓ, lo, hi)`.

**Fact 2 (canonicity, Minato 1993).** Under a fixed order, with zero-suppression and
hash-consing, every family of subsets of `[n]` has exactly one node; equality of families is
equality of node identifiers.

Recursions (both operands are split on the smaller top level `ℓ`, with variable `v = x_{π(ℓ)}`;
an operand whose top level is larger has `P_1 = 0`):

- `P + Q = (ℓ, P_0 + Q_0, P_1 + Q_1)` (symmetric difference);
- `P · Q = P_0 Q_0 + v (P_0 Q_1 + P_1 Q_0 + P_1 Q_1)` (the *three-product* form);
- terminal cases: `0·Q = 0`, `1·Q = Q`, `P·P = P` (every element of `B_n` is idempotent),
  `P + P = 0`, `P + 0 = P`.

**Proposition 3 (correctness of the product recursion).** With `P = P_0 + v P_1` and
`Q = Q_0 + v Q_1`, where `P_0, P_1, Q_0, Q_1` do not contain `v`,
`PQ = P_0Q_0 + v(P_0Q_1 + P_1Q_0 + P_1Q_1)`.

*Proof.* Expand and use `v^2 = v`:
`PQ = P_0Q_0 + v P_0Q_1 + v P_1Q_0 + v^2 P_1Q_1 = P_0Q_0 + v(P_0Q_1 + P_1Q_0 + P_1Q_1)`.
None of the four products contains `v`, so `P_0Q_0` is the `lo` part and the bracket the
`hi` part, and `mk(ℓ, lo, hi)` applies the zero-suppression rule. ∎

The alternative "two-product" form `v((P_0+P_1)(Q_0+Q_1) + P_0Q_0)` is algebraically equal
but builds larger intermediate sums in practice (`docs/research/BENCHMARK_FINDINGS.md`); we
make no asymptotic claim about either form.

**Termination and recursion depth.** Every recursive call strictly increases the top level
of at least one operand, so the recursion depth is at most `2(n+1)`; with `n ≤ 64` this is a
small constant for the C stack. No complexity bound better than the size of the result
family is claimed: ZDD operations can be exponential in `n` in the worst case, and the
multiplier family of the blind corpus is included precisely to exhibit such growth.

## 5. Budgets

`Budget(max_seconds, max_nodes, max_terms)` is checked inside the recursions (clock every
1 024 recursive steps and every 64 gates of the fused loop; node count on insertion; term
count when a polynomial is materialised as an explicit family). Term counts are kept per
node; a 64-variable family can hold 2^64 monomials, so the counts must saturate rather than
wrap (fixed in PR #23, open and not in the measured binary: before it, the count of
`x_63 + Π_{i<63}(1 + x_i)` wrapped to a negative number and bypassed `max_terms`). Exceeding a limit raises
`ResourceLimitExceeded`; no verdict and no partial result is returned.

**Proposition 4 (budget soundness).** Every verdict returned under a budget is the verdict
of Corollary 1. *Proof.* The budget only aborts; when it does not abort, the computation is
the unbudgeted one. ∎

This is a statement about the absence of approximation, not about completeness: a budgeted
run may refuse to answer.

## 6. Evidence for each statement

| statement | paper proof | exhaustive tests | differential / mutation tests | machine-checked |
|---|---|---|---|---|
| Fact 1, Prop. 1 | standard / §2 | all inputs of 40 seeded random circuits of 1–7 wires, for each of the 10 registered backends including `zdd-native` (`tests/test_backends.py::test_outputs_match_concrete_execution`); variants and mutants against the exhaustive oracle `Circuit.equivalent` (≤ 16 wires) on 2–7 wires (`tests/test_equivalence.py`) | — | no |
| Prop. 2 (witness) | §3 | — | every returned witness is re-executed (`check_equivalence`); a lying backend is detected (`tests/test_equivalence.py::test_witness_self_check_detects_lying_backend`) | no |
| Fact 2, Prop. 3 | Minato / §4 | — | native core vs Python ZDD vs sparse ANF, identical node tables (`tests/test_zdd_native.py`, 250 tests); the differential checks kill deliberately broken *Python* algebras (missing cross term, no GF(2) cancellation, OR instead of XOR; `tests/test_equivalence.py::test_differential_checks_kill_backend_mutants`); the order of variables changes sizes, not results (`tests/test_backends.py`, and run R-ORDER: 7 orders × 19 circuits) | no |
| Prop. 4 | §5 | — | budget tests in `tests/test_backends.py`, `tests/test_audit_regressions.py`, `tests/test_zdd_native.py` | no |

"Formal verification" is therefore **not** claimed for symq itself: the decision procedure
is exact by construction and its implementation is tested differentially, exhaustively on
small widths, and against independent native tools.

## 7. The phase/HMR fragment (paper B, not part of paper A)

`docs/research/PHASE_HMR_SPEC.md` defines a restricted fragment (±1 phases, X-basis
measure-and-reset, single-outcome Z-type feed-forward) with obligations O1 (clean ancillas)
and O2 (outcome independence) and two theorems with proof sketches. Their status is:
paper proof sketch; exhaustive comparison with an independent integer state-vector oracle on
all inputs and outcomes of small programs (`tests/test_phase.py`); no external corpus, no
machine-checked proof, no budgeted backend (audit finding F4). Issue #20 lists the missing
pieces (grammar, per-outcome Kraus normalisation, necessity of O2, induced injectivity). It
is deliberately excluded from the claims of paper A.
