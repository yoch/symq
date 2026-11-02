# Affine dephasing and dyadic phase derivatives

`symq.labs.affine_phase` is an opt-in research checker for two explicitly
constructed channels. It extracts the dephasing signature from a real source
program and checks phase derivatives on a declared affine input support.
It is not a default backend or an authorization to rewrite a surrounding circuit.

## Exact contract

The inputs are:

- Two actual `DyadicPhaseProgram` objects, `left` and `right`, with the same
  data width. Their closed grammar contains reversible basis permutations and
  dyadic diagonal phases; no Hadamards or measurements.
- One actual `PhaseProgram` named `dephaser`. It has that data width, any
  declared zero-initialized ancillas within the width cap, and the strict
  sign/HMR grammar, including measured-outcome-controlled sign phases.
- A nonempty affine coherent input support, parametrized injectively as
  $x(z)=x_0+Bz$ over $\mathbb F_2$. The domain is the span of these computational
  basis states, so coherent superpositions and entangled external references
  are covered. This is an explicit input contract, not a claim that an
  unspecified preparation circuit establishes that support.

The checker proves that the actual dephaser restores every data wire to
`x(z)` and every ancilla to zero on this support. It extracts its measurement
signature in the parameter variables and requires that signature to be affine.
Nonlinear source signatures can become affine after the declared restriction;
this is checked by exact Boolean substitution, not inferred from samples.

The compared channels, with outcomes forgotten, are

$$
(U_L\otimes I_A)\circ D
\quad\text{and}\quad
(U_R\otimes I_A)\circ D.
$$

`U_L` and `U_R` act on the data wires only. Their canonical extension is the
identity on every final ancilla of `D`. **All quantum outputs are retained.**
Visible measurement records, partial traces, nonzero initial ancillas,
arbitrary non-affine supports, and substitution under coherent control are
outside this theorem.

## Why the kernel basis suffices

The validated sign/HMR grammar gives branch operators

$$
K_m|x\rangle=2^{-M/2}(-1)^{p(x)+m\cdot g(x)}|x,0_A\rangle.
$$

After forgetting outcomes, a matrix unit survives precisely when
$g(x)=g(y)$. The phase of the common dephaser cancels in the comparison.
The checker first verifies the actual output functions of `left` and `right`
are equal on the support. If their relative dyadic phase is $\delta(z)$,
channel equality then reduces to constancy of $\delta$ on the fibres of

$$
g(x_0+Bz)=c+H_z z.
$$

For a complete basis $v_1,\ldots,v_r$ of $\ker H_z$, the obligations are

$$
\delta(z\oplus v_i)-\delta(z)=0\pmod{2^k}
\quad\text{for every }z\text{ and every }i.
$$

Every difference within a fibre is a sum of these basis vectors. Invariance
under each generator therefore implies invariance under every such difference.
Conversely, fibre constancy implies each displayed equation. The implementation
recomputes the complete kernel by GF(2) elimination; a supplied incomplete basis
cannot establish a proof.

This is ordinary finite-dimensional linear-structure mathematics. The
contribution here is the source-bound SymQ obligation, its guarded checker,
and the avoidance of unnecessary modular expansion.

### Avoiding unnecessary expansion

The checker keeps the actual phase gates as grouped weighted Boolean
predicates, $\delta(z)=\sum_j c_j b_j(z)$.

1. If $H_z$ has full column rank, every fibre is a singleton. The checker
   verifies output equality and never constructs phase predicates or lifts.
   Source angles and gate fields are still validated.
2. Otherwise, for each kernel direction it translates each predicate in
   Boolean ANF. A predicate with $b_j(z\oplus v)=b_j(z)$ contributes zero
   and is discarded **before** modular lifting.
3. Remaining predicates are lifted with their coefficient already included.
   The identity $a\oplus b=a+b-2ab$ is used exactly modulo $2^k$;
   coefficients annihilated by the modulus disappear during construction.

The surviving derivative is represented in the square-free monomial basis.
That representation is unique as a function on the Boolean cube over
$\mathbb Z/2^k\mathbb Z$, so a zero coefficient dictionary proves the identity.
Dense Boolean translations and modular lifts can still expand exponentially.
The implementation uses the canonical elimination basis, without a
minimum-weight basis search.

### The domain is essential

On the support $D=\{00,11\}$, the valid direction is `11` in ambient coordinates.
Testing ambient single-bit directions only when both endpoints remain legal
would find no edges and could miss a phase difference between the two states.
The implementation works in the support parameters and tests their complete
kernel. This counterexample, affine offsets, and singleton supports are regressions.

## API and replay

