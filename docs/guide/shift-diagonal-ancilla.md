# Boolean-first and shift-diagonal ancilla research

`symq.labs.shift_diagonal_ancilla` studies a specific cost boundary of the
[backward Pauli checker](backward-ancilla.md): a diagonal error predicate may be
small as a Boolean expression even when expanding a multi-controlled gate in
Pauli words is expensive. The module retains exact Boolean ANF while possible,
then switches to a representation that preserves the input coherences needed
by HMR and classical feedback. It is opt-in research, with no stable API or
automatic selection by `symq.verify`.

## The same restricted obligation

For the actual validated `HybridProgram` channel $\Phi$, target ancilla $a$ and
zero-ancilla embedding $V$, the computed effect is

$$
E = V^\dagger\Phi^*(|1\rangle\!\langle1|_a)V.
$$

Every declared ancilla starts in zero. Data may be any coherent state,
including a state entangled with an arbitrary reference. All outputs are
retained for the source semantics; there is no postselection, input-support
approximation or borrowed dirty ancilla. Classical slots are internal and
must be initialized before use. The accepted operations are X, CX, CCX, MCX,
SWAP, CSWAP, Z, CZ, CCZ, global sign, HMR, Z measurement, standalone reset,
value/sign gates with classical conditions, and classical store/invert/XOR.
Unsupported instructions and malformed primitive fields are rejected.

A `clean` result means the exact effect vanishes for every data state. Because
$E$ is positive semidefinite, this proves the target's terminal marginal is
pure zero and therefore separates it from the remaining quantum, classical
and reference systems. It does not establish data-channel identity, and does
not authorize removing a reset, deleting a wire or rewriting the program.
For example, discarding a phase correction after HMR can leave all ancillas
clean while changing the data channel. The public qualification preserves
that example explicitly.

## Representation and exact transition

The initial error predicate is the target output bit. As long as it stays a
Boolean diagonal operator, it is represented in canonical GF(2) ANF. Value
gates compose their Boolean functions directly, sign gates commute with it,
Z measurement substitutes its recorded value, and reset substitutes zero.
No whole-circuit inverse-pair cancellation is performed.

At HMR on qubit $q$ writing slot $b$, first substitute output $q=0$ and take
the two outcome cofactors $g_0,g_1$. If they are equal, the outcome is irrelevant
and the effect stays Boolean. Otherwise each cofactor is lifted exactly to a
multilinear rational polynomial, using $x\mathbin{\oplus}y=x+y-2xy$, and the
effect becomes

$$
\frac{g_0+g_1}{2} + X_q\frac{g_0-g_1}{2}.
$$

The coefficients no longer depend on $q$, so this formula fixes the operator
order unambiguously. A relevant HMR creates X coherence; using only its output
bit probability would lose that information.

General mode represents

$$
O=\sum_s X^s\operatorname{diag}(f_s),\qquad
O|u,b\rangle=\sum_s f_s(u,b)|u\oplus s,b\rangle.
$$

Here $s$ shifts quantum bits only; $f_s$ is a canonical rational multilinear
polynomial in quantum and classical Boolean bits. Multiplication reduces
$x_i^2=x_i$ exactly. Coefficients are `Fraction` values and no term is truncated.
The implementation remains in general mode after promotion, even if a later
step happens to become diagonal again.

### Controlled conjugation without a Pauli gate expansion

For a permutation $F$, the exact convention gives

$$
U^\dagger O U|u\rangle
=\sum_s f_s(F(u))|F^{-1}(F(u)\oplus s)\rangle.
$$

For MCX with target $t$ and control conjunction $C(u)$, $F$ is involutive.
Compose the coefficient with $u_t\mapsto u_t\oplus C(u)$, and replace the shift
by

$$
s' = s\oplus e_t\bigl(C(u)\oplus C(u\oplus s)\bigr).
$$

If no control is shifted, the shift is unchanged. Otherwise $C(u)$ and
$C(u\oplus s)$ are disjoint events, so their XOR is their ordinary sum. This
partitions the coefficient between at most two outgoing shifts; it does not
expand the full controlled unitary into Pauli words. The coefficient
composition is required even when the shift is unchanged.

