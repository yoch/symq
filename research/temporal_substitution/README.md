# Exact transcript-bound substitutions (research-only, issue #89)

This prototype establishes **equality of two completely supplied classical reversible gate
streams for all global inputs and all global outputs**. It does not prove that either
stream implements a claimed higher-level algorithm. It does not support measurements,
resets, HMR, phases, observed-only outputs, or conditional clean ancillas.

## Proof argument

Supply a fully ordered stream consisting of identical common operations and local
replacement pairs. For each local pair, the public exact SymQ checker proves the
**total permutation** is equal on every local wire, treating scratch and accumulator
inputs as arbitrary. Each slot carries an injective local-to-global mapping; all
other global wires are the unchanged identity frame. Induction proves equality
of the fully reconstructed global streams, even when two slots share wires and
the joint interaction graph has a connected component wider than 64.

Source and destination are provided independently as complete Circuits, with
caller-trusted complete SHA-256 pins over canonical IR. Reconstructed streams
must match both exact Gate tuples, including all common prefix/suffix gates.
Missing or reordered gates, aliased maps, dirty-wire restoration or incorrect
local transformations cause failure. Cache reuse is **process-local only** and
keys contain both immutable local circuits, preserved contract, backend and budget;
mappings and full global transcript are rechecked for every proof invocation.
JSON reports are not accepted as proof inputs.

## Native path, cost, and exactness

Select the C/ZDD backend explicitly with `backend="zdd-native"` when installed;
each local slot must fit its native width limit. The global stream may exceed
64 wires because no full-width native symbolization is attempted.
Without the extension use an explicit pure-Python backend such as `sparse`;
there is **no automatic fallback**. Each local check is resource-bounded by
the requested SymQ Budget, with a separate whole-call deadline and a finite
expanded-gate cap. No speedup over monolithic checking has been measured.

```python
from symq import Circuit, Gate
from research.temporal_substitution.proof import (
    Common, Program, Slot, digest, verify_transcript,
)

local = Program.freeze(Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2))
empty = Program.freeze(Circuit(3))
pieces = [Common((Gate("cx", (0, 3)),)),
          Slot(local, empty, (0, 1, 2))]
left = Circuit(4).cx(0, 3).ccx(0, 1, 2).ccx(0, 1, 2)
right = Circuit(4).cx(0, 3)
proof = verify_transcript(
    left, right, pieces,
    reference_sha256=digest(Program.freeze(left)),
    candidate_sha256=digest(Program.freeze(right)),
    backend="sparse",
)
assert proof.equivalent
```

**Trust boundary:** The caller must independently authenticate the two source
hashes. Passing a hash calculated from an untrusted input only proves equality
to that same input. SymQ's symbolic engine and Python are part of the trusted
computing base; the report is not a checkable LRAT/Lean certificate. Exhaustive
small-circuit tests and counterexample replay add independent sanity checks.

Run: `python -m pytest -q tests/test_temporal_transcript_research.py`.
Native adoption requires exact-head CI, benchmarks on matched genuine workloads,
CPU/RSS and supported-case denominators, plus review of the proof boundary.
