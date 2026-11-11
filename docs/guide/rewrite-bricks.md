# Portable classical rewrite bricks (research)

`symq.labs.rewrite_bricks` packages a reusable local pattern, replacement and
cut obligations as a closed JSON document. Every application locates the
pattern in the actual source, maps the obligations, calls the existing
`prepare_local_classical`, and runs a fresh contextual SAT proof. A successful
example or an earlier site's report never substitutes for these obligations.

## Exact first scope

The brick grammar is X/CX/CCX/MCX on locally numbered wires. The conclusion is
the existing **classical all-output contextual theorem** under the caller's
explicit initial constants. It preserves arbitrary unmentioned inputs,
including accumulation targets and declared borrowed wires. No coherent,
HMR, instrument, relative-phase-gate or table specification is added.

The document separates these roles:

| Field | Meaning |
| --- | --- |
| `pattern`, `replacement` | Actual local reversible circuits, on the same width |
| `cut_contract` | Required local `clean_at_cut`, `restored_at_cut` and Boolean `cut_assumption` over `u.<wire>` |
| `phase_policy` | Exactly `phase_free_only`; other phase/measurement grammars are refused |
| `classical_mapping` | Exactly `[]` in this version; no measurement-slot renaming is inferred |
| `sources` | Authored/adapted origin, source URL/revision, license and license URL |
| `examples` | Self-contained positive sites and mutants, with explicit domains and expected checker outcomes |

Every local wire must occur in the pattern, so the locator can determine a
complete injective map. Additional unmentioned ancillas, ambiguous occurrences
and unproved resource availability do not produce an applicable candidate.

The brick supplies **requirements at the cut**, never assumptions about the
initial state of a new source. The caller must supply `initial_constants` for
each use, even when it is `()`. Those are global input-wire indices. The
checker proves the local requirements from the actual prefix on that domain,
then proves all-output equality and restoration. The initial domain remains
a declared classical restriction, not proof of an external preparation.

## Example: product computation, XOR and uncomputation

The authored MIT example
[`examples/rewrite_bricks/clean_product.json`](../../examples/rewrite_bricks/clean_product.json)
contains this local identity:

```text
CCX(a,b,s); CX(s,t); CCX(a,b,s)  ->  CCX(a,b,t)
```

It requires `s=0` at the cut, restores `s`, `a` and `b`, and permits arbitrary
`t`. With dirty `s`, the original additionally XORs its initial value into
`t`, so the identity cannot be used under that wider domain.

The package contains two positive contexts, with local-to-global maps
`[0,1,2,3]` and `[4,1,5,2]`, a dirty-scratch mutant, and a replacement with the
product toggle removed. These are small synthetic development cases, not
a certification of any external circuit or untouched holdout evidence.

```python
from pathlib import Path

from symq.circuit import circuit_from_dict
from symq.labs.classical_transcript import Program, digest
from symq.labs.rewrite_bricks import (
    check_brick_examples, load_classical_brick, run_classical_brick,
)
from symq.labs.rewrite_request import replayed_candidate
from symq.resources import Budget

# Pin the bytes independently of a received package or its saved reports.
brick_pin = "d3c2d8d8bcaa2155a8b3b599ac7911b449fb996ade94495bdbf1b5658618ea54"
brick = load_classical_brick(
    Path("examples/rewrite_bricks/clean_product.json").read_bytes(),
    expected_sha256=brick_pin,
)
examples = check_brick_examples(brick, expected_brick_sha256=brick_pin)
assert examples["all_expectations_met"]
assert examples["authorizes_other_sites"] is False

# Here the selected source is the inspected second fixture. In an integration,
# use the actual caller-selected source and its independently recorded pin.
case = brick.to_dict()["examples"][1]
source = circuit_from_dict(case["source"])
source_pin = digest(Program.freeze(source))
use = run_classical_brick(
    brick, source, expected_brick_sha256=brick_pin,
    expected_source_sha256=source_pin, initial_constants=((5, 0),),
    budget=Budget(max_seconds=10),
)
assert use["status"] == "equivalent"
assert use["quantum_mapping"] == [4, 1, 5, 2]

# Stored JSON is untrusted. This existing accessor replays its embedded proof.
candidate = replayed_candidate(use["proof_report"])
assert candidate is not None

# The preceding success has no authority over a new domain.
dirty = run_classical_brick(
    brick, source, expected_brick_sha256=brick_pin,
    expected_source_sha256=source_pin, initial_constants=(),
)
assert dirty["status"] == "precondition_failed"
assert dirty["proof_report"]["candidate"] is None
```

## Identity, trust and failure behavior

The brick pin is SHA-256 of its **exact bytes**, including whitespace. The
source pin is the existing canonical classical stream `digest(Program)`.
The caller supplies both pins to every use. Matching a hash identifies the
chosen contents; it does not prove the contents correct. Reading an expected
pin from the same untrusted artifact is not an independent trust anchor.

`load_classical_brick` validates the closed schema and immutable bytes. Each
use checks the bytes and schema again, snapshots the source, checks its pin,
and reruns the source-bound checker. Edits to the pattern, replacement,
obligations, source, provenance or examples invalidate the old brick pin.
Unknown fields, duplicate JSON keys, embedded `verified`/`proof_report` flags
or executable entry points are refused. Source/license metadata is declared
provenance; the loader does not fetch URLs or authenticate legal clearance.
An adapted source requires a lowercase 40-digit commit identity or 64-digit
content digest in `source_revision`; a moving branch name is refused. Authored
sources may leave it null. The pin format does not itself authenticate an
upstream source or establish that the adaptation matches it.

A unique structural location yields a fresh preparation and proof report.
`not_found` or `ambiguous` has no proof report. A proof failure retains the
normal precise `precondition_failed`/`not_proved` status and no candidate.
Missing SAT is `unsupported`; a time or source-size cap is `inconclusive`.
An expired whole-call deadline withholds even an otherwise positive inner
report. Invalid input or a mismatched consumer pin raises a typed exception.

The example checker executes every positive and mutant. Expected labels are
test expectations only. A mutant can expect `equivalent`: a double X is
neutral on all inputs, and a mutation can also be neutral only under the
declared preconditions. Such mutants still run the full contextual proof.
Every package must include a positive case and at least one mutant expecting
`precondition_failed` or `not_proved`. The checker never accepts `unsupported`
or `inconclusive` as a successful expected outcome; a matched negative
regression is not a global inequivalence theorem. Tests independently
enumerate the sample programs and confirm both the positive identities and
actual differing negative-mutant inputs.

## Limits and reproduction

This first adapter retains full bounded sources: 2,000,000 brick bytes,
100,000 operations per source, at most 256 local wires, at most 4096 global
site wires and 32 embedded examples. Example source width is capped at 256.
Limits precede copying oversized site circuits. The existing expression
depth cap applies to cut predicates. The shared cooperative time budget
covers capture, location, preparation and proof; it is not a hard OS wall or
RSS bound. Unenforceable term/node/byte budgets are explicitly refused,
including inherited budgets. It does not replace the separate large-source
window/cone work.

Optional `weights` are passed to the existing declared cost proxy. Correctness
is decided independently of that proxy; no hardware or competition score is
implied. General original-input Boolean assumptions and portable quantum
contracts require separately reviewed extensions to this first manifest.

```bash
python -m pytest -q tests/test_rewrite_bricks.py
```

No new optimization discovery, allocator or proof kernel is introduced. The
change connects a reusable declarative artifact to the existing source-bound
preparation, substitution and replay contracts.