For a sign gate $(-1)^{C(u)}$, multiply each coefficient by
$(-1)^{C(u)+C(u\oplus s)}$. A classical guard selects between the transformed
and original coefficient. SWAP and CSWAP have exact local lowerings to three
CX/CCX primitives; tests include non-symmetric basis operators so that a
transposed operator convention cannot pass merely because physical effects
are symmetric.

### Measurement, feedback and initial projection

| Operation | Exact backward action in general mode |
| --- | --- |
| Reset on $q$ | Drop terms whose shift flips $q$; set output $q=0$ in all other coefficients. |
| Z measurement $q\to b$ | Drop terms whose shift flips $q$; substitute $b=q$, keeping the qubit value. |
| HMR $q\to b$ | Drop terms whose shift flips $q$; set $q=0$, take outcome cofactors, and create the sum/difference pair of shifts $s$ and $s\oplus e_q$. |
| Classical update | Compose with the actual Boolean store/invert/XOR function, including self-updates and overwritten slots. |

The old value of a slot that a measurement or store overwrites disappears
through substitution. Self-conditioned invert and self-XOR are included;
`invert("b0", condition="b0")` and `oxor("b0", "b0")` both set the bit to zero.

Only after all pullbacks are complete does initial projection discard shifts
on declared ancillas and evaluate their variables at zero. Data shifts remain.
The final effect is also checked for real symmetry,
$f_s(u)=f_s(u\oplus s)$. That check and its conversions share the same budget.

## Verdicts, witnesses and the missing replay layer

```python
from fractions import Fraction

from symq.experimental.hybrid import HybridProgram
from symq.labs.backward_ancilla import AncillaLimits
from symq.labs.shift_diagonal_ancilla import check_shift_diagonal
from symq.resources import Budget

# The remaining controls compensate for the changed first control.
program = HybridProgram(3, 1)
program.mcx(0, 1, 2, 3).x(0).mcx(0, 1, 2, 3).ccx(1, 2, 3).x(0)
result = check_shift_diagonal(program, 3, budget=Budget(max_seconds=5, max_terms=4096),
                              limits=AncillaLimits(max_products=1000000))
assert result.status == "clean" and result.mode == "boolean"

# E = u1 (I-X0)/2. Its diagonal has no constant monomial.
feedback = HybridProgram(2, 1).hmr(0, "b0").cx(1, 2, condition="b0")
bad = check_shift_diagonal(feedback, 2)
assert bad.status == "not_clean" and bad.mode == "shift_polynomial"
assert bad.assignment & 2 and bad.probability == Fraction(1, 2)
```

| Status | Meaning |
| --- | --- |
| `clean` | The source-bound exact effect is zero. |
| `not_clean` | The returned basis assignment has the returned exact positive error probability. |
| `inconclusive` | A resource cap prevented completion; no source claim, witness or work counters are returned. |

For Boolean ANF, assigning precisely the bits of a minimum-degree monomial
makes that predicate one. In general mode, positivity gives a positive
normalized trace for every nonzero effect. The mean of diagonal polynomial
$\sum_m c_m\prod_{i\in m}u_i$ is

$$
\sum_m c_m/2^{|m|},
$$

not its constant coefficient. Successive conditional means find a basis
assignment with positive probability. Positivity also explains why the bounded
forward oracle can decide this one property by enumerating basis inputs;
that argument would not prove general channel equality. The tests separately
compare the entire error matrix on input coherences.

**There is no portable certificate or replay API for this prototype.** Its
source hash identifies the copied, validated input but is not a proof token.
The benchmark independently checks returned witnesses with forward density
semantics up to width six and records `unsupported` above that width. It does
not label those larger witnesses as replayed. The older Pauli checker's own
certificate replay is measured separately and must succeed when present.

## Budget boundary and adverse parity

The module reuses the strict source/settings helpers and `AncillaLimits` from
`backward_ancilla`, pinned to PR #145 HEAD
`0e8959592c48c2dc203ba286ef1efcc322bb6dd5`, source SHA-256
`687f799064e577a5518c9498a3cedb46374fda126810936543db92862b67e927`.
The private dependencies are `_settings`, `_freeze` and the `_Source` shape;
the observable algebra is separate. This coupling is intentionally explicit,
and qualification verifies the pinned bytes before any trials. Future edits
to those helpers require requalification and a conscious pin update.

