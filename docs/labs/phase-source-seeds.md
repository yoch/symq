# Optional source-derived monomial seeds for the high-degree phase frontier

Research follow-up to the [degree-bounded separator](phase-degree-bound.md).
A low-degree policy starting with linear features cannot learn the full degree-d
monomial on a surjective d-bit signature before observing 2^d signatures. The
retained benchmark shows that the old greedy rule can also spend all its samples
on this family. A different information source is needed, not just a smaller
separator or a larger cap.

## Exploit already verified source structure, without trusting a candidate

The learner already extracts Boolean ANFs for the actual effective signature h
and every weighted source phase predicate. If a source predicate is one monomial
p, and certain signature coordinates are themselves monomials whose masks are
contained in p, their product equals p exactly iff the union of their masks is p.
Overlapping variables are harmless because x_i^2=x_i in Boolean arithmetic.

The optional source_monomials=True pass greedily covers the source mask using
those eligible coordinates, reconstructs the union to check the identity and
adds that product to the INITIAL dictionary. Greedy cover is not a minimum-size
factorization. Signature sums and phase predicates with multiple ANF terms are
skipped, not approximated or declared different. Existing aggregate phase
checking still handles carries and compensating predicates; this is a sufficient
seed heuristic, not a replacement for that theorem.

The actual source/program/support snapshots and effective h including feedback
remain the authority. No caller may supply trusted factorizations. Even if a
seed proposal is incorrect, it is only a feature: SAT counterexamples and the
fresh unchanged phase-certificate checker remain mandatory before success.

## Why this can escape the sample frontier

For h_i=a_i*b_i and delta=product(h_i), the source has one monomial involving all
2d physical free bits. The pass recognizes its product in h without a truth table
or sampling the signature cube. With the usual constant/linear seed, this adds
one feature, so at most d+2 independent samples fit this family. With an explicit
constant-only seed, the dictionary contains just constant and product, requiring
two samples. This does not contradict the low-degree lower bound: it supplies a
high-degree feature using additional symbolic information from the actual source.

This is a restricted constructive case, not a polynomial-time sparse-learning
claim on general functions. Many real phase predicates will not be monomials;
source ANF extraction can still expand; adding irrelevant seeds can consume caps
or increase solver work. The default source_monomials=False remains unchanged.
All resource limits are shared, feature-cap overflow is inconclusive and a fresh
proof is still charged to the original deadline.

## Validation boundary

The pure factor proposal was tested locally on1600 seeded systems with20116 exact
reconstructed products. The end-to-end installed-package qualification is a
separate CI obligation on the published source: all256 two-signature source
families, invalid proposals/caps, real signature collisions and source-refusal
paths. A paired campaign compares four explicit modes (greedy/halving, seeded or
not) with the SAME64-sample cap on constructed degrees3,5,7,9,16,32. Every positive
is freshly rechecked externally. Large cases are symbolic proofs, not exhaustive
density simulations. The two-sample variant is explicit in tests, not silently
used to bias the linear-seed benchmark.

```bash
python -m pytest -q tests/test_phase_separator_source.py
python -m benchmarks.phase_separator_source --output evidence/source-seeds.json
```

Runtime results are pending until the exact-source qualification is inspected.
Do not infer speedups from feature counts. No default engine, stable API,
coherent-control permission or external support-preparation proof is introduced.
