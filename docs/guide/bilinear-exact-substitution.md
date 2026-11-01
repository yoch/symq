# Exact bilinear substitution: full unitary equality without SAT

**Experimental scope:** a restricted, phase-free triangular network of CX and
CCX gates. This checker is NOT a general QASM, HMR, phase or measurement
equivalence engine. It is independent of the GF24 tensor *factor generator*
and reinterprets the actual original and replacement gate streams.

## Accepted interface and theorem

Provide an injective mapping of three n-bit registers (A, B, Z) into
existing global wires; a real source gate span; and an explicit
irreducible degree-n binary modulus. Inside that span the checker
accepts only CX **within** A, B or Z, and CCX with one control from A,
one from B and target in Z. Unsupported, cross-register, nonlocal and
nonlinear operations of other types fail closed. The surrounding
prefix/suffix may be any unchanged supported reversible Circuit.

Every A/B bit carries a symbolic linear mask of the original input.
Every Z bit carries its original dirty-Z linear mask and an exact
quadratic bitset over A_i B_j. For each CX, those masks are XORed;
for each CCX, the two controls' current linear masks contribute their
outer product to the target's quadratic bitset. Thus the complete
stream represents exactly

```text
A_out = L_A A
B_out = L_B B
Z_out = L_Z Z XOR T(A,B)
```

Both blocks must restore L_A=L_B=L_Z=I, and their output tensor must
equal the **independently computed** 24×24 (or smaller) multiplication
table, T[i,j] = x^(i+j) mod P(x), on *every* coefficient pair. A
tensor certificate supplied by the optimizer is **not trusted**.

These phase-free CX/CCX circuits implement ordinary basis
permutations with unit amplitude and no relative phase. Exact equality
on every basis vector therefore implies equality of their unitaries,
including arbitrary dirty accumulator states, coherent superpositions
and entanglement with wires outside the block. The entire enclosing
Circuit preserves its unitary under substitution because the prefix
and suffix are unchanged. No clean-ancilla or cut-reachability
assumption is needed. This stronger result comes from the narrowly
enforced grammar: a general reversible or hybrid circuit may be
equivalent yet rejected.

## Source-pinned proof, replay and automatic selection

```python
from symq import Budget
from symq.generators import gf2n
from symq.labs.gf24_tower import GF24_MODULUS
from symq.labs.gf24_schedule import pinned_gf24_emitted
from symq.labs.bilinear_exact_substitution import (
    BilinearWeights, check_bilinear_substitution, apply_bilinear_substitution,
    optimize_gf24_substitution,
)

old = gf2n.emit(24, gf2n.karatsuba(24), strategy="pivot-scheduled").circuit
new = pinned_gf24_emitted().circuit

proof = check_bilinear_substitution(
    old, (0, len(old.gates)), new,
    n=24, modulus=GF24_MODULUS, wires=tuple(range(72)),
    weights=BilinearWeights(ccx=32, cx=1),
    budget=Budget(max_seconds=25),
)
assert proof.weighted_delta == -1238
applied = apply_bilinear_substitution(
    proof, old, (0, len(old.gates)), new, budget=Budget(max_seconds=25)
)
assert applied.proof == proof
```

The proof pins SHA-256 digests of the complete original and candidate
streams, the original/replacement blocks, explicit span, mapping, field
polynomial, tensor and caller-declared integer gate weights. Application
**freezes mutable inputs before replay** and redoes every proof obligation
on those exact snapshots. Forged success flags, stale receipts, invalid
gates and deadlines fail closed.

`optimize_gf24_substitution(source, span, wires=...,
weights=BilinearWeights(...))` automatically picks among the three
previously published GF24 methods, but **independently re-proves the
actual mapped candidate** before returning an immutable program. A
negative weighted delta is mandatory by default; optional
`require_saving=False` changes only that policy, not proof soundness.
CCX/CX weights are user-defined integer proxies, **not** T-count,
physical hardware costs or official Kaggle scores.

## Bounded qualification

The verifier supports n=2..24 with verified irreducible polynomials,
a default limit of 10,000 gates per local block and 4,096 global wires,
and a shared absolute time deadline through proof/replay. Unsupported
node/term/byte limits are refused. The coefficient-state method scales
with the number of gates and n² tensor coefficients, not 2^(3n)
enumerated input assignments.

[Adversarial tests](../../tests/test_bilinear_exact_substitution.py)
cover 72-wire arithmetic in a nontrivial 78-wire context; an
exhaustive GF16 16-wire contextual case; source/candidate mutants;
wrong field bases; unrestored input/output frames; nonlocal gates;
stale and forged receipts; timeouts; and strict cost policies.
The [qualification runner](../../benchmarks/bilinear_exact_proof.py)
produces an inspectable, SHA-256-pinned JSON proof receipt.
These checks qualify this exact theorem and tested code, not a
third-party proof-certificate system or global quantum optimization.

The underlying rank-nine/rank-99 interpolation construction is based
on methods documented in [Polytof](https://github.com/ZIB-IOL/polytof)
(MIT; commit `0dcac107d15adc34dc646242d222f21ae7d32699`).
The distinct [James Barlow KMB dataset](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation)
is declared Apache-2.0, with pinned original hashes in
[SOURCE.md](../../benchmarks/corpus/kaggle_bilinear/SOURCE.md). It is
not a blind GF24 holdout. No private Qant dataset or other project
dependency is used or claimed to have been qualified.
