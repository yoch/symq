# Affine derivative bases and bounded lift caching

This is a reproducible development study layered on the
[source-bound affine phase checker](affine-phase.md). Its purpose is to compare
the complete cost of choosing a different kernel basis with a simpler bounded
cache. `symq.labs.affine_basis_study` is opt-in research code with no API promise.
The existing checker, its defaults, and its receipt schema remain unchanged.

The motivating question is whether a basis adapted to phase predicates reduces
the exact directional proof cost. Merely lowering a vector's Hamming weight
does not capture invariance of a dense parity or the growth of its Boolean
substitution. A necessary control is the canonical basis with repeated modular
lifts cached: the published implementation can lift the same predicate at many
directions.

## Exact obligation

The input contract is the one proved from actual source programs by
`affine_phase`: the compared channels are `(U_left tensor I_A) o D` and
`(U_right tensor I_A) o D`, all quantum outputs are retained, and measurement
outcomes are forgotten. `D` must restore data and zero ancillas on the declared
nonempty affine support. Its extracted signature must be affine in the support
parameters. U programs act on the data wires and extend by identity on D's
ancillas. This study adds no inferred preparation or supplied signature.

Let `H` be the signature matrix in these parameters and `delta` the relative
dyadic phase after source interpretation. The exact obligation is

\[
  \delta(z\oplus v)-\delta(z)=0\pmod {2^k}
  \quad\text{for all }z\text{ and all }v\text{ in a basis of }\ker H.
\]

Invariance under a complete basis implies invariance under every sum of its
vectors by successive translation. Thus an invertible basis change preserves
the theorem. The experiment independently checks membership in `ker H`, the
nullity from row rank, each selected vector's coordinates in the canonical
basis, exact reconstruction, and the full rank of the change-of-basis matrix.
Incomplete, dependent, out-of-kernel and malformed bases cannot establish a
result. Every final derivative is computed exactly, even if the score predicted
that all predicates would be invariant.

The canonical source-bound receipt is retained. A proof with a different full
basis establishes the same equality; receipt replay deliberately uses the
published canonical checker again. A positive trial requires a receipt, the
correct source digest, and a successful fresh canonical replay. This is a
recomputable receipt, not an independently checked formal proof object.

## Methods compared

| Method | Work performed |
| --- | --- |
| `published` | Calls the pinned published `check_affine_phase`. |
| `canonical` | Instrumented orchestration with the canonical basis, rank validation, and no lift cache. |
| `canonical_cache` | The same instrumented path with a bounded per-call LRU lift cache. |
| `hamming` | Selects an independent basis from the bounded candidate pool ordered by Hamming weight. |
| `adaptive` | Selects from that pool using predicate invariance and a substitution/lift cost proxy. |
| `adaptive_cache` | The adaptive basis plus the same bounded lift cache. |
| `canonical_precompute` | Canonical basis; `lift(p, −c)` pinned once per predicate outside the LRU. |
| `canonical_complement` | As above, plus the complement identity and an affine parity shortcut. |
| `canonical_split` | Complement plus the Boolean-derivative split for nonlinear predicates. |
| `canonical_factorized` | One lift of the non-invariant phase, translated as a pseudo-Boolean polynomial. |

Both the direct published baseline and the instrumented canonical control are
needed: validating the basis and collecting counters themselves have a cost.
No performance threshold is a CI gate.

The deterministic candidate pool contains the canonical basis, directions in
the kernel of `H` augmented by the linear forms of affine phase predicates,
and pairwise sums of canonical directions. Duplicate directions are removed.
For each manageable predicate/direction pair, the heuristic computes the exact
Boolean translation. Invariance predicts that the modular lift can be skipped.
Other scores use saturated combinatorial bounds on the number of lift additions
and the raw substitution size. Large probes are scored as unknown and expensive.
The score does not certify anything and is not a global runtime optimum.

The search is bounded by kernel dimension, candidates, probe size, an explicit
work counter, and the original proof deadline. The default caps are 64 kernel
dimensions, 128 candidates, 2,048 raw translation terms per probe, and 250,000
search work units. A soft search-cap fallback uses the complete canonical basis
and the same remaining deadline; it does not reset the clock. It can still lose
time on negative or already-invariant instances.

## Cache and resources

The cache key is `(Boolean predicate, coefficient mod modulus, modulus)`.
Each invocation owns a fresh cache. Its default limits are 128 entries and
16,384 retained term units, counting the predicate key and lifted polynomial.
Oversized entries are not stored, and deterministic LRU eviction makes room for
other entries. Consumers only read the cached polynomials.

The statistics used to count distinct lift keys are also bounded. Their term
units and cache units together respect the inherited term cap; incomplete key
counts are marked as lower bounds. The global guard covers configuration
freezing, source validation, preparation, selection, proof, source/witness
replay inside the proof, scratch cleanup, and final receipt-to-dictionary
conversion. Boolean and integer subclasses, forged dataclass metadata, and
invalid settings cannot silently replace a supplied cap with a default.

