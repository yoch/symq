# Z8 phase-polynomial pilot — independent of qant

Research issue [#80](https://github.com/yoch/symq/issues/80). This prototype is **not**
installed as a production checker and does **not** change `symq.phase`.

For basis permutations and diagonal Clifford+T gates, the unitary is
`U|x> = omega^p(x) |F(x)>`, with `omega = exp(i*pi/4)`.
The maps `F` are exact GF(2) ANFs; `p` is a unique integer multilinear polynomial
over the Boolean cube with coefficients modulo 8. A canonical polynomial comparison
proves equality on all basis inputs, therefore on every superposition by linearity.

The pivotal identity is **not** ordinary Boolean ANF-to-Z8 conversion:

```
    lift(a XOR b) = lift(a) + lift(b) - 2*lift(a)*lift(b)  (mod 8).
```

Failure to include the cross term would accept incorrect phase gadgets after
CNOT layers. Test cases reproduce the error explicitly and validate independent
concrete state/phase output on all inputs for random widths up to 5.

Accepted gate grammar: X, CX, CCX, MCX, T, Tdg, S, Sdg, Z, CZ, CCZ.
Unsupported: arbitrary H, HMR, measure, reset, conditional gates, non-eighth-root rotations.

The checker distinguishes exact identity, equality up to global `omega^k`,
and actual output/relative-phase disagreement with concretely checked witnesses.
It provides coarse `Budget` guards, but is **not** a production-scale compiler
or proof certificate format. This path cannot verify arbitrary Clifford+T circuits
that contain H. An explicit optional MQT QCEC adapter is a separate P1 proposal.

Run: `PYTHONPATH=src python -m pytest tests/test_phase8_research.py -q`.

### Independent QCEC cross-check and resource discipline

The already-optional `[external]` CI job executes
`tests/test_phase8_external.py` against the currently installed MQT QCEC
on a **matched unitary-only fragment**. A QCEC `equivalent` or
`equivalent_up_to_global_phase` verdict must agree with the exact Z8 local
checker, and `not_equivalent` must agree with a local difference. MQT remains
an optional test dependency, not a dependency of SymQ or of any other project.

The public pilot `check_equivalence` charges both symbolic simulations to a
**single cooperative Budget**. A deterministic delayed-symbolic test verifies
that the second pass cannot restart the deadline.

### Nouvelle validation ciblée

Deux compilations réversibles distinctes du gadget diagonal
`T(x_0 XOR x_1)` sont prouvées équivalentes par la représentation Z8 et
par MQT QCEC. Un mutant comportant une phase T supplémentaire est rejeté
par les deux moteurs. **Neuf** paires unitaires appariées ont ainsi été
testées dans l'environnement externe : la [CI 40765866702](https://github.com/yoch/symq/actions/runs/40765866702)
a exécuté **205 tests externes réussis**, et ses sept jobs sont verts.

Ce pilote ne couvre toujours pas les Hadamard arbitraires, les mesures
ou les resets. Les garanties restent celles de la grammaire diagonale.

## Why the Z8 normal form is exact

For any Boolean input assignment $x \in \{0,1\}^n$, a diagonal
eighth-root phase acts as $\omega^{p(x)}$ with
$\omega=e^{i\pi/4}$ and $p(x) \in \mathbb{Z}/8\mathbb{Z}$.
Every map from the Boolean cube to $\mathbb{Z}/8\mathbb{Z}$ has a
**unique multilinear representation**

$$
p(x)=\sum_{S\subseteq\{0,\ldots,n-1\}} a_S\prod_{i\in S}x_i
\pmod 8.
$$

**Proof (Möbius inversion on the Boolean lattice).** Let $1_T$ denote
the bit vector with exactly the indices in $T$ set. Evaluating the
polynomial gives $p(1_T)=\sum_{S\subseteq T} a_S$. Therefore

$$
a_S=\sum_{T\subseteq S}(-1)^{|S|-|T|}p(1_T)\pmod 8.
$$

The subset-inclusion matrix is triangular with diagonal entries $1$,
so it is invertible **even though** $\mathbb{Z}/8\mathbb{Z}$ is not
a field. Distinct coefficient maps yield distinct functions on the
Boolean cube.

For $a,b\in\{0,1\}$, Boolean parity has the *integer* identity

$$
a\oplus b=a+b-2ab.
$$

The implementation applies this identity recursively when lifting each
GF(2) ANF monomial to Z8. It multiplies monomial masks with
$x_i^2=x_i$ and reduces every coefficient modulo 8. Consequently
the resulting polynomial agrees pointwise with the original Boolean
function on every basis assignment. The exact output permutation and
the canonical phase polynomial together determine the entire unitary
by linearity. Two circuits are equivalent up to global phase exactly
when their output polynomials agree and the difference of phase
polynomials has **only a constant term**.

This is a statement of mathematical semantics, not a formal proof
about every Python/C memory or resource path. Runtime confidence also
requires the independent integer-basis oracle. The tests enumerate
**all 256 Boolean ANFs of three variables** (including every nonlinear
support) and check all eight assignments for each, as well as nine
matched native MQT QCEC unitary comparisons.

**Resource and domain limitations:** `max_terms` also counts the
initial input monomials of empty programs; `max_nodes` is explicitly
rejected because no native ZDD manager exists here. An evaluation
outside the declared width is rejected. Canonicality does not guarantee
a polynomial-sized representation, so higher-width expansion remains
resource bounded. An arbitrary H, measure, reset or classical
feed-forward is **not** part of this theorem.
