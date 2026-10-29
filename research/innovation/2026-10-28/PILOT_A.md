# Pilot A: the factored HMR phase and a channel criterion

Files: `prototype/factored.py` (the criterion), `prototype/channel.py` (the independent
density-matrix oracle), `tests/test_factored.py` (51 tests), `prototype/pilot_a.py`,
`prototype/pilot_a2.py`, `prototype/pilot_scale.py`. Raw numbers: `RESULTS.json`.

## 1. The two structural facts, and the proof

Let the fragment be the one `src/symq/phase.py` accepts: `mcx` (an unconditional flip when it has
one qubit), `mcz`, `hmr` (X-basis measure and reset) and `mcz_if` (a classically controlled
`mcz` keyed on an earlier outcome). Its semantics assigns to every wire an ANF `f_w` over the
data variables `x` and, if the program measures, the outcome variables `m`, plus a phase `phi`.

**F1 (outcome-free wires).** For every reachable program state, `f_w` is an ANF in `x` only.

*Proof.* By induction on the instruction list. Initially `f_w = x_w` for data wires and `0` for
ancillas, both outcome-free. `mcx` replaces `f_t` by `f_t + prod(f_c)`, a sum and product of
outcome-free polynomials, hence outcome-free. `mcz` and `mcz_if` do not touch `f`. `hmr` sets
`f_q := 0`, which is outcome-free. ∎

**F2 (phase affine in the outcomes).** `phi = phi0(x) + sum_j m_j g_j(x)`, with every `phi0`
and `g_j` outcome-free.

*Proof.* By the same induction, tracking the coefficients separately. `mcz(q)` adds
`prod(f_q)`, outcome-free by F1, to `phi0`. `hmr(q)` producing outcome `j` adds
`m_j * f_q` (a single outcome variable times an outcome-free polynomial) to `phi`, hence
contributes `f_q` to `g_j` and nothing to `phi0`; then `f_q := 0`. `mcz_if(j, q)` adds
`m_j * prod(f_q)`, again a single outcome variable times an outcome-free polynomial, so it adds
`prod(f_q)` to `g_j`. Since the outcomes are fresh and each is introduced once, no monomial can
ever collect two outcome variables. ∎

A corollary worth stating because it is the reason pilot A1 fails:
**no monomial of `phi` carries two outcome variables, so the expanded ANF has exactly
`|phi0| + sum_j |g_j|` monomials** -- the factored form is not smaller, it *is* the expanded
form, partitioned.

Both facts are checked exhaustively against `phase_semantics` on 60 random programs, and the
invariant itself is asserted on 80 more (`tests/test_factored.py`).

## 2. The channel, and the criterion

Write `K_m = 2^{-M/2} (-1)^{phi(x,m)} |f(x)><x|`, so that `E(rho) = sum_m K_m rho K_m^dagger`.
Using F2,

    sum_m (-1)^{phi(x,m) + phi(y,m)}
      = (-1)^{phi0(x)+phi0(y)} prod_j sum_{m_j} (-1)^{m_j (g_j(x)+g_j(y))}
      = (-1)^{phi0(x)+phi0(y)} 2^M [g(x) = g(y)],

and the `2^M` cancels `2^{-M}` from the Kraus normalisation. Hence

    E(|x><y|) = (-1)^{phi0(x)+phi0(y)} [g(x) = g(y)] |f(x)><f(y)|.                 (CH)

`equivalent_channel` decides equality of two channels from (CH) by three Boolean-function
comparisons, all over `2 * width` *pair* variables and none over the `M` outcome variables:

1. `f_L = f_R` (the diagonal `x = y` forces it, since its kernel factor is always 1);
2. `[g_L(x) = g_L(y)] = [g_R(x) = g_R(y)]`;
3. on that common kernel, `phi0_L + phi0_R` is constant.

Steps 2 and 3 are ZDD equality and a ZDD product over the pair space. Nothing is enumerated.

## 3. It is the same predicate as the density-matrix oracle

`prototype/channel.py` is deliberately independent: no ANF, no pair space, exact `Fraction`
amplitudes, `2^M` integer Kraus operators composed explicitly. On 150 random pairs of programs
and 400 more in a standalone run, `equivalent_channel` and `same_channel` agree on every one,
with no disagreement in either direction. Two bugs found this way were in the oracle (an
uninitialised amplitude factor and a transposed matrix composition), which is exactly why it was
written separately.

The two tests that pin the semantics rather than the implementation:

* `test_the_factorised_map_has_the_expected_closed_form` checks (CH) entry by entry against the
  oracle on a program whose `g` is non-constant;
* `test_hmr_on_a_data_wire_is_a_reset_and_not_the_identity` states that a measurement on a data
  wire *does* change the channel -- measuring decoheres, and the criterion must say so.

## 4. What the pilots found

**A1. The factorisation saves nothing.** Ratio `expanded / factored` = 1.00 for
`M = 2, 4, 8, 16, 32, 64`. Consequence of the corollary above. A factored storage layer would be
code with no saving.

**A2. The criterion accepts more programs, soundly.** Of 300 random programs compared with the
identity of the same width: 36 accepted by the strict criterion, 40 by the channel criterion, 4
only by the channel criterion, all 4 confirmed by the oracle. No disagreement with the oracle.

**A2b. But not the ones that matter.** The canonical measurement-based uncomputation forms --
`ccx` into a clean ancilla, copy out, `hmr`, correct on the data wires -- satisfy O2 at 1, 2 and 3
ancillas. The programs the criterion additionally accepts have phases built from outcomes alone;
they are correct, but no compiler emits them as the interesting case.

## 5. Honest limits

* The comparison against Irene and phased outcome-complete simulation is not done; neither tool
  is installed and neither runs this fragment.
* 300 random programs is a small sample for a 1.3 % effect; the four extra acceptances are
  reported individually in `RESULTS.json`, not as a rate.
* The criterion is stated and proved for programs of equal width. Comparing programs with
  different ancilla counts needs the partial trace, which the criterion does not implement.
