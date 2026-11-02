# Reusing modular lifts in affine phase derivatives

This note supports four opt-in study methods in `symq.labs.affine_basis_study`:
`canonical_precompute`, `canonical_complement`, `canonical_split` and
`canonical_factorized`. The [study guide](../guide/affine-basis-study.md) has the
harness and the measured results. These are research methods, not defaults.
They do not change the published checker `symq.labs.affine_phase` or its receipt.

The note works out which parts of the derivative obligation the published
checker recomputes. It proves each identity the methods use. It also states
when a route is exact but slower.

## Setting and notation

Fix the kernel parameters `z` in `F_2^n` and the modulus `M = 2^k`. A Boolean
predicate `p` is held in algebraic normal form (ANF) as a `frozenset` of monomial
masks. Mask `0` is the constant `1`. `[p]` is its integer value in `{0, 1}`. The
relative phase is

\[
  \delta(z) = \sum_i c_i\,[p_i(z)] \bmod M ,
\]

with distinct nonempty predicates `p_i` (the keys of `delta`) and nonzero
coefficients `c_i` in `Z/M`. Translation by a kernel direction `v` is
`(τ_v p)(z) = p(z ⊕ v)` (`affine_phase._translate`). The obligation for a basis
direction `v` is that `D_v δ(z) = δ(z ⊕ v) − δ(z)` vanishes identically. The
published `_derivative` computes the following, adding coefficients mod `M` with
`_add_term`:

\[
  \sum_{i:\ \tau_v p_i \neq p_i} \operatorname{lift}(\tau_v p_i, c_i) + \operatorname{lift}(p_i, -c_i).
\]

## Canonical forms

**Lemma 1 (unique multilinear representative).** Every function
`f : {0,1}^n → Z/M` has exactly one representation
`f(z) = Σ_S a_S z^S` with `a_S` in `Z/M` and `z^S = Π_{j∈S} z_j`.

*Proof.* Evaluating at the indicator `1_T` gives `f(1_T) = Σ_{S⊆T} a_S`. The matrix
`ζ(T,S) = [S ⊆ T]` is unitriangular for any order that extends inclusion. It is
therefore invertible over every commutative ring, with Möbius inverse
`a_S = Σ_{T⊆S} (−1)^{|S∖T|} f(1_T)`. ∎

Write `rep(f)` for this representation as a dictionary, with the zero
coefficients omitted. `rep` is `Z/M`-linear. For example, `rep(u·f + g)` is
`u·rep(f) + rep(g)`, reduced and with zeros dropped.

**Lemma 2 (lifts are canonical).** `_lift(p, c, M) = rep(z ↦ c[p(z)] mod M)`.

*Proof.* By induction over the masks in sorted order. Assume the dictionary
`R = Σ a_S z^S` equals `rep(c[x])` for the XOR `x` of the masks already processed.
For bits, `[x ⊕ m] = [x] + [m] − 2[x][m]`. On `{0,1}`, `z_j^2 = z_j`. So
`c[x ⊕ m] = R + c z^m − 2 Σ a_S z^{S ∪ m}`. This is exactly what `_lift` adds from
its snapshot `old` of `R`. `_add_term` reduces mod `M` and drops zeros, so the
result is a multilinear polynomial with nonzero coefficients that represents the
function. By Lemma 1 it is `rep`. ∎

**Corollaries.**

1. *Decision identity.* Every route below produces `rep(D_v δ)` for each direction,
   possibly in another dictionary insertion order. The checks `if difference`, the
   witness `min(difference, key=(popcount, mask))` and its replay are therefore
   identical to the published ones. The receipt is built from the canonical
   basis and `delta` alone, so it is byte-identical to `published`. The tests
   check this on random sources and generated cases.
2. *Exact cache keys.* ANF is canonical, so a lift is determined by
   `(p as frozenset, c mod M, M)`. The modulus must be in the key, and the sign of
   `c` matters unless `c ≡ −c` (only `c = M/2` among nonzero values). Conversely,
   equal functions `c[p] = c'[p']` with `c ≠ 0` force `p = p'` and `c = c'`, so the
   key has no aliasing.
