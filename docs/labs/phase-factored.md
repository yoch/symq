# Factored source-bound phase certificates after affine signature mixing

Research extension of #163. The existing fixed/adaptive discovery and the audited
bitplane checker are unchanged. This separate candidate grammar preserves products
of affine forms instead of expanding a certificate into all its ANF monomials.

## A representation frontier, not just a search problem

Let q_i=a_i*b_i be jointly surjective nonlinear signature coordinates. Replace them
by h_i=q_i XOR q_(d-1) for i<d-1 and h_(d-1)=q_(d-1). This invertible XOR mixing
preserves all coherence fibres. The phase bit product(q_i) equals

```math
h_{d-1}\prod_{i<d-1}(1\oplus h_i).
```

Its unique ANF in h has exactly 2^(d-1) monomials, but the product-of-affine-forms
representation uses d factors. No number of better CEGIS samples makes a bounded
explicit-ANF dictionary hold all those terms. The recognizer instead recovers q_i
in the affine span of the ACTUAL effective signature and keeps their product.

## Certificate grammar and checking

An immutable certificate is a tuple of `(coefficient, products)` terms. Each
`products` tuple is an XOR of products; each product is a tuple of nonnegative
integer affine-form masks. Bit0 selects the constant, bit(j+1) selects h_j.
An empty product is one and an empty XOR is zero. Coefficients are canonical
integers modulo 2^k, where k is taken from the frozen source pair, not the witness.
All nested types, bounds and resource charges are checked before interpretation.

The claimed phase is a weighted modular sum of these Boolean expressions. The
checker independently freezes real L/R sources, the real sign/HMR dephaser and the
coherent affine support; verifies restoration and equality of all quantum outputs;
and extracts the effective signature INCLUDING phase feedback and source delta.
Affine forms are substituted by XORing the actual source ANFs. Products stay in
a bounded Boolean DAG and exact ripple addition preserves modular carries. Each
source bit is compared by SAT with the supplied factored expression. A SAT witness
is replayed by a literal source interpreter and independent scalar certificate
arithmetic. A false supplied candidate is not channel inequivalence.

The theorem is the existing fibre-constant phase criterion: equality of outputs
and delta=R(h) on the legal support prove equality of the full retained-output
channels AFTER the actual dephaser, with records forgotten. No controlled-use,
external support preparation or broader interference semantics are introduced.

## Sufficient structural discovery, not a complete factorizer

`discover_factored_phase` uses GF(2) elimination over the ANFs of `(1,h)` with
provenance. A monomial already present in source expressions can be recovered as
an affine form of h iff its row reduces to zero. Such atoms are reconstructed
exactly, then used as Boolean-mask covers of source phase monomials. An entire
phase predicate already in the affine span is handled directly, even when it is
nonmonomial. Otherwise its ANF monomials are covered separately and XORed.

Failure to cover a source atom is `not_proved(structural_factorization)`, never
inequivalence. In particular, this sufficient recognizer can miss valid aggregate
cancellations across unfactorable predicates. The earlier aggregate CEGIS/bitplane
route remains necessary on that overlap. Resource exhaustion is inconclusive.
A discovered certificate is not accepted until NEW source preparation and checking
succeed on detached sources within the same original deadline, with matching hashes.

Related prior art includes affine/nonlinear phase relations (Amy–Lunderville,
[POPL2025](https://arxiv.org/abs/2410.23493)) and factored Boolean SAT representations
([XOR-OR-AND normal forms](https://doi.org/10.1007/s11786-024-00594-x)). This work does
not claim to invent Gaussian elimination, functional decomposition or the general
advantage of factored expressions. It makes an explicit, testable source-bound
representation change for SymQ's phase certificate problem.

## Validation status and trust boundaries

The initial standalone pure-algebra run checked 16,030 assignments across 818
accepted algebra cases, with 963 safe structural refusals. It used minimal guard
and error shims, NOT an installed SymQ package or SAT solver. Installed-source,
independent channel-oracle and actual Glucose validation is a separate CI gate.

Source ANF extraction can still expand. The certificate grammar is not a compact
representation for every function. SAT UNSAT still trusts the encoder and solver;
there is no independently checked UNSAT log or portable proof kernel. Private
helpers are a labs-only dependency. No real compiler/KMB loader, untouched holdout,
general performance superiority or stable/default API promotion is claimed.
