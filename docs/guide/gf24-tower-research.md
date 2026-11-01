# GF(2^24) rank-99 tower: exact construction and gated cost comparison

**Status: experimental, not a stable API.** This builds a *specific*
reversible multiplier, not a general DQI decoder or quantum optimization
pipeline. It is deliberately separate from the verified GF16/GF64 KMB
case studies and from the classical contextual rewrite contract.

## Exact mathematical object

SymQ's **pinned polynomial basis** is

```text
GF(2^24) = GF(2)[x] / (x^24 + x^4 + x^3 + x + 1)
modulus  = 0x100001B
```

The implementation in `src/symq/labs/gf24_tower.py` explicitly finds
a GF(16) subfield embedded in this polynomial basis, using the
GF(16) polynomial `x^4+x+1` (`0x13`). It checks that the resulting
24 vectors `alpha^i * x^j` form a full GF(2) basis, calculates a
degree-six reduction relation over GF(16), and evaluates its
degree-five input polynomials at **10 distinct GF(16) elements and
infinity**. Interpolation reconstructs the degree-ten product and
reduces it modulo the degree-six relation.

Each of these 11 GF(16) point products uses the previously certified
**9-term** GF(2) bilinear construction. Thus the total decomposition
contains **11 × 9 = 99 binary rank-one products**. The module
reconstructs and compares the **entire 24 × 24 × 24 multiplication
tensor**, over GF(2), with the pinned GF(2^24) modulus before returning
the immutable tuple of factor masks. The deterministic factor-list
fingerprint, computed as SHA-256 over ASCII semicolon-separated
`left_hex,right_hex,output_hex`, is:

```text
52cd951205360264ea57c80bd02000da9d2c57c9db7e58e97ac6e15d14c9f54c
```

This is a *constructive upper bound* on bilinear complexity, **not a
proof of the optimal rank**, nor a new independently checked formal
proof artifact. The original source code is maintained in SymQ and
has no runtime dependency on a second repository.

## Circuit accounting

All alternatives act on **72 qubits** (24-bit A, B, and potentially
dirty accumulator Z), return the two inputs unchanged, and compute
`Z ^= A*B`. Each circuit contains only CX and CCX gates, with no
ancilla, measurement, reset, phase or postselection.

| Method | CCX | CX | Qubits |
| --- | ---: | ---: | ---: |
| Schoolbook, original incidence emitter | 1,419 | 0 | 72 |
| Karatsuba, pivot-scheduled | 162 | 1,856 | 72 |
| GF16-tower rank-99, pivot-scheduled | **99** | 2,896 | 72 |

The rank-99 method saves 63 CCX compared with the Karatsuba
pivot-scheduled realization but adds 1,040 CX. A user-declared,
nonnegative integer proxy `ccx_weight*CCX + cx_weight*CX`
prefers rank-99 over Karatsuba when `ccx_weight/cx_weight` is
**strictly greater than 1040/63 ≈ 16.51**. Schoolbook may be cheaper
if CX is assigned extremely high weight. Neither these arbitrary
weights nor this exact gate accounting represents T-count, T-depth,
physical duration, quantum surface-code volume or the official
Kaggle competition score.

```python
from symq.generators.gf2n import emit
from symq.labs.gf24_choice import choose_gf24
from symq.labs.gf24_tower import gf24_tower_factors

factors = gf24_tower_factors()
assert len(factors) == 99
circuit = emit(24, list(factors), strategy="pivot-scheduled").circuit
assert circuit.counts()["ccx"] == 99

# A declared proxy, never a performance/scoring theorem.
choice = choose_gf24(ccx_weight=32, cx_weight=1)
assert choice.method == "tower-99-pivot-scheduled"
```

The selector `choose_gf24` considers exactly the three methods
listed above, refuses bool/float/negative/both-zero weights, and is
opt-in. It reports exact gate counts and an untrusted-to-compiler
mutable candidate circuit, **not a substitution permission or proof
receipt**. To apply the resulting circuit inside a larger program,
the caller still needs a correctly scoped substitution theorem,
appropriate phase/coherence semantics, budget and proof replay.

## Verification and negative controls

`tests/test_gf24_tower.py` independently implements integer
polynomial convolution and reduction, verifies all **576** input
basis-pair coefficients of the tensor, checks the pinned factor hash,
and rejects deleted/corrupted factors and the wrong polynomial.
It checks a seeded set of **262 complete 72-bit basis states**
against an independent oracle, including deliberately dirty
output patterns, and checks the exact three circuit cost records
and the proxy-selection boundaries. Unlike the 12/18-wire tests,
this is **not exhaustive over 2^72 input states**. The exact tensor
certificate plus the separately tested reversible synthesis rule
supports the construction; the sampled whole-circuit tests are a
regression guard, not a formal independent circuit-proof artifact.

## Scientific provenance and scope

The finite-field interpolation approach and GF(16) 9-term basis
construction follow the mathematical ideas in
[Polytof](https://github.com/ZIB-IOL/polytof), MIT-licensed, exact
upstream commit `0dcac107d15adc34dc646242d222f21ae7d32699`.
The *distinct* public [James Barlow VQCC bilinear KMB evaluation
dataset](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation)
is declared Apache-2.0 and is sourced in
[its original manifest/provenance record](../../benchmarks/corpus/kaggle_bilinear/SOURCE.md).
Its **14 public cases are GF16/GF64, not GF24**, and are not used
as new GF24 holdout evidence. No source or dependency is imported
from a private project.

The implementation and circuit counts are new SymQ research experiments.
They do not establish an improved GF24 lower bound, a complete quantum
phase/HMR equivalence theorem, an independently verified SAT/UNSAT
certificate, a DQI score gain or external comparative performance.
Run `python -m pytest -q tests/test_gf24_tower.py` in a clean checkout
of the pinned PR head to reproduce the reported gate counts and tests.
