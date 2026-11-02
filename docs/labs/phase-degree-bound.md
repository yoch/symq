# Logarithmic-degree features for obstruction-guided phase discovery

Research continuation of #163 on the integrated main baseline. This is a feature
proposal mechanism, not a new quantum theorem or proof authority. The fixed and
adaptive source checkers remain responsible for source binding, exact queries,
replayed samples, rank growth and fresh validation of final certificates.

## Bound and constructive proof

Let S be a nonempty set of N DISTINCT Boolean signature words. There is a positive
monomial M such that XOR over S of M(s) is one and

```math
\deg M\le\lfloor\log_2 N\rfloor.
```

For odd N the constant monomial works. Otherwise, repeatedly pick any coordinate
that varies among the remaining words and retain its smaller nonempty half. At
each split the number of surviving words is at most halved, so at most floor(log2 N)
coordinates isolate one word. Their positive or negated literals form a cube C
with incidence parity one on the ORIGINAL S.

Eliminate each negative literal without expanding the cube: over GF(2),
C'(1+x_i)=C'+C'x_i. If the old cube has odd incidence, at least one right-hand
term does. Keep such a term and repeat. At the end the term is a positive monomial
of degree at most the number of isolating literals. Further greedy deletion can
only decrease its degree. Runtime counts finite sample/bit operations; no complete
Boolean cube, degree layer, SAT query or 2^d cube expansion is needed for this step.

The bound is tight for the full d-dimensional Boolean cube: every monomial below
degree d has even weight. The general existence statement is also a consequence
of Reed--Muller duality and minimum distance, NOT a new coding theorem. See Abbe,
Shpilka and Ye, [Reed-Muller Codes: Theory and Algorithms](https://arxiv.org/abs/2002.03317),
Sections II-B/II-C. Sparse Boolean interpolation and membership/equivalence-query
learning are prior art; see [Roth--Benedek 1991](https://doi.org/10.1137/0220019).
The contribution proposed here is an explicit bounded-degree refinement step
inside SymQ's source-bound phase learning, with independently replayed rank evidence.

## Why the old deletion-minimal rule is insufficient

For odd m>=5, write W=2^m-1 and consider

```math
S_m=\{0,W\}\cup\{2^i:0\le i<m\}\cup\{W\oplus2^i:0\le i<m\}.
```

It has 2m+2 distinct words. Constant, linear and quadratic moments vanish, whereas
every cubic moment is odd. The prior maximal-word greedy rule starts at W and
cannot remove even one factor: it returns degree m. The minority-cube rule returns
a cubic in the executed family, including m=255, N=512. This is a constructed
negative example for the heuristic, not a real compiler performance benchmark.

The new rule is NOT minimum-degree or uniformly better: S=(1,2,3,4) produces mask3
(degree2), although mask4 (degree1) works. Keep this regression and compare complete
learning behavior, not only the degree of one local feature. A lower degree need
not reduce sample count, graph size, or total verification time.

## Executed pure-kernel checkpoint

Local Python3.13 execution: all65,808 nonempty sets in widths1..4 satisfy odd
incidence, deletion minimality and the degree bound. The unbounded-gap family at
m=5,7,15,31,63,127,255 returns degree3. A separate test covers500 seeded sets through
width256, input ordering, forged primitives and injected expiration at every
budget callback. End-to-end source and actual SAT validation belong to CI on the
published content, not to this standalone kernel experiment.

New helper: `symq.labs.phase_separator.halving_separator`. It proposes one column;
accepting that column still requires the replayed finite obstruction and rank
increase. No change to default discovery, stable APIs or main in this checkpoint.