```python
import json

from symq.labs.affine_phase import check_affine_phase, replay_affine_phase
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.phase import PhaseProgram

# D measures the parity x0 XOR x1 into an ancilla, then resets that ancilla.
dephaser = PhaseProgram(2, 1).cx(0, 2).cx(1, 2)
dephaser.hmr(2)

# Compute that same parity, add a T phase, and restore the data permutation.
left = DyadicPhaseProgram(2)
right = DyadicPhaseProgram(2).cx(1, 0).t(0).cx(1, 0)
result = check_affine_phase(left, right, dephaser)
assert result.equivalent
assert result.receipt is not None

document = json.loads(json.dumps(result.receipt.to_dict()))
assert replay_affine_phase(left, right, dephaser, document).equivalent
```

An explicitly correlated support changes the obligation:

```python
from symq.labs.affine_phase import AffineSupport

domain = AffineSupport(width=2, offset=0, columns=(0b11,))
result = check_affine_phase(
    DyadicPhaseProgram(2), DyadicPhaseProgram(2).z(0), PhaseProgram(2),
    support=domain,
)
assert result.status == "not_proved"
assert set(result.witness) == {0b00, 0b11}
```

Columns must have full column rank. An empty column tuple denotes the
singleton containing `offset`, and remains a nonempty coherent domain.

| Status | Meaning |
| --- | --- |
| `equivalent` | Source restoration, affine signature, output equality and every required derivative were checked exactly. |
| `not_proved` | A semantic prerequisite, phase/output obligation or receipt check failed. This API makes no general inequivalence claim. |
| `inconclusive` | A resource cap or deadline prevented completion; no receipt is exposed. |

Malformed source objects and unsupported API settings raise an explicit
exception. Boolean values and deceptive subclasses are refused in integer,
name and container fields before interpretation.
Exact `Fraction` angles are reconstructed from canonical plain-integer
numerators/denominators; forged internals and shared mutable angle state are
not trusted.

The JSON receipt binds all three frozen source programs and the complete
support parametrization. It records the extracted affine rows/constants,
the recomputed kernel, the normalized modulus, and a digest of the grouped
weighted phase predicates. For singleton fibres that digest explicitly
records that phase expansion was unnecessary. Equivalent source syntax or
an alternative parametrization still requires a new matching receipt.

The receipt is portable data, not a standalone formal proof or trusted token.
`replay_affine_phase` recomputes the obligation from current source objects
and compares the complete canonical receipt. Missing, extra, edited and
non-JSON fields cannot establish equivalence. In particular, removing a
kernel direction from the receipt is rejected.

## Resources

The default whole-call budget is 100,000 terms and 10 seconds. Explicit
`Budget` values may replace these defaults. Time checking is cooperative,
includes source validation and concrete witness replay, and has a final
check after symbolic scratch cleanup. It is not a process-kill guarantee.
Use process isolation for a hard wall-clock or process-memory requirement.

`max_terms` bounds accounted explicit polynomial/state collections and
intermediate translations/lifts; it is not a bound on Python RSS or all
simultaneously live objects. Node and byte budgets are unsupported and
explicitly refused. `DerivativeLimits` additionally caps total circuit
width (at most 256), gates per source program, measurement events, and
receipt items. Phase denominators use `1 <= k <= 64`.
Integer angles and fraction components have a 4,096-bit serialization cap.

## Reproduction and interpretation

```bash
python -m pytest -q tests/test_affine_phase.py tests/test_affine_phase_qualification.py
python -m benchmarks.affine_phase --repetitions 3 --output evidence/affine-phase.json
```

The qualification retains every randomized-order repetition, complete-call
wall/CPU time including source construction, construction time separately,
Python allocation peaks, budgets, failures, source hashes and environment.
Timing is instrumented by `tracemalloc`; its overhead is not subtracted.
Both checker modules are imported before timed trials. Construction and
sign-program conversion remain inside the measured interval.
Receipt replay is a separate correctness check, outside the timed proof call.
Small cases have an exhaustive concrete coherence-pair oracle. Tests also
use an independent exact Kraus/cyclotomic oracle on every matrix unit.

Two sign-only cases compare the existing two-copy channel checker with its
Python ZDD and native ZDD backends. Native unavailability is recorded as such,
without contributing a successful comparison. The large dyadic families
also time full modular phase preparation under the same term cap; that
preparation stage is explicitly **not** a complete competing channel checker.

The families are constructed development examples: full dephasing,
measured parity, an adverse unmeasured parity that reaches its term cap,
restricted support, missing phase invariance and failed prerequisites.
They are not an untouched holdout, a public compiler corpus, or evidence of
general superiority over native checking. In particular, a full-rank
signature removes all phase obligations by the theorem, not by a faster
implementation of an otherwise necessary phase expansion.

The dedicated workflow saves raw evidence as an Actions artifact. Results
are not committed to the repository.
