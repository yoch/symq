# GF(2^n) multiplier synthesis

**Status: experimental.** The generators live in `symq.generators.gf2n` and the GF(2^24)
pieces in `symq.labs`; neither is a stable API. They build specific reversible multipliers
from bilinear factorizations that are given or constructed, and do not discover new
factorizations. To use a generated multiplier inside a larger circuit, prove the rewrite with
the [rewrite guide](rewrite.md).

## The circuits

A factor `Term(u, v, w)` over integer bitmasks contributes `parity(u & a) * parity(v & b) * w`
by XOR to the `n`-bit accumulator `z`. `gf2n.emit(n, terms, strategy=...)` emits a CX/CCX
circuit on `3n` wires that computes the whole dirty-register permutation

```text
(a, b, z) -> (a, b, z XOR sum of the factors)
```

Every source wire is preserved, the original `z` may hold any value, there are no ancillas,
phases or measurements, and the circuit has exactly one CCX per factor. Because these gates are
basis permutations, equality on every basis state is equality of the permutation unitaries.

| Strategy | What it does |
| --- | --- |
| `incidence` (default) | The original emitter; the only one that accepts `share=True`. |
| `pivot` | Keeps the factor order and picks in-register parity pivots by dynamic programming. |
| `pivot-scheduled` | Also searches a bounded greedy factor order, with 2-opt reversals for at most 32 factors; refuses more than 1,024 factors. |

Only the CX count is optimized; the CCX count is the number of factors. Factor masks must be
nonzero `Term` instances within `n` bits.

The pivot strategies keep linear frames open between Toffolis. For an output pivot `p` and
another output `k`, the conjugation `CX(p,k) ; CCX(u,v,p) ; CX(p,k)` adds the product to both
`p` and `k` without adding the old value of `p` to `k`. Each frame is a pair
`(pivot, mask of original variables)`; moving between frames on the same pivot toggles the
symmetric difference of the masks, and every frame is restored after the last Toffoli. This is
why the output register may be dirty.

```python
from symq.generators import gf2n
from symq.generators.bilinear_optimization import certify_decomposition

terms = gf2n.karatsuba(2)
certify_decomposition(2, terms, modulus=0b111)
pivot = gf2n.emit(2, terms, strategy="pivot")
scheduled = gf2n.emit(2, terms, strategy="pivot-scheduled")
assert pivot.ccx == scheduled.ccx == len(terms)
assert scheduled.cx <= pivot.cx
```

`gf2n.multiplier(n, method, strategy=...)` applies the same lowering to the schoolbook,
Karatsuba and coordinate-slice factorizations in SymQ's fixed modulus `gf2n.MODULI[n]`.

## Field arithmetic and certificates

`symq.generators.gf2n` holds one copy of the field arithmetic: `gf_mul`, the multiplication
`tensor` and a Rabin `is_irreducible` test for any binary modulus.
`certify_decomposition(n, terms, modulus)` checks that the modulus is irreducible and that the
factors reproduce every coefficient of the `n x n x n` multiplication tensor. The emitter never
guesses a modulus; for a basis other than SymQ's default, such as GF(64) modulo `0x49` instead
of `0x43`, certify against that modulus and pass the same factors to `emit`.

## Tower factors for GF(16) and GF(64)

`gf2n.tower_factors(n, modulus=...)` builds a 9-factor GF(16) or 15-factor GF(64) factorization
for any irreducible modulus of degree 4 or 6. It finds an explicit GF(2)-linear isomorphism to
`GF(4)[z]/(z^2+z+w)` (n=4) or `GF(4)[z]/(z^3+z+1)` (n=6), interpolates, and certifies the whole
tensor before returning. Arguments are validated before the cache is consulted, so
`tower_factors(4.0, modulus=19.0)` is refused. `gf2n.tower_multiplier` emits it with
`pivot-scheduled`.

```python
from symq.generators import gf2n

native = gf2n.tower_multiplier(6, modulus=0x43)
external = gf2n.tower_multiplier(6, modulus=0x49)
assert native.counts()["ccx"] == external.counts()["ccx"] == 15
```

Both circuits act on 18 dirty qubits, but they compute different multiplication tables. Never
swap one for the other without a proved change of basis.

## GF(2^24): a 99-product tower

