# GF(2^24): pinned full-input substitution and a better CNOT order

**Research only; not a stable public API.** This work composes existing
SymQ engines, rather than trusting an arithmetic factor certificate as
permission to edit an arbitrary circuit. It is stacked on
[PR #129](https://github.com/yoch/symq/pull/129), whose own base is
[PR #126](https://github.com/yoch/symq/pull/126). The separate
[PR #128](https://github.com/yoch/symq/pull/128) explores **restricted
classical cut predicates using SAT**; the 72-wire construction here uses
a different, stronger *all-input* proof obligation and does not silently
reuse that SAT result.

## The key theorem: equality on all 72 dirty inputs

A GF(2^24) multiplier is a reversible permutation
`(a,b,z) -> (a,b,z XOR a*b)`. The A/B inputs and every original Z bit
may initially be arbitrary. No clean scratch, measured bits, local phase
debts or classical input predicates are assumed. When **both actual**
local gate streams are exactly the same permutation on all basis inputs,
they may replace one another in **any identical reversible
X/CX/CCX/MCX prefix and suffix**; this is ordinary compositional
equality. Because accepted operations are genuine phase-free
permutation unitaries, full all-input equality also implies equality
on coherent superpositions and entangled references. It does **not**
validate other quantum operations (CZ/HMR/rotations/measurements),
relative-phase Toffolis, reset/feed-forward or an instrument theorem.

`apply_gf24_rewrite` uses the existing
`symq.labs.classical_transcript.verify_transcript` and
`symq.check_equivalence(...,backend="packed")` engines. `packed`
represents exact ANFs of degree at most 2, with no SAT approximation.
Both actual X/CX/CCX streams must remain within this admitted degree;
unsupported higher-degree intermediate products raise
`ResourceLimitExceeded("degree")`, and **no replacement is applied**.
The theorem includes every output wire, not only the 24 result bits.
A complete frozen source/replacement stream and local insertion span
are SHA-256 pinned, the entire prefix/suffix is checked against the
declared transcript, and both local programs must restore every
explicitly listed `preserved` wire.

The wrapper independently validates the caller's 72-wire injective
mapping, the declared integer CCX/CX weights, explicit method and
bounds, and source gate span. Source and candidate are frozen before
proof. Two independent fresh calls to the exact transcript checker
share **one absolute deadline**, and the result contains the frozen
candidate and two matching source/candidate fingerprints. No
previously saved positive flag or arbitrary JSON is accepted as
authority; `replay_gf24_rewrite` recomputes from the exact supplied
source and checks pins/weights. An invalid map, unsupported gate,
wrong source, detected mutation, timeout or missing strict weighted
saving (default policy) causes a fail-closed refusal.

## Code sample

```python
from symq import Circuit, Budget
from symq.generators.gf2n import emit, karatsuba
from symq.labs.gf24_verified_rewrite import (
    GF24GateWeights, apply_gf24_rewrite, replay_gf24_rewrite,
)

source = emit(24, karatsuba(24), strategy="pivot-scheduled").circuit
applied = apply_gf24_rewrite(
    source, (0, len(source.gates)), wires=tuple(range(72)),
    weights=GF24GateWeights(ccx=32, cx=1),
    budget=Budget(max_seconds=40, max_terms=4000),
)
assert applied.proof.equivalent and applied.proof.backend == "packed"
assert (applied.cost.after_ccx, applied.cost.after_cx) == (99, 2646)
assert replay_gf24_rewrite(applied, source).candidate_sha256 == applied.candidate_sha256
```

A separate test surrounds the multiplication with real prefix/suffix
gates on **76 wires**, including nontrivial interactions with unmapped
context wires. It confirms exact complete stream fingerprints,
restoration of borrowed wires, and parity against independent
concrete execution on sampled basis assignments. Mutation, forged
cost receipt, changed source, bad map, refused cost, unadmitted
degree-3 circuit, and resource guards are tested as negative controls.
Smaller GF16 circuits are cross-checked with the **different exact
ZDD** engine. Tests do **not** claim a portable independently
checkable UNSAT proof or exhaustive 2^76 concrete replay.

## Additional GF24 CNOT scheduling gain

The original [GF24 research PR](https://github.com/yoch/symq/pull/129)
identified GF16-tower root `0xB781C5`, outer beta `0x10`, rank 99,
and **99 CCX / 2750 CX** with the default greedy pivot scheduler.
An extra **bounded deterministic 504-start 2-opt search** now
optimizes the ordering of those **same 99 factors**. It estimates
CNOT transitions with a symmetric parity-frame surrogate and
then reruns the exact per-register dynamic pivot program for
every retained schedule. The best **among these 504 starts** is
pinned as `PINNED_ORDER`; it emits **99 CCX / 2646 CX** on the
same 72 dirty qubits. The factor SHA-256 remains:

`549b1c30d2bee1a35fca79d96defd4ad99870a4fb59f0d9b9960fe125472c88a`

This is **104 fewer CX (3.78%)** than the prior 2750-CX
realization, without changing the tensor or Toffoli count; it
is neither a globally optimal permutation nor a proof of
the minimum attainable CX network. The factor-order search is
reproduced by
`python -m benchmarks.gf24_order_qualification --output /tmp/order.json`,
with full raw order, environment, 504-start protocol and a SHA-256
sidecar. Original `choose_gf24` behavior remains the default;
`include_pinned_order=True` opts into the fourth candidate.

| Whole multiplier | CCX | CX | Weighted proxy CCX=32, CX=1 |
| --- | ---: | ---: | ---: |
| Karatsuba, scheduled | 162 | 1856 | 7040 |
| GF16 tower, greedy schedule | 99 | 2750 | 5918 |
| GF16 tower, pinned 2-opt schedule | **99** | **2646** | **5814** |

The new choice is **17.4% below Karatsuba** under these
*illustrative integer weights*, not a measured T-count,
fault-tolerant resource estimate, physical runtime, surface-code
volume or official Kaggle VQCC score.

## Provenance and boundaries

Original GF16-tower mathematical idea: [Polytof](https://github.com/ZIB-IOL/polytof),
MIT, upstream commit
`0dcac107d15adc34dc646242d222f21ae7d32699`.
The separate [James Barlow VQCC bilinear agent-evaluation dataset](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation)
is Apache-2.0 as declared in the uploaded README;
its exact original KMB/manifests and hashes appear in
[the source provenance](../../benchmarks/corpus/kaggle_bilinear/SOURCE.md).
Those **14 GF16/GF64 development cases are not GF24 holdouts**.
The new GF24 schedule search and all-in-context proof wrapper are
maintained independently within SymQ. There is no import,
fixture or dependency from another private repository.

The PR remains Draft: CI establishes qualified behavior on its exact
source tree, not independent mathematical code review, a universal
quantum-circuit theorem, or an improvement on a true DQI workload.