The whole call shares a cooperative deadline, a term cap and a global product
cap. Source validation, Boolean substitution, promotion, coefficient products,
symmetry checking, witness extraction and final semantic-scratch cleanup are
included. Structural limits are inherited: width 256, 10000 source operations,
256 classical slots, gate arity 12, and 1000000 elementary products by default.
Here products mean Boolean/rational monomial products, whereas the Pauli
checker counts Pauli products. Equal numeric caps are not equal work units.
The default explicit-term cap is 4096; it applies to each temporary polynomial
and each complete shift collection. It is not a process memory bound or a
bound on the sum of simultaneously live temporaries. Node/byte caps are
refused. Cooperative checks do not guarantee a hard scheduling deadline.

The counterexample to a universal speed claim is sparse parity across a
relevant HMR. For the benchmark family, the final effect is

$$
E=\frac{I-X_0\prod_{i=1}^{k} Z_i}{2}.
$$

It is small in Pauli form, but its exact rational monomial expansion can grow
exponentially. The harness retains both successful slower conversions and a
term-capped `inconclusive` case where the Pauli checker succeeds. It performs
no fallback that would hide this refusal. Factorized coefficients, decision
diagrams or a separately validated representation selector remain future
research, not features of this prototype.

## Reproduce the explored development qualification

```sh
python -m pytest -q tests/test_shift_diagonal_ancilla.py tests/test_shift_diagonal_qualification.py
python -m benchmarks.shift_diagonal_ancilla --repetitions 3 --output evidence/shift-diagonal-ancilla.json
```

The dedicated workflow uploads raw JSON rather than committing measurements.
The 39 cases include six constructed families: changed controls with a missing
compensation mutant, compute/use/uncompute with a missing cleanup mutant,
Z-measurement correlations with an overwritten-slot mutant, coherent HMR
feedback with sign phases, conditional routing with a missing route, and the
parity/HMR boundary. The computed ancilla is actually used in compute/use
examples; the cohort is not just adjacent inverse gates.

Twelve further obligations use the existing public
[Qualtran fixtures](../../benchmarks/corpus/qualtran/README.md), including
inverse cleanup, HMR cleanup, missing phase that still leaves ancillas clean,
and missing cleanup. Complete fixture bytes are checked against pinned Git
blobs; upstream commit, source hashes and Apache-2.0 license are preserved.
They are already explored development inputs, not holdouts.

Each trial rotates method order and records all repetitions, source hashes,
machine/interpreter/dependencies, whole-call wall and CPU time, traced Python
peak, process cumulative RSS, caps, failures, verdicts and witness checks.
The shared construction/import of cases into `HybridProgram` is separately
timed and retained; both symbolic methods then receive the same actual input.
All internal representation conversions are inside the public-call times.
The density comparison uses the same numeric term/time caps and has an
explicit width-six limit. The three methods count different representations;
unsupported density rows are not successful timing comparisons. No failed
early repetition is replaced by a later successful repetition.

These are internal implementation comparisons with a bounded scalar oracle.
No external tool was benchmarked, and no superiority to the state of the art
or general performance advantage is claimed.

## Prior work and the research question

Observable propagation and ancilla reasoning already have substantial prior
work. [Hoare meets Heisenberg](https://quantum-journal.org/papers/q-2026-07-23-2172/)
uses Heisenberg semantics for program reasoning, including separability and
ancilla disposal. Rudolph et al.'s
[Pauli Propagation framework](https://arxiv.org/abs/2505.21606) gives a broad
account and an implementation of Pauli propagation. Fuller et al.'s
[operator backpropagation](https://www.nature.com/articles/s41534-026-01196-0)
uses classical observable evolution to shorten quantum circuits and discusses
term growth and controlled truncation.

Approximate truncation cannot establish this exact zero-effect obligation
without an error argument strong enough to prove exact zero. This module's
question is narrower: within SymQ's closed hybrid grammar, when does keeping
an exact Boolean diagonal form, then promoting only at the necessary HMR
boundary, avoid an expensive representation without losing coherent effects?
The qualification is designed to expose both sides of that boundary.