SymQ's GF(2^24) basis is `GF(2)[x] / (x^24 + x^4 + x^3 + x + 1)`, modulus `0x100001B`.
`symq.labs.gf24_tower.gf24_tower_factors()` embeds GF(16) (`x^4+x+1`) in that basis, writes the
field as a degree-six extension of GF(16), and evaluates the degree-five operands at 10 points
of GF(16) and infinity. Each of the 11 point products uses the 9-factor GF(16) construction, so
the factorization has 99 products. The whole 24 x 24 x 24 tensor is checked before the factors
are returned, and the factor list is pinned by its SHA-256 fingerprint
`549b1c30d2bee1a35fca79d96defd4ad99870a4fb59f0d9b9960fe125472c88a`.

The pinned GF(16) subfield root `0xB781C5` and outer generator `x^4` were selected by a 96-case
basis grid in `benchmarks/gf24_basis_scan.py`. A separate search over factor orders,
`benchmarks/gf24_order_search.py`, found the order pinned in `symq.labs.gf24_order`, which the
exact per-register pivot dynamic program emits with 2634 CX. Neither search is a global optimum.

| Circuit on 72 qubits | CCX | CX |
| --- | ---: | ---: |
| Schoolbook, incidence emitter | 1,419 | 0 |
| Karatsuba, `pivot-scheduled` | 162 | 1,856 |
| 99-product tower, `pivot-scheduled` | 99 | 2,750 |
| 99-product tower, pinned order | 99 | 2,634 |

`tests/test_gf24_rewrite.py` proves exactly, on all 2^72 inputs, that the schoolbook circuit's
output polynomials are the field tensor and that the Karatsuba and pinned-order circuits equal
the schoolbook circuit. It uses the packed degree-two engine, with no sampling and no SAT solver.

## Choosing and rewriting a GF(2^24) multiplier

`symq.labs.gf24_choice.choose_gf24(ccx_weight=..., cx_weight=...)` picks the cheapest of the
three circuits under declared non-negative integer weights. The tower wins over Karatsuba when
the CCX weight is more than 778/63 (about 12.35) times the CX weight. The weights are a declared
proxy, not a T-count, a fault-tolerant cost or a hardware duration, and the choice alone proves
nothing about where the circuit is inserted.

`symq.labs.bilinear_substitution.gf24_rewrite` replaces a 72-wire multiplier block inside a
larger circuit, on an explicit wire map, and proves it with the total theorem on the packed
engine. A block of degree above two is `unsupported`, not guessed.

```python
from symq.labs.gf24_choice import choose_gf24
from symq.labs.gf24_order import pinned_gf24_emitted

assert pinned_gf24_emitted().cx == 2634
assert choose_gf24(ccx_weight=32, cx_weight=1).method == "tower-99-pinned-order"
```

`examples/gf24_rewrite.py` runs a whole rewrite with its receipt and replay.

## Public evidence: the bilinear KMB corpus

[benchmarks/corpus/bilinear_kmb](../../benchmarks/corpus/bilinear_kmb/SOURCE.md) redistributes,
under Apache 2.0, the 14 GF(16) and GF(64) multiplier circuits of a public dataset by James
Barlow, with their checksums. `python -m benchmarks.bilinear_kmb` proves each file equal, on
every input, to `tower_multiplier` in the same basis, with the packed engine.

| Field (seven files each) | `pivot` | `pivot-scheduled` |
| --- | ---: | ---: |
| GF(16), modulus `0x13` | 9 CCX, 42 CX | 9 CCX, 30 CX |
| GF(64), modulus `0x49` | 15 CCX, 136 CX | 15 CCX, 82 CX |

| All 14 files | CCX | CX |
| --- | ---: | ---: |
| Source circuits | 240 | 1,862 |
| Tower multipliers | 168 | 784 |

The 9- and 15-product targets are published with the dataset, and the corpus was explored during
development. These results are a constructive baseline on an open set, not a holdout.

## Provenance and limits

The tower construction follows the GF(4)-tower interpolation described by
[Polytof](https://github.com/ZIB-IOL/polytof) (MIT, commit
`0dcac107d15adc34dc646242d222f21ae7d32699`). No Polytof code is included, and the KMB corpus is
a separate source. The 9-, 15- and 99-product factorizations are constructive upper bounds, not
proofs of minimal bilinear rank, and the CX counts are not proved optimal. The GF(2^24) results
do not use the KMB corpus, which has no GF(2^24) case.