3. *Linearity.* `lift(p, −c) = −lift(p, c)` and `lift(p, 2c) = 2·lift(p, c) mod M`.
   More generally `lift(p, u c) = u·lift(p, c)`. These are coefficientwise
   rescalings, with no expansion.

**Lemma 3 (expansion depth).** For `p = m_1 ⊕ … ⊕ m_r`, the following holds,
collected by the union mask:

\[
  c[p] = \sum_{\emptyset \neq S \subseteq \{1..r\}} c\,(-2)^{|S|-1} z^{\cup_{i\in S} m_i}.
\]

Every term with `|S| > k − ν(c)` vanishes mod `2^k`, where `ν` is the 2-adic
valuation. So `lift(p, c)` has at most `Σ_{s=1}^{k−ν(c)} C(r, s)` monomials, and
`lift(p, 2c)` has a depth one smaller.

*Proof.* For a bit `x`, `(−1)^x = 1 − 2x`. So
`[⊕x_i] = (1 − Π_i (1 − 2x_i))/2`. Expanding the product gives the coefficient
`−(−2)^{|S|}/2 = (−2)^{|S|−1}`. ∎

At `c = M/2` the lift is linear in `|p|`, and `lift(p, 2c) = 0`.

## What the published derivative recomputes

**(I0) Invariant predicates.** If `τ_v p = p` as ANF, the functions are identical
and the contribution is zero. The published checker skips these without lifting.

**(I1) Direction independence.** The term `lift(p_i, −c_i)` does not involve `v`.
For `d` kernel directions the published checker computes it once for each
direction along which `p_i` is not invariant. In `identity_dense` this is half
of its 72 lifts, on 4 keys. The `canonical_cache` LRU keeps these lifts only
while nothing evicts them. With a one-entry cache, original and translated keys
alternate and nothing hits.

**(I2) Complement.** Suppose `τ_v p = p ⊕ 1`. Then `[τ_v p] = 1 − [p]` and

\[
  c[\tau_v p] - c[p] = c - 2c[p], \qquad
  \operatorname{rep} = \{\emptyset: c\} + \operatorname{lift}(p, -2c).
\]

Also `lift(p ⊕ 1, c) = c − lift(p, c)`. The right-hand side does not depend on
`v`, and Lemma 3 makes it shallower than either published lift. The tests verify
the identity exhaustively for all 256 three-variable ANFs, every `k ≤ 4` and every
`c`, against direct evaluation.

**(I3) Affine predicates are only invariant or complemented.** Write
`p = b ⊕ ⊕_{j∈A} z_j`, where every mask has weight at most one. Then
`τ_v p = p ⊕ (|A ∩ v| mod 2)`. Classification needs one parity test after a single
`O(|p|)` pass, with no Boolean substitution. With (I2), the only lift an affine
predicate ever needs is the direction-free `lift(p, −2c)`.

**(I4) Boolean-derivative split.** Let `d = p ⊕ τ_v p` (the ANF symmetric
difference, the Boolean derivative `D_v p`). Then `τ_v p = p ⊕ d`. For bits,
`[p ⊕ d] − [p] = [d] − 2[p][d] = [d] − 2[p·d]`, where `p·d` is the ANF product.
Hence

\[
  c[\tau_v p] - c[p] = \operatorname{lift}(d, c) + \operatorname{lift}(p\cdot d, -2c).
\]

The cases `d = 0` and `d = 1` are (I0) and (I2). Every monomial `z^m` maps to
`Σ_{T⊆m∩v} z^{(m∖v)∪T}`, and the `T = m∩v` term cancels in `d`. So
`deg d ≤ deg p − 1`. The second lift is one level shallower. If `p·d = p` (that
is, `p ⇒ d`), it is direction-free and can be pinned.

In the identity family the product predicate is `P = p∧q`, with `p`, `q`
affine. Its derivative is `d ∈ {q, p, p ⊕ q ⊕ 1}`, and in every case
`P·d = P`. One pinned `lift(P, −2c)` and three affine `lift(d, c)` replace two
dense lifts per direction. This accounts for the 7 lifts against 72. The route is
exact everywhere, but it is not always cheaper. `p·d` costs `|p||d|` to form and
can have more terms than `τ_v p` (nonlinear predicates in mixed coordinates).