The published meaning of `max_terms` is preserved: it bounds the accounted
explicit polynomial/collection sizes, not Python RSS or every simultaneously
live object. A time budget is cooperative, not a hard process termination
guarantee. The harness additionally terminates a stuck subprocess and records
that failure. Cache residency is reported separately from process memory.

## Development fixtures

An exact identity supplies useful positive instances:

\[
  p+q-(p\oplus q)-2pq=0.
\]

Real reversible circuits compute predicates into three data workspace wires,
apply the four dyadic phases, and uncompute. The explicit affine input support
fixes those workspace inputs to zero. Several dense linear presentations,
nonlinear predicates, nonzero offsets and invertible support coordinates are
used. Perturbing one coefficient supplies negative instances.

The fixed campaign also includes single dense phases, partial and full
dephasing, already-invariant predicates, grouped cancellation, output
mismatches, a deliberately small cache with evictions, a soft selection
fallback, an expansion term cap, and a short deadline. Nine labelled
`variation_*` cases (32 in all) were added for the lift-reuse methods. They
vary the coefficients and their 2-adic valuation (`scale`), the moduli, and the
kernel directions (mixed and partial supports). They include an adversarial
near-invariant dense predicate and a `fibre_constant` positive whose phase is
constant on fibres but not identically zero. Apart from those and
`measured_dense_predicate` (one predicate, invariant along every direction), every
generated positive has an identically zero relative phase. All are development fixtures generated
here; none is a holdout or an external compiler corpus.

Independent tests compare every matrix unit on small declared supports using
actual Kraus branches and a separate integer dyadic interpreter. Larger
negative benchmark trials independently replay their returned matrix-unit
witnesses. These references use no ANF, kernel, translation, or modular-lift
helpers from the implementation under study.

## Lift reuse within one proof

The audit of the cache control found that the published derivative recomputes
direction-independent work. For every kernel direction `v` and every
non-invariant predicate `p` with coefficient `c`, it lifts `τ_v p` with `c` and `p`
with `−c`. The second lift does not depend on `v`. The
[algebra note](../labs/affine-lift-reuse.md) proves the following identities.
Every route returns the unique multilinear representative of the same derivative
function, so decisions, witnesses and receipts are identical to `published`.

- `canonical_precompute` pins `lift(p, −c)` once per predicate. It is filled
  lazily and lives outside the LRU, but it is charged to the same term budget.
- `canonical_complement` adds the complement identity:
  `c[p ⊕ 1] − c[p] = c + lift(p, −2c)`, which is direction-free and one level
  shallower. An affine predicate is only ever invariant or complemented, so it
  is classified by a parity test, with no substitution.
- `canonical_split` adds the Boolean-derivative split. With `d = p ⊕ τ_v p`, it
  computes `c[p ⊕ d] − c[p] = lift(d, c) + lift(p·d, −2c)`. The second lift is
  pinned when `p·d = p`.
- `canonical_factorized` lifts once only the predicates that some basis direction
  moves. It then translates that pseudo-Boolean polynomial with
  `z_j → 1 − z_j`. Lifting *every* predicate is valid but hits the term cap on
  `measured_dense_predicate`, where `published` lifts nothing.

Measured on one development machine (Python 3.13). The campaign has 32 cases, 10
methods and 3 repetitions: 960 trials, all qualified. The only inconclusive trials
are the 60 expected cap/deadline trials, and coverage is identical for every
method. Ratios are paired geometric means over the decided trials. The brackets
give the paired minimum and maximum. "Call" is the whole proof call. "Full" adds
fixture construction and the fresh published replay. "Proof" is the derivative
loop alone; `published` has no such timer.

| Method | Call vs `published` (63 eq / 27 neg) | Call vs `canonical_cache` (eq / neg) | Full vs `canonical_cache` (all) | Proof vs `canonical_cache` (all) |
| --- | --- | --- | --- | --- |
| `canonical_cache` | 0.47 [0.19–1.33] / 1.06 [0.76–1.26] | — | — | — |
| `canonical_precompute` | 0.47 / 1.16 [0.75–10.8] | 1.00 [0.64–2.07] / 1.09 | 1.01 | 1.02 |
| `canonical_complement` | 0.40 / 0.84 | 0.86 [0.32–2.05] / 0.80 [0.29–1.47] | 0.90 | 0.75 |
| `canonical_split` | 0.25 / 0.66 | 0.53 [0.17–1.71] / 0.62 [0.29–1.08] | 0.80 | 0.45 |
| `canonical_factorized` | 0.16 / 0.91 [0.42–6.14] | 0.34 [0.07–1.11] / 0.87 [0.46–5.89] | 0.83 | 0.33 |

The untimed companion (`benchmarks.affine_basis_operations`) counts lifts
expanded and coefficient additions over the 30 decided cases:

| Method | Lifts | Additions |
| --- | ---: | ---: |
| `published` | 1012 | 2.24 M |
| `canonical_cache` | 299 | 0.85 M |
| `canonical_precompute` | 276 | 0.84 M |
| `canonical_complement` | 208 | 0.72 M |
| `canonical_split` | 265 | 0.52 M |
| `canonical_factorized` | 91 | 0.60 M |

