# Contextual classical substitution (experimental)

This is an opt-in research API under symq.labs, not a stable production facade.
It proves the safety of a specific replacement of a **classical reversible**
X/CX/CCX/MCX gate interval, relative to a declared basis-input domain and a
cut-state predicate. No arbitrary quantum superposition, HMR, phase, observed
instrument, output projection or dirty-ancilla coherent-frame theorem follows.

Start from the existing [SAT relational composition](sat.md) and
[total-input transcript substitutions](experimental-composition.md).
The context-sensitive check here is *not* a substitute for quantum channel
composition in symq.labs.channel_composition.

## A complete runnable example

Run the [example script](../../examples/contextual_substitution.py) after
installing the SAT optional extra:

`python -m pip install -e ".[sat]"`

```python
from symq import Circuit
from symq.labs.contextual_substitution import (
    SubstitutionContract, check_substitution,
)

source = Circuit(3).cx(0, 2).cx(0, 2).cx(2, 0).cx(0, 1)
result = check_substitution(
    source, (2, 3), Circuit(3),
    contract=SubstitutionContract(
        initial_constants=((2, 0),),
        clean_at_cut=(2,),
    ),
)
assert result.equivalent
assert result.cost.weighted_delta == -1
```

The source and replacement use **the same global wire numbering**; the
replacement is inserted at [start, stop), in source gate indices. The code
never mutates either input. The returned digests pin complete frozen original
and candidate streams, and a digest of the input/cut contract and insertion
span. The caller must check those pins when actually applying the rewrite.
The original suffix is unchanged and its compatibility follows from proving
full-output block equality at the cut.

### Exact obligations

1. The input domain P(x) given by initial_constants is satisfiable.
2. The actual prefix A(x) proves the cut predicate C(A(x)) for every x in P.
3. The relational interface requires equality of both cut states, in addition
   to C(u), and implies the local block precondition.
4. The original block B and proposed B' agree on *every output* for all cut
   states satisfying C; a cut witness may be unreachable in the global circuit.
5. Both blocks independently restore all clean_at_cut and restored_at_cut wires
   to **their own cut input values**, for all cut states satisfying C.

An optional cut_assumption is a validated Boolean formula over `u.<wire>`
(for example Not(Var("u.0"))) and is established by SAT against the actual
prefix. It is not an unchecked assertion. The initial_constants restrict the
original classical input domain; the API does not pretend that a classical
input predicate justifies a coherent quantum subspace.

### Results and cost model

- `equivalent` (and `certified=True`): all obligations passed for the
  frozen circuits, basis domain and contract.
- `precondition_failed`: the input domain is empty or the prefix/interface
  cannot establish the cut invariant. A prefix witness is an original input.
- `not_proved`: a local block or restoration obligation failed. A
  suffix/restoration witness is a **cut state**, not necessarily a reachable
  global input; `different` therefore remains false.
- `inconclusive`: budget expired or an obligation was undecided.
- `unsupported`: no interruptible SAT solver is installed.

The result lists each checked obligation with its outcome and typed witness.
It can be serialized via `result.to_dict()` for inspection, but replay must
recompute from the pinned inputs: JSON is not a proof authority. The opt-in
`replay_substitution(receipt, source, span, replacement, contract=...)` accepts
a typed result and **reruns the entire check**. It rejects any changed circuit,
span, contract or declared cost model by exact SHA-256 and value comparisons.
It returns the **newly established outcome**, never trusts a saved `equivalent`
flag or assumes a deterministic SAT witness. It does not parse an untrusted
JSON dict into proof authority. The default
whole-call timeout is 30 seconds, starting **before input freezing,
contract inspection, hashing and cost accounting**; only a SAT-enforceable wall
budget is supported. A cooperative timeout does not impose hard process RSS limits.

The cost report includes per-gate counts, the global counts before/after and
an optional explicit `GateWeights` (integer weights for X/CX/CCX/MCX).
Default weights of 1 are **just gate counts**, not T-count, hardware depth,
surface-code resources or competition-specific costs. A negative delta has
meaning only under the selected declared weights, and permission to apply a
rewrite requires a positive equivalence proof independently of cost.

### Limits / next gate

This version supports complete Boolean outputs and borrowed-bit *classical*
restoration only. Do not use it to conclude that a dirty qubit retains all
off-diagonal entanglement correlations; that requires the local quantum
channel/instrument substitution theorem. The next milestone is a user-facing
wrapper for the existing bounded HMR/channel composition and phase-debt
engines, with source-pinned public Qualtran or kickmix examples.
