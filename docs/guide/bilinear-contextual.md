# Certified contextual GF(16) rewrite (stacked research integration)

**Experimental and classical only.** This guide qualifies a deliberately
stacked integration of [SymQ PR #124](https://github.com/yoch/symq/pull/124)
(contextual SAT proof and immutable apply) with
[PR #126](https://github.com/yoch/symq/pull/126) (exact GF(4)-tower
rank-9/15 synthesis). This branch is not a merged, released API.

## Exact contract

`apply_tower_substitution(source, span, n, modulus, wires, contract, weights)`
constructs a complete phase-free X/CX/CCX multiplier and maps its
`3*n` local wires (A/B/accumulator in that order) to **distinct existing
global wire indices**. It does not guess a span, polynomial basis,
ancilla preparation or output projection.

The original block within the declared span must implement the same
function at the insertion point. This is proved by contextual SAT,
including the actual prefix and the declared classical input/cut
contract; a tensor certificate alone is **not sufficient**.
All output wires agree, and any declared clean/borrowed wires are
proved restored by both versions. The frozen proof is rechecked before
constructing the immutable replacement program. A failure, timeout,
stale receipt, wrong modulus or invalid wire map returns no application.

A single absolute deadline bounds factor construction, proof, replay,
and immutable result construction. `weights=GateWeights(...)` is a
declared **integer gate proxy only**, not T-count, depth, surface-code
volume, the official Kaggle score or any hardware-calibrated metric.
By default the wrapper requires the proposal to decrease that proxy;
`require_saving=False` opts out of this policy but never disables proof
obligations.

## Runnable GF(16) demonstration

The [complete example](../../examples/bilinear_contextual_substitution.py)
uses the native GF16 polynomial `0x13`, a 13-wire surrounding circuit,
a prepared scratch wire 12 and a strict [start,stop) slice.

```python
from symq import Budget, Circuit
from symq.generators import gf2n
from symq.labs.bilinear_substitution import apply_tower_substitution
from symq.labs.contextual_substitution import GateWeights, SubstitutionContract

old = gf2n.emit(4, gf2n.schoolbook(4)).circuit
source = Circuit(13, list(old.gates))
application = apply_tower_substitution(
    source, (0, len(source.gates)), n=4, modulus=0x13,
    wires=tuple(range(12)), contract=SubstitutionContract(),
    weights=GateWeights(cx=1, ccx=12),
    budget=Budget(max_seconds=25),
)
assert application.proof.certified
assert application.proof.cost.weighted_delta < 0
```

A separate CI integration suite checks an actual **prepared and restored
cut wire** with nontrivial surrounding gates, and independently replays
all legal classical inputs. Missing preparation, a corrupted target,
the wrong GF16 basis `0x19`, duplicate wire assignments and an
unprofitable declared cost all fail closed.

The same constructive family supports GF64 (`0x43` or `0x49`), but
a large-context SAT proof has not yet been qualified as a general
timing or scalability claim. All proof claims above are **classical
basis-state** statements under explicit input restrictions. They do
not imply unrestricted coherent channel, HMR, measurement/feedback,
arbitrary quantum phases, or independently certified UNSAT artifacts.

## Attribution and evidence

The bilinear method follows the [Polytof MIT-licensed research source](https://github.com/ZIB-IOL/polytof)
at `0dcac107d15adc34dc646242d222f21ae7d32699`.
The distinct [James Barlow public KMB evaluation dataset](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation)
is declared Apache-2.0; uploaded source bytes and their hashes are
documented in [SOURCE.md](../../benchmarks/corpus/kaggle_bilinear/SOURCE.md).
These are public development cases, not a sealed holdout or official
quantum competition score comparison.

Use `python -m pytest -q tests/test_bilinear_contextual_integration.py`
with the `symq[sat]` optional dependency for reproducible exact-HEAD
integration tests. CI success demonstrates exercised obligations on that
source tree, not a general proof of the implementation.

## File-driven P0 workflow and public external-source demonstration

The separate [P0 end-to-end workflow](substitution-p0-workflow.md) uses
this same experimental contextual SAT theorem and frozen replay on
strict QASM, classical KMX or JSON source/replacement files, with an
explicit JSON contract, gate weights and a report/sidecar that can be
rechecked without the original files. A qualified public `gf16-07`
KMB fixture is imported through an independent, source-pinned decoder,
placed at a real prepared cut and compared against the GF16 rank-nine
candidate. This remains an **exposed development case**, not a
holdout or a quantum coherent/HMR proof.