The per-case findings are:

- **`canonical_precompute` is a negative result.** It has no gain over the LRU
  control except when the LRU is starved: `cache_evictions` runs at 0.65× in the
  call and 0.64× in the proof. When both tables hold a large lift, it retains up
  to twice the terms (29.8k against 14.9k on `variation_near_invariant_dense`).
- **`canonical_complement`** wins clearly when affine predicates carry the cost:
  `early_negative` 0.48× and `variation_near_invariant_dense` 0.33× against the
  cache. Elsewhere it is close to 1.
- **`canonical_split`** is the most even improvement. It has one robust
  regression: nonlinear predicates in mixed coordinates
  (`variation_nonlinear_mixed`), at 1.46× against the cache and 0.91× against
  `published`. There, `p·d` is larger than `τ_v p`.
- **`canonical_factorized`** has the largest mean gain. Most of it comes from
  whole-phase cancellation: almost every generated positive has an identically
  zero relative phase. On the two `fibre_constant` positives, whose phase is not
  zero, it matches `canonical_split` (0.45× and 0.64×). It has an unbounded
  adversarial loss: a dense predicate that is non-invariant along only one
  direction (`variation_near_invariant_dense`) runs 5.8–6.1× slower than both
  baselines.
- Cases with no lift to reuse (singleton fibres, invariant or grouped
  predicates, output mismatch) are unchanged, up to sub-millisecond timer
  noise. Single large outliers there, such as 10.8× once on `output_mismatch`,
  disappear in a 9-repetition rerun (medians 0.78–1.04 against the cache).
- Under tracemalloc, the reuse methods' peak memory relative to the cache
  control is at most 1.26× (`canonical_precompute`). `split` and `factorized`
  are lower on average. RSS is dominated by the interpreter and is not
  informative here.

The conclusion is mixed. Pinning alone, idea (a), is a negative result. The
complement and split identities are exact, cheap to state, and give robust
gains on these fixtures, with one documented regression for `split`.
Factorization is fastest on average but has a large, constructible worst case,
and its average depends on the fixture mix. All four remain documented study
methods. None is a default, and no general speedup is claimed. The fixtures are
small generated development cases, there is no holdout, the timings come from
one machine, and the runs use only the canonical basis.

## Reproduce and inspect the evidence

Run from a source checkout. The qualification requires the exact bytes of the
published baseline module (SHA-256 pinned in `benchmarks/affine_basis.py`) and
that the imported module is that checkout's file; any other bytes are refused.
Whether the published baseline commit
`cd315955256dfeebd7beeb67533c2c4ef2122bde` is an ancestor is recorded as
`baseline_lineage`, not required, so a squash or rebase merge or a shallow
clone does not break the check. The dedicated workflow keeps full history:

```bash
python -m pytest -q tests/test_affine_basis_study.py tests/test_affine_basis_qualification.py
python -m benchmarks.affine_basis --repetitions 3 --output evidence/affine-basis.json
python -m benchmarks.affine_basis_summary evidence/affine-basis.json --output evidence/affine-basis-summary.json
python -m benchmarks.affine_basis_operations --factorized --output evidence/affine-basis-operations.json
```

The harness refuses an altered published `affine_phase.py` baseline. It records
the actual checkout commit and dirty state, source digests, machine/interpreter,
settings, per-case budgets, deterministic method order, every repetition,
every status/error, cache counters, and all replay outcomes. Each worker checks
source-file identity at the beginning and end; the parent compares it with its
own pinned snapshot. A fresh interpreter runs each proof; there is no cache
shared across trials.

`total_seconds` is the whole proof call, including semantic preparation and
selection. Fixture generation is outside that API call and separately recorded;
construction-plus-proof fields are supplied too. A fresh canonical receipt
replay has a new deadline with the same ceilings. Its cost and status are
recorded separately, along with proof-plus-replay and
construction-plus-proof-plus-replay totals. These totals do not claim to fit
inside the single proof-call budget. Independent oracle checks are correctness
qualification, not a competing checker timing.

Process memory uses Linux `ru_maxrss` and includes interpreter/import/launch
cost, potentially inherited fork pages. It cannot by itself isolate the
cache's allocation cost. The raw record also contains the explicitly accounted
cache term peak. No memory superiority is inferred from the process figure.

Expected cap cases may qualify as correctly inconclusive; they never count as
proved instances or successful timing pairs. `--require-decision` instead makes
any inconclusive trial fail qualification. Missing receipts, replay exceptions,
wrong source digests, invalid witnesses, and missing workers always fail.
The JSON is written before exit status 1, and other trials continue after an
individual failure. A provenance/setup refusal also writes a failed JSON with
its reason and no trials. The workflow uploads raw records even on failure; raw
results are not committed.

Interpret the paired distributions and the negative/adverse cases together.
Saving lift calls is a structural observation, while beating the bounded-cache
control after selection is a separate empirical claim. The study supports
retaining negative results and exploring caching independently. It does not
promote an adaptive default, claim general speedup, or establish SOTA.
