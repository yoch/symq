# Clean ancillas by backward propagation

`symq.labs.backward_ancilla` is an opt-in research module. It proves that one
declared ancilla finishes in the pure state $|0\rangle$ by propagating its error
observable backward through an actual, validated `HybridProgram`.

## Exact claim and scope

The input has arbitrary coherent data, possibly entangled with an external
reference, and every declared ancilla starts in $|0\rangle$. The target must be
one of those ancilla wires. Classical slots are internal, initially
uninitialized, and must be written before they are read. There is no input
postselection or user-supplied support approximation.

Supported operations are the existing closed `HybridProgram` grammar:

- X, CX, CCX, MCX, SWAP, CSWAP and real sign phases Z, CZ, CCZ, `neg`;
- X-basis measurement with reset (`hmr`), Z-basis measurement (`measure_z`),
  and true standalone `reset`;
- quantum value/sign gates conditioned on an initialized classical bit or
  its negation; classical `store`, `invert` and `oxor`, including slot reuse.

H gates, general complex rotations, arbitrary input supports and borrowed dirty
ancillas are outside this theorem. A target with arbitrary initial content and
external classical inputs are handled by an exact reduction, below. The checker
rejects unsupported source instructions; it does not approximate them.

## A target that starts dirty, slots set before the program

A program cut out of a larger computation often reads classical slots measured earlier
and must clear a wire that held arbitrary content. A `HybridProgram` cannot express either
directly.
`symq.labs.ancilla_inputs.with_inputs` builds the exact program that does: a hidden data
wire is swapped into the target (`initial_target="arbitrary"`), and each slot of
`classical_inputs` is first measured from its own hidden data wire. The theorem above,
which covers every data state, then covers every initial target content and every input
value. The engines are unchanged; `layout.explain` reads a witness back in the caller's
terms (data input, initial target value, input values).

```python
from symq.experimental.hybrid import HOp
from symq.labs.ancilla_inputs import with_inputs
from symq.labs.backward_ancilla import check_clean_ancilla

ops = [HOp("cx", (0, 2), condition="b3"), HOp("hmr", (2,), slot="b1"),
       HOp("cx", (1, 2), condition="b1"), HOp("cx", (1, 2), condition="b1")]
program, layout = with_inputs(2, 1, ops, 2, initial_target="arbitrary",
                              classical_inputs=("b3",))
result = check_clean_ancilla(program, layout.reduced_target)   # clean
```

Only the target may start dirty; every other ancilla still starts at $|0\rangle$
(a borrowed dirty ancilla that must be *restored* is a different, unsupported theorem).
Input values may be correlated with the data or with the target's content. The obligation
ranges over every input value, so a `not_clean` witness may use a combination the
enclosing computation never produces. A listed slot must be read before the program
writes it.

A certificate binds the program `with_inputs` returned, hidden wires included; it does
not record the layout. To rely on the claim about your own program, rebuild it with
`with_inputs` and replay.

## What cleanliness does not establish

**Cleanliness does not establish preservation of the data channel.** For
example, entangling an ancilla with data and then resetting it leaves that
ancilla clean while dephasing the data. Removing a phase correction after HMR
can also preserve every terminal zero ancilla while breaking the intended
channel. The tests check both distinctions by exact channel comparison; the
public qualification retains both cases, where it checks only the ancilla status.

The result alone does not authorize deleting an operation, a wire, a reset,
or substituting a block. Those changes require their own contextual proof.

## Why one observable suffices

Let $\Phi$ be the source program's CPTP map and let $V$ embed arbitrary data
into the declared zero-ancilla input space. For target ancilla $a$, define

$$
Q_a=\frac{I-Z_a}{2},\qquad E=V^\dagger\Phi^*(Q_a)V.
$$

The checker computes $E$ exactly. Complete positivity gives $E\succeq0$.
Thus $E=0$ means zero probability of observing ancilla value one for every
data density matrix. The marginal is the pure state $|0\rangle$, which also
implies separation of this ancilla from all remaining systems, including an
arbitrary reference and any retained classical record.

If $E\ne0$, its trace is positive. At least one computational-basis input
therefore has a positive diagonal entry. The checker finds such an input by
successive conditional averages of the diagonal effect, without enumerating
all $2^d$ data inputs. Its witness contains that input and the exact positive
error probability as a `Fraction`.

This use of positivity is particular to the clean-ancilla property. Checking
only computational-basis outputs does not establish general channel equality.

## Representation and backward rules

An observable is a sparse sum of real words $X^xZ^z$, multiplied by parity
characters $(-1)^{c\cdot b}$ on classical slots. Coefficients are exact rational
numbers. The convention is explicit:

$$
X^x Z^z|u\rangle=(-1)^{z\cdot u}|u\oplus x\rangle,
\qquad
(X^x Z^z)(X^{x'}Z^{z'})=(-1)^{z\cdot x'}X^{x\oplus x'}Z^{z\oplus z'}.
$$

There is no omitted imaginary phase: a single $XZ$ is real anti-Hermitian;
the final effect is checked to be real symmetric. Controlled gates are
expanded using exact control projectors and conjugated as $U^\dagger O U$.
An operation with disjoint quantum support leaves an observable unchanged,
after the entire source has still been validated and bound to its hash.

For HMR, output X/Y components on the reset qubit vanish, output Z evaluates
to one, and the new measurement parity character pulls back to **X** on the
measured input qubit. For Z measurement the character pulls back to **Z**.
Standalone reset also removes X/Y components and evaluates output Z at zero.
An overwritten slot has no remaining dependence on its previous value.

Classical parity updates compose by XOR of character masks. This includes
noninvertible self-updates such as `oxor("b0", "b0")` and
`invert("b0", condition="b0")`, both of which set that bit to zero.

Only after every backward step does the checker project the **initial**
ancillas onto zero. X components on initial ancillas vanish; Z components
evaluate to one. X components on data are retained: they encode real input
coherence, for example $E=(I-X)/2$ after HMR-controlled value feedback.

## API and replay

```python
import json

from symq.experimental.hybrid import HybridProgram
from symq.labs.backward_ancilla import check_clean_ancilla, replay_clean_ancilla
from symq.resources import Budget

# Correlated cleanup: the measured data bit equals the copied ancilla value.
program = HybridProgram(1, 1)
program.cx(0, 1).measure_z(0, "b0").x(1, condition="b0")
result = check_clean_ancilla(program, 1, budget=Budget(max_terms=4096, max_seconds=5))
assert result.clean
document = json.loads(json.dumps(result.certificate.to_dict()))
assert replay_clean_ancilla(program, document).clean

broken = HybridProgram(1, 1).cx(0, 1)
bad = check_clean_ancilla(broken, 1)
assert bad.status == "not_clean"
assert bad.witness.assignment == 1
assert bad.witness.probability == 1
```

The example's final zero follows from a correlation between data, ancilla and
classical record. The current independent 0/1/unknown abstraction cannot prove
that correlation. A regression compares both analyses explicitly.

| Status | Meaning |
| --- | --- |
| `clean` | The complete source-bound error effect vanishes; a receipt is returned. |
| `not_clean` | A specific basis data input has a strictly positive ancilla-error probability. |
| `not_proved` | Replay rejected a malformed or mismatched receipt. |
| `inconclusive` | A resource bound prevented completion; no receipt or witness is returned. The result says which limit was reached (see below). |

Malformed source or settings raise an explicit exception. Portable receipts
have a closed versioned schema, source SHA-256, frame dimensions, target and
operation count. They are data, not trusted proof tokens. Replay reconstructs
the full error effect from the actual intended source and checks it afresh.
Changing a receipt's hash to match a bad program cannot make that program clean.
The source hash binds the program, not the target: without `target=`, replay
re-proves whichever ancilla the receipt names. Pass `target=` to
`replay_clean_ancilla` when you rely on a particular ancilla; a receipt naming
another one is then `not_proved`.

## Budgets and adverse cases

`Budget` supports cooperative whole-call time limits and explicit term limits.
The default budget limits each explicit observable or gate expansion to 4096
terms. `max_nodes` and `max_bytes` are refused: this module has no ZDD manager
or byte-accounted allocator. Term limits do not claim to bound process RSS or
the sum of all temporarily retained dictionaries.

`AncillaLimits` additionally caps width (default 256), source operations
(10000), distinct classical slots (256), gate arity (12) and total elementary
Pauli products (1000000). The public final deadline check occurs after the
semantic scratch has been released, including on replay.

An `inconclusive` result reports the work done before it stopped (`peak_terms`,
`pauli_products`, `checked_operations`; `None` only when the call stopped before
any work, never reported as zero work) and the limit it reached: `resource`
(`terms`, `seconds`, `pauli_products`, `width`, ...), `limit`, `observed`, a
`hint` naming the parameter that controls it, and `limits`, every limit the call
ran with. A larger limit may let the call conclude, or may not: `observed` is
where it stopped, not what a proof needs. The same fields are documented in
`symq.labs.resource_report` and returned by the shift-diagonal checker and the
table verifiers.

Controlled non-Clifford gates can expand a small observable into exponentially
many Pauli terms. Even a reversible compute/uncompute sequence can be much
slower here than forward simulation on a small basis set. Qualification keeps
controlled-uncompute cases with increasing arity and a deliberate work-cap
refusal. This module is a targeted alternative, not a replacement for the
Boolean, SAT, or constant-propagation engines.

## Reproduce the development qualification

```sh
python -m pytest -q tests/test_backward_ancilla.py tests/test_backward_ancilla_qualification.py
python -m benchmarks.backward_ancilla --repetitions 3 --output evidence/backward-ancilla.json
```

The dedicated CI workflow uploads raw JSON. It records every repetition,
complete public-call wall/CPU cost, Python allocation peaks, process cumulative
RSS, source/binary identity, machine, limits, failures, fresh receipt replay and
independent witness checks. A `clean` without a receipt, a `not_clean` without
a witness, or a witness on a program wider than the six-qubit dense oracle
fails the qualification. A failed early repetition cannot be hidden by a
later success. Failed calls retain their measured cost; the CLI writes the
report before returning failure.

The 23-case development cohort includes 12 obligations derived from the public
[Qualtran fixtures](../../benchmarks/corpus/qualtran/README.md): inverse cleanup,
HMR cleanup, missing phase correction that still leaves clean ancillas, and
missing cleanup. Their full file Git blobs are pinned and checked before import,
in addition to the existing upstream commit, source hashes and Apache-2.0 license.
No private programs or new third-party assets are included.

The forward baseline checks the same one-ancilla property on basis inputs,
using positivity, with the existing bounded exact density oracle. It is limited
to width six; wider cases are explicitly unsupported and excluded from any
successful-pair timing comparison. Conversion into `HybridProgram` is outside
both calls; validation and backward source binding are inside the public call.
The separate tests compare full error-effect matrices on all input coherences.

Terminal HMR/reset examples are already easy for a constant-only abstraction.
Their timings against a density oracle do not demonstrate an advantage over
that abstraction. All cases are development examples, not an untouched holdout
or a comparison to the fastest available external verifier.

The observable/Heisenberg approach has prior art, including
[Hoare meets Heisenberg](https://quantum-journal.org/papers/q-2026-07-23-2172/).
This module's contribution is a bounded, source-bound obligation for SymQ's
declared hybrid grammar, with explicit failure semantics and independent tests.
