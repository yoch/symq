# Exact bilinear synthesis with reusable linear frames

**Status:** opt-in experimental generator, not a circuit optimizer that discovers
bilinear factors. See [the public Kaggle corpus provenance](../../benchmarks/corpus/kaggle_bilinear/SOURCE.md)
and the [substitution qualification matrix](../../benchmarks/substitution_qualification.md).

## Mathematical and software contract

For integer bitmasks `u`, `v`, `w`, a factor
`Term(u, v, w)` contributes

`parity(u & a) * parity(v & b) * w`

by XOR to the `n`-bit accumulator `z`. The generated reversible circuit
implements the complete **dirty-register** permutation

`(a, b, z) -> (a, b, z XOR product_of_factors(a,b))`.

Every source wire is preserved, all transient linear frames are restored, the
original `z` may contain any bit pattern, and **no extra qubits** are used.
Only CX/CCX gates are emitted. Because these gates are exact basis
permutations with no phases or measurements, whole-function equivalence on
all basis states entails equality of the corresponding permutation unitaries.
It does *not* prove a local replacement safe under an unproved cut
precondition, HMR instrument equivalence, or correctness of the supplied
factorization.

## Usage

```python
from symq.generators import gf2n
from symq.generators.bilinear_optimization import certify_decomposition

terms = gf2n.karatsuba(2)
certify_decomposition(2, terms, modulus=0b111)

old = gf2n.emit(2, terms)  # existing incidence-per-target emitter
pivot = gf2n.emit(2, terms, strategy="pivot")
scheduled = gf2n.emit(2, terms, strategy="pivot-scheduled")
assert pivot.ccx == scheduled.ccx == len(terms)
assert scheduled.cx <= pivot.cx
```

`strategy="incidence"` is the **unchanged default**. `"pivot"`
preserves factor order but uses dynamic programming to select the best
in-register parity pivots; `"pivot-scheduled"` also considers a bounded
greedy term order and, for at most 32 factors, deterministic 2-opt segment
reversals. All modes preserve the same bilinear function. `share=True` is
only supported by the original incidence emitter (and is rejected alongside
the new strategies rather than silently ignored). Term masks must be
nonzero, within `n` bits, and genuine `Term` instances. The scheduled
mode refuses more than 1,024 terms instead of doing unbounded quadratic
search. `MAX_2OPT_TERMS` is 32.

