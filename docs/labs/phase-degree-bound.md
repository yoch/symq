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
only decrease its degree. The bit-operation cost includes large-integer arithmetic;
there is no enumeration of a complete Boolean cube or a degree layer in this step.

The bound is tight for the full d-dimensional Boolean cube: every monomial below
degree d has even weight. The general existence statement also follows from
Reed--Muller duality and minimum distance, NOT a new coding theorem. See Abbe,
Shpilka and Ye, [Reed-Muller Codes: Theory and Algorithms](https://arxiv.org/abs/2002.03317),
Sections II-B/II-C. Sparse Boolean interpolation and query-based learning are prior
art; see [Roth--Benedek 1991](https://doi.org/10.1137/0220019). This implementation
uses that structure for a source-bound phase refinement, with exact rank evidence.

## Unbounded greedy-degree gap on a constructed finite obstruction

For odd m>=5, write W=2^m-1 and consider

```math
S_m=\{0,W\}\cup\{2^i:0\le i<m\}\cup\{W\oplus2^i:0\le i<m\}.
```

It has 2m+2 words. Constant, linear and quadratic moments vanish; every cubic
moment is odd. The prior maximal-word greedy rule starts at W and cannot remove
one factor, returning degree m. The minority-cube rule returns a cubic for the
executed family through m=255,N=512. This is a constructed heuristic regression,
not a real compiler performance benchmark. The new rule is NOT minimum-degree:
S=(0,2,3,5) yields mask3 of degree2, while old greedy finds linear mask4.

## A fundamental counter-frontier: low degree is not always useful

If the signature image is the full d-bit cube and the true phase bit is the single
monomial h0*...*h(d-1), its ANF on that cube is unique and has degree d. Starting
from a linear dictionary, a learner that ONLY adds features of degree at most
floor(log2 N) for an N-sample obstruction cannot acquire that monomial before
at least 2^d distinct signature samples have been observed. Linear combinations
of lower-degree features cannot represent it.

This lower bound is on this specific degree-bounded policy, NOT on sparse Boolean
learning generally. The old greedy rule has no such degree restriction and may
succeed much sooner. The retained source fixture uses nonlinear, jointly surjective
h_i=a_i*b_i and a real compute-phase-uncompute source for their product. Shared
sample caps must remain unchanged between methods, and cap failures stay
inconclusive, never inequivalence. An isometric/channel certificate that proves
such a case must still pass a fresh source check.

Therefore lower local feature degree is not a uniformly better policy. Keep both
strategies explicit, preserve all negative results, and compare full discovery
cost including parsing, SAT, sample replay and fresh checking.

## Interface, tests and provenance

`discover_adaptive_phase(..., separator_strategy='halving')` selects the new rule;
`'greedy'` remains the default and its helper is unchanged. The public option is
closed to those exact strings. A proposal is checked for exact integer type,
nonnegativity, odd incidence, novelty, degree bound (halving only), and rank growth.
Source mutation, counterfeit fresh checks and inherited deadlines still fail closed.

Local pure-kernel execution: all65,808 sets of widths1..4 pass parity, deletion
minimality and the degree bound;500 additional sets cover widths8..256. On the
exhaustive cohort the new degree is lower/equal/higher than greedy on
20,180/41,839/3,789 sets. Many such sets are not actual learner obstructions, so
these are kernel statistics, not real-certificate speedup evidence.

The installed-package qualification tests all256 h=(ab,bc)->Z/4 source families
for both strategies, independently checks full channels, replays rank obstructions
and fresh certificates, and compares randomized-order whole calls on sparse
nonlinear-signature families. A separate campaign retains the single-high-degree
phase frontier and a common64-sample cap. Until that exact-content CI finishes,
the source-bound results are pending, not inferred from the pure-kernel test.

```bash
python -m pytest -q tests/test_phase_separator.py tests/test_phase_separator_integration.py tests/test_phase_separator_frontier.py
python -m benchmarks.phase_separator --output evidence/phase-separator.json
python -m benchmarks.phase_separator_frontier --output evidence/phase-separator-frontier.json
```

No minimum-size certificate, uniform speedup, portable proof or independently
checked SAT-UNSAT log is claimed. Private helpers remain a labs-only dependency.
No merge, default backend change or stable API promotion.
