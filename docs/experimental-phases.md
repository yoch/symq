# Experimental dyadic phases, exact channels and optional QCEC

These installed modules are experimental APIs. They do not import `research/`.
The original `research/phase8/phase8.py` is an explicit compatibility shim, so
`Program8`, `Gate8`, `Symbolic8`, `Verdict8`, `symbolic`, `lift_anf`,
`eval_phase` and `check_equivalence` share one maintained implementation.

## D1: sparse multilinear phases modulo a power of two

```python
from fractions import Fraction
from symq.experimental.phase import PhaseProgram, symbolic, check_equivalence

p = PhaseProgram(2, k=4).cx(0, 1).phase(1, Fraction(1, 16))
assert symbolic(p).phase == {1: 1, 2: 1, 3: 14}
assert all(symbolic(p).run(x) == p.run(x) for x in range(4))
```

A program acts as `U|x> = exp(2*pi*i*p(x)/2**k)|F(x)>`. Outputs `F` use
Boolean ANFs; `p` is the unique integer-valued multilinear polynomial on the
Boolean cube with coefficients modulo `2**k`. Angles are **exact rational
turns**, and their denominator must divide `2**k`. Floats and non-dyadic
angles are refused. Named T/Tdg, S/Sdg, Z/CZ/CCZ phases retain their ordinary
angles, so T requires `k >= 3`. The reversible grammar is X/CX/CCX/MCX.
H, measurements and reset are outside this polynomial grammar.

The parity conversion uses `a XOR b = a + b - 2ab`, including mixed terms
and monomial collisions. Coefficientwise casting of a Boolean ANF is unsound:
T after CX is a concrete counterexample. Every Boolean product, integer
product and parity-conversion intermediate is checked against the term budget.

`check_equivalence` compares different moduli by exact embedding into their
common power of two. It distinguishes `equal`, `global_phase` and `different`.
A global-phase exponent means **left minus right** modulo `2**verdict.k`.
A difference includes a basis-input witness independently replayed by the
integer interpreter. For a relative-phase difference, compare that witness
with input zero; one basis state alone cannot disprove global-phase equivalence.

## D2: bounded exact cyclotomic reference

```python
from symq.experimental.cyclotomic import (
    CyclotomicProgram, channel_semantics, check_channel_equivalence,
)

p = CyclotomicProgram(1).h(0).h(0)
assert check_channel_equivalence(p, CyclotomicProgram(1)).equivalent
measured = CyclotomicProgram(1)
outcome = measured.hmr(0)
measured.phase_if(outcome, 0, Fraction(1, 8))
channel = channel_semantics(measured)
```

`CyclotomicProgram` accepts the D1 gates, H, X-basis measurement followed by
reset to zero (`hmr`) and an exact conditional phase controlled by an earlier
outcome (`phase_if`). All wires are arbitrary inputs and retained outputs;
there are no hidden initialized ancillas. Every HMR outcome is discarded from
the channel after its feed-forward uses. General reset, arbitrary measurement,
postselection and dynamic QCEC are unsupported.

The independent reference sums Kraus amplitudes. For an HMR input bit `b`,
outcome `m` contributes `(-1)**(b*m)/sqrt(2)` and resets that wire to zero.
For input matrix unit `|x><x'|`, the stored coefficient is

```
E(|x><x'|)[y,y'] = sum_m K_m[y,x] conjugate(K_m[y',x']).
```

Both sides use the **same** measurement transcript inside each program. The
transcripts of two different programs are summed separately; their counts need
not coincide. Global phases cancel automatically in this channel relation.
`coefficient(x, xp, y, yp)` returns an exact `Cyclotomic`, represented in the
canonical basis of `Q[z]/(z**(2**(r-1))+1)`, where `r=max(3,k)` and
`z=exp(2*pi*i/2**r)`. Rational coefficients and reduction are exact.
`approximate()` is a display/test helper and is never used for proofs.

This is a finite reference, without a scalability claim. Default
`ReferenceLimits` bound width to 4, H gates to 12, HMR events to 8, root
exponent to 8 and retained map entries to 65,536. Explicitly changing those
limits does not change the semantics. Exceeding a reference limit or `Budget`
raises `ResourceLimitExceeded`, never an approximate verdict.

Only the following event elimination has been proved and implemented. If

```
phi(x,m) = a0(x) + sum_j aj(x) mj  (mod 2**k),
```

then

```
sum_m zeta**phi(x,m) = zeta**a0(x) product_j (1 + zeta**aj(x)).
```

`affine_event_factor(phase, event_variables, assignment, k=k)` computes the
normalized average by default; `normalize=False` returns the sum. It refuses
any nonzero monomial containing two event variables, even if one particular
data input would annihilate that monomial. This helper eliminates an exponent
only; it does not assume output permutations are independent of outcomes.

A generalization of the Boolean-kernel criterion is explicitly rejected.
Already with one event and `phi=m` at `k=3`, the average is `(1+zeta)/2`,
which is neither zero nor one. With `phi=m0*m1`, the affine product formula
is inapplicable. Those are executable negative cases, not assumptions about a
larger unproved phase fragment. General channels therefore use the bounded
exact reference and never that Boolean shortcut.

## D4: optional unitary QCEC adapter

```python
from symq.experimental.qcec import check_unitary_equivalence

result = check_unitary_equivalence(
    CyclotomicProgram(1).h(0).h(0), CyclotomicProgram(1),
    up_to_global=False,
)
```

The optional adapter lazily imports the maintained `symq.external.qcec` adapter
and reuses its complete alternating decision-diagram checker configuration.
Simulation and ZX heuristic checkers remain disabled. H and named Clifford+T
phases are accepted, with CCZ exactly lowered to H/MCX/H. HMR and conditional
phases are refused before loading MQT. Arbitrary rational `phase` instructions
are also refused: the external rotation interface uses floating parameters,
so the adapter makes no exact arbitrary-dyadic-rotation claim.

`up_to_global` is a mandatory Boolean keyword. A QCEC
`equivalent_up_to_global_phase` result is accepted only when this flag is true;
`equivalent` is accepted under both conventions. `not_equivalent` maps to
false; every inconclusive/probabilistic external verdict maps to `None`.
Missing MQT raises `ModuleNotFoundError` on use; importing the module and using
the two exact internal engines does not require it.

All three entry points participate in `VerificationSession`: conversions,
both programs, coefficient comparison, witness replay and final result return
share the outer deadline. QCEC receives the remaining duration. `max_nodes`
is explicitly refused by these engines because they do not allocate a ZDD.

## Reproduction and evidence

Run the focused checks with

```
python -m pytest tests/test_experimental_phases.py tests/test_phase8_research.py -q
```

The tests exhaust all 256 three-variable Boolean functions at five moduli,
compare randomized reversible/dyadic programs with a direct integer oracle,
exhaust all one-wire words of length at most three over X/H/T/Tdg/HMR against
an independently implemented dense Kraus oracle, and compare randomized
two-wire circuits including feed-forward. They include exact identities,
relative/global-phase mutants, complete affine-event sums, nonlinear refusals,
resource exhaustion, shared deadlines and absent optional dependencies.
Optional real QCEC comparisons are skipped if MQT is absent; mocked adapter
checks separately test verdict classification and conversion. No external
performance advantage is claimed.