`gf2n.multiplier(n, method, strategy="pivot-scheduled")` applies the
same lowering to existing schoolbook, Karatsuba and coordinate-slice
factorizations; its default strategy remains the old one. It continues
to use the fixed modulus `gf2n.MODULI[n]`. For external field bases (for
example GF(64) modulo `0x49`, *not* SymQ's pinned `0x43`),
call `certify_decomposition(n, terms, 0x49)` and pass those exact
`Term` objects to `emit`. The certificate checks the complete
GF(2) tensor and irreducibility of the declared modulus. The emitter
never guesses a modulus from a term list.

## Why the output register can be dirty

For an output pivot `p` and another target output `k`,
the conjugation `CX(p,k) ; CCX(u,v,p) ; CX(p,k)` adds the same product
to both `p` and `k`, *without* adding the original value of `p`
to `k`. For many terms, the input parity folds and output conjugation
frames may remain active between successive CCX gates. Each frame is
tracked as `(pivot, original-variable mask)`. A transition keeping the
same pivot toggles exactly the symmetric difference of the masks;
switching pivots first undoes the old frame. After the last CCX,
every frame is restored to identity. A per-register DP minimizes these
CNOT transition costs for a fixed factor order; a deterministic heuristic
also searches better orders. **Only CX count**, not rank, is optimized by
this scheduler.

## Source-pinned public qualification (1 November 2026)

James Barlow's [VQCC bilinear KMB agent-evaluation dataset](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation)
is an exposed 14-instance *development* corpus, declared Apache-2.0.
The independent factor reconstruction follows GF(4)-tower
interpolation mathematics described in [Polytof](https://github.com/ZIB-IOL/polytof),
MIT, exact upstream commit
`0dcac107d15adc34dc646242d222f21ae7d32699`.
See the exact source-upload and file checksums in `SOURCE.md`;
the live Kaggle dataset version was not independently identified.

| Field (seven circuits each) | Prior pivot emitter | New scheduled emitter |
| --- | ---: | ---: |
| GF(16), modulus `0x13` | 9 CCX, 62 CX | **9 CCX, 30 CX** |
| GF(64), modulus `0x49` | 15 CCX, 174 CX | **15 CCX, 82 CX** |
| All 14 KMB starts | **240 CCX, 1,862 CX** | **168 CCX, 784 CX** |

The new candidate KMB bytes were checked against the **original author's
unmodified `evaluate.py`** for all 14 original IDs: 14/14 valid, 14/14
improved, and 14/14 reached the published bilinear targets. The
independent polynomial reference and a separate basis simulator checked
all 4,096 GF(16) and 262,144 GF(64) complete inputs on the two distinct
generated circuits. The GitHub tests also cover factor mutations,
incorrect moduli, randomized larger multipliers, original KMB payload
hashes, and a full-context permutation comparison with a negative mutant.

These results do not demonstrate blind optimizer discovery, a new
bilinear-rank lower bound, a general optimal CNOT network, a contextual
cut-proof, or an official Kaggle competition score improvement. The
exhaustive small-size tests and published-source evaluator checks
qualify only the exact pinned workload and implementation.

## Reusable exact GF(4)-tower factor construction (n = 4 or 6)

The experimental **production generator** `symq.generators.gf2n.tower_factors`
constructs 9-factor GF(16) and 15-factor GF(64) bilinear decompositions for
an explicitly declared irreducible degree-`n` binary modulus. It is
self-contained in `src/symq/generators/bilinear_factors.py`: no imported
Kaggle files, external Python dependencies or runtime network calls.

```python
from symq.generators import gf2n

terms_43 = gf2n.tower_factors(6, modulus=0x43)
terms_49 = gf2n.tower_factors(6, modulus=0x49)
assert len(terms_43) == len(terms_49) == 15

native = gf2n.tower_multiplier(6, modulus=0x43)
external = gf2n.tower_multiplier(6, modulus=0x49)
assert native.counts()["ccx"] == external.counts()["ccx"] == 15
```

Both circuits implement the complete reversible permutation on **18 dirty
qubits**, but their encoded multiplication tables differ. Never substitute
their coefficient masks without a proved field-basis conversion. The
`tower_multiplier` default uses `pivot-scheduled`; the original
`gf2n.multiplier(n, method=...)` default is unchanged.

Before synthesizing, the builder finds an explicit GF(2)-linear
isomorphism from the polynomial basis to either GF(4)[z]/(z²+z+ω) (n=4)
or GF(4)[z]/(z³+z+1) (n=6). It generates the rank-one terms by
interpolation, checks the modulus is irreducible and certifies **all**
multiplication-tensor coefficients. It rejects any other degree or bad
polynomial rather than silently treating different bases as equivalent.
An immutable cached internal factor tuple is copied before exposure.

This construction is independently coded but uses previously published
finite-field multiplication mathematics. Academic/method provenance:
[Polytof](https://github.com/ZIB-IOL/polytof), MIT licence, exact
upstream commit `0dcac107d15adc34dc646242d222f21ae7d32699`.
The separate public validation corpus is by James Barlow, declared
Apache-2.0, with pinned original bytes and hashes in
[the Kaggle source record](../../benchmarks/corpus/kaggle_bilinear/SOURCE.md).
These two origins must not be conflated. A rank-15 *construction* is not
a new lower-bound proof. The optional adapter is not a certified contextual
replacement without satisfying its insertion contract.

Tests compare the new core factor generator against the previously
independent benchmark implementation, certify the GF(2) tensor,
reject corrupted terms and wrong polynomials, verify all operand pairs
with dirty outputs in both GF64 representations, and exercise a complete
reversible surrounding context. Their correctness claim is scoped to the
exact code and inputs checked.
