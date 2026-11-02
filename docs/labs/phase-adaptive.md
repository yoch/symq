# Obstruction-guided adaptive phase dictionaries (research)

This continues #163 after merging audited main@755385e into its existing branch.
The fixed-dictionary engine and the independent source certificate checker are
unchanged. No default engine, stable API or channel theorem is broadened.

## Why enrich a dictionary rather than enumerate a degree layer?

A fixed feature dictionary may be insufficient even though the two channels are
equal. Raising the maximum degree generates all combinations of signature bits,
which can hit the feature cap before one useful nonlinear term is tried.
The adaptive route starts with a small seed (constant and linear terms by default),
retains all literal-source counterexamples, and adds one justified column at a time.

## Finite rank certificate and constructive separator

Let A be the Boolean feature-evaluation matrix on the current samples, and b their
k-bit source phase labels. Elimination produces a nonempty sample subset S with
XOR(feature rows)=0 and XOR(labels)!=0. Duplicate signature words with different
labels are already a genuine, source-replayed coherence counterexample. Otherwise
the signature words in S are distinct.

Choose a word y in S maximal under set inclusion (maximal popcount suffices).
The positive monomial whose mask is y evaluates to one on y and on no other word
of S. Hence its column v satisfies q^T v=1, whereas q^T A=0. It cannot lie in the
old column span; adding it increases evaluation rank exactly once. Greedy removal
of factors while preserving odd parity makes it deletion-minimal, not globally
minimum-degree. The code checks the rank increase on the obstructed sample prefix.
A new column need not make the previously failing row independent: it may break
an earlier dependency while another obstruction remains. The completion loop
must continue in that case rather than reject the valid rank increase.

For a fixed sample set of N distinct words, at most N-rank(A) such additions are
needed to make every label bit jointly representable. Across counterexamples the
number of accepted samples still bounds total feature additions. Each refuting
query either introduces a new signature word or finds a real fibre collision.
Without resource limits, finite signature images therefore terminate; the image
may be exponentially large. No polynomial runtime, optimal sparsity or SAT bound
is implied. All bits share one GF(2) system; no arithmetic over Z/(2^k) is treated
as field elimination.

The source DAG/signature are prepared once for learning and reused during feature
refinement. Positive results still require a NEW run of the unchanged source-bound
nonlinear phase checker, with matching source/certificate identities and the same
original deadline. Learned samples, masks and rank diagnostics never authorize
acceptance on their own.

## Incremental interpolation and explicit baseline

`reuse_basis=True` inserts each independent new sample into the existing echelon
form. Rebuilding is needed only when an obstruction requires feature growth.
`reuse_basis=False` deliberately rebuilds on every sample and remains a paired
reference. Tests require identical verdicts, candidates, samples, growth records
and SAT graphs between these modes, apart from timing/rebuild accounting.

The qualification retains three complete-call timing trials per mode. Fewer
rebuilds do not establish an end-to-end speedup: parsing, source extraction, SAT,
scalar replay and fresh checking may dominate. The observed small timing changes
have mixed signs and are not presented as statistically significant gains.

## Explicit failure and retained limitations

- `proved`: a discovered candidate passes fresh source checking.
- `different`: source-replayed output mismatch or equal effective signatures with
  different actual deltas; it is never inferred from a feature cap.
- `not_proved`: a source obligation such as dephaser restoration is outside this theorem.
- `inconclusive` or `unsupported`: feature/sample/round/resource/dependency refusal.

The initial dictionary is a seed, NOT an instruction to forbid larger-degree terms.
Caps are strict, sources are detached, and shared VerificationSession limits apply.
A wrong separator or fresh verifier result must fail closed. SAT UNSAT remains
trusted; no portable certificate or proof log is claimed. Existing source ANF
extraction can still grow. This can be slower than a well-chosen fixed dictionary.

Counterexample to minimum-degree claims: S=(2,3,4,5,6,7,8,9) annihilates every
constant/linear feature. Our deterministic greedy separator returns mask7 of
degree3, though mask9 of degree2 also separates it. The regression retains this
negative result rather than claiming optimal feature discovery.

## Qualification

The pure separator was executed locally on all 65,808 nonempty subsets of Boolean
cubes of widths 1..4, plus 500 seeded sets at widths 8,24,48,128,256. Every result has
odd incidence and passes deletion-minimality checks on the exhaustive set. A
separate pure interpolation test covered 1,200 systems and 13,987 column additions.
These are pure-kernel results, NOT local installed SymQ or PySAT validation.

The dedicated installed-package workflow checks all 256 h=(ab,bc)->Z/4 source
families against the independent exact channel oracle, replayed rank obstructions,
real fibre collisions, unreachable signatures, affine offsets, resource limits,
hostile helper outputs and late expiry. New tests include the rank-progress
regression, randomized completion and an irregular three-input modulo-256 source.
The campaign pairs fixed linear/quadratic and adaptive discovery, then records
all outcomes (including resource refusals) on sparse nonlinear-signature families.
Larger cases are symbolic source proofs, not enumeration or independent matrix
simulation of their cubes.

```bash
python -m pytest -q tests/test_phase_adaptive.py tests/test_phase_adaptive_completion.py
python -m benchmarks.phase_adaptive --output evidence/phase-adaptive.json
```

[Exact executable checkpoint evidence](../evidence/phase-adaptive-2026-11-02.md)
includes successes, safe refusals, timing regressions and the initial overstrict
assertion. All data are synthetic development data, not an untouched holdout.
Current HEAD CI must be read separately before adoption; prior receipts are not
silently re-labelled after a code or documentation change.

## Prior art and positioning

CEGIS and syntax-guided synthesis are established techniques, not new claims:
[Alur et al., Syntax-Guided Synthesis, FMCAD2013](https://escholarship.org/uc/item/1g67m7hp),
[Abate et al., CEGIS Modulo Theories, CAV2018](https://www.repository.cam.ac.uk/handle/1810/287744).
Sparse Boolean-polynomial interpolation also has a long history:
[Roth and Benedek, SIAM J. Computing1991](https://doi.org/10.1137/0220019).
This note derives and checks a concrete obstruction-driven enrichment mechanism
for SymQ's source-bound phase problem. It does not establish global research
novelty, a sparse-learning complexity improvement or superiority to those methods.