**(F) Factorization.** Let `N_v = {i : τ_v p_i ≠ p_i}`, and let `S` be any set of
predicates that contains `N_v`. The predicates outside `S` are `v`-invariant, so
`D_v δ = D_v δ_S` with `δ_S = Σ_{i∈S} c_i[p_i]`. By linearity,
`Δ_S = rep(δ_S) = Σ_{i∈S} lift(p_i, c_i)`. For bits, `z_j ⊕ 1 = 1 − z_j`. So
`z ↦ Δ_S(z ⊕ v)` is represented by substituting `z_j → 1 − z_j` on `v`:

\[
  z^m \mapsto z^{m\setminus C}\prod_{j\in C}(1 - z_j)
  = \sum_{T\subseteq C} (-1)^{|T|} z^{(m\setminus C)\cup T},\qquad C = m\cap v .
\]

The result is multilinear. Subtracting `Δ_S` and reducing gives `rep(D_v δ)`.
Monomials with `C = ∅` contribute nothing and are skipped.
`canonical_factorized` uses `S = ∪_v N_v` over the basis. It lifts each such
predicate once and then does `Σ_{m∈Δ_S, m∩v≠∅} (2^{|m∩v|} + 1)` additions per
direction.

The factorization proposed in the question, `Σ_i c_i·lift(p_i)` taken over
*all* predicates, is valid but not adopted. It lifts every invariant predicate.
In `measured_dense_predicate` (a 24-term parity, `k = 16`) that lift has about
`1.6 × 10^7` monomials and hits the term cap. The published checker decides the
case with no lift. Restricting to `S` removes that failure. Two costs remain,
both unbounded relative to the published checker:

- a predicate in `S` because of a single direction is still expanded along every
  direction its lifted monomials meet;
- the expansion has no mod-2 cancellation, and its size grows as `2^{|m∩v|}`.

The adversarial case `variation_near_invariant_dense` measures the first cost.
When `Δ_S` cancels, the method is very cheap: the identity family has `δ ≡ 0`,
so `Δ = 0`.

## Reuse conditions and keys used

| Situation | Exact test | Reused object | Key |
| --- | --- | --- | --- |
| invariant | `τ_v p == p` (ANF), or even parity for affine `p` | nothing computed | — |
| original term | always | `lift(p, −c)`, pinned | `(p, −c mod M, M)` |
| complement | `τ_v p ^ p == {0}`, or odd parity for affine `p` | `{∅: c} + lift(p, −2c)`, pinned | `(p, −2c mod M, M)` |
| split | `d = τ_v p ^ p` otherwise | `lift(d, c)` in the LRU; `lift(p·d, −2c)` pinned if `p·d == p`, else in the LRU | `(d, c mod M, M)`, `(p·d, −2c mod M, M)` |
| factorized | `p` non-invariant along some basis direction | one `Δ_S` per call | — |

The following were not implemented. A translated predicate can equal another
phase predicate `p_j`, and a coefficient can be a unit multiple of a cached
coefficient. Corollary 3 would serve both by rescaling. The study fixtures do
not exercise either case.

## Resources

Every lift, product, translation and coefficient addition goes through the
call's `_Work` guard (term count and deadline). The pinned table is filled
lazily, so a predicate that is invariant along every direction is never lifted.
It holds at most two keys per predicate and is never evicted, so the LRU's entry
and term caps do not apply to it. It is charged to the same term budget: pinned,
LRU and key-statistics units together never exceed `max_terms`, and the LRU
shrinks to fit (`Lifts.reserved`). An entry that does not fit is recomputed
instead of retained, so retention alone never produces `inconclusive`.
`canonical_factorized` keeps one `Δ_S` dictionary, bounded like every other
explicit collection. A cap or deadline exhaustion at any accounting point
returns `inconclusive` with no receipt and no witness. A test injects exhaustion
at every point of several small proofs.
