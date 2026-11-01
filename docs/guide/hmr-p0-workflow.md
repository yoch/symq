# P0 — Reproducible coherent HMR substitution with a real Qualtran source

**Experimental (unmerged research, not an API stability promise).**
This is the second P0 pathway, complementary to the classical
[file-driven classical substitution workflow in PR #128](https://github.com/yoch/symq/blob/e9c6abae7cf7f5c5782b2750f72ef67e0082cc39/docs/guide/substitution-p0-workflow.md).
Its proof is a **coherent quantum channel or observed instrument**
theorem, **not** a classical Boolean truth-table equivalence check.

## One command: import → quantum contract → verify → cost → replayed apply

The implementation is `symq.labs.hmr_workflow`, built on the
[coherent contextual substitution engine](hybrid-substitution.md)
from PR #125. It never invents a zero ancilla, classical preparation
condition or outcome-record equivalence. It accepts two **closed,
bounded JSON** files and one explicit request:

- The source is a versioned `symq.experimental.serialization`
  `HybridProgram` document with `data` arbitrary coherent wires,
  `ancillas` prepared **exactly in |0〉**, and quantum/classical
  `HOp` stream. Its complete prefix and suffix are retained.
- The candidate is a **local hybrid fragment**, with its own closed
  `hybrid_fragment` versioned document, local quantum wires and
  optional explicitly declared incoming classical slots.
- The request states the exact `[start,stop)` global operation
  interval, injective local-to-global wire map, local `clean`
  and `preserved` dirty frames, output discards, retained
  classical records, bounded oracle resources, caller-declared
  operation weights and the policy `require_saving`.

No permissive QASM/measurement import is claimed. Unsupported operations,
ill-defined record slots, unproved cut preparations, unknown fields,
missing feed-forward, bad mapping and exceeded resource limits
**fail closed**. The public Qualtran adapter emits the JSON explicitly
from authenticated normalized decomposition files.

The request format is strict:

```json
{
  "schema_version": 1,
  "kind": "symq_hmr_contextual_request",
  "source": "source.json",
  "replacement": "replacement.json",
  "contract": {
    "span": [1, 3],
    "wires": [0, 1, 2],
    "clean": [2],
    "preserved": [0, 1],
    "discarded": [],
    "observed_slots": [],
    "discarded_global": [],
    "weights": {
      "unit": "illustrative_integer_proxy_not_T_count",
      "by_kind": [["ccx", 12], ["hmr", 0], ["cz", 2]]
    },
    "max_local_width": 6,
    "max_events": 8,
    "max_branches": 256,
    "require_saving": false
  }
}
```

The `span` here is just a schema example; the actual interval is
calculated from the imported source. Clean and preserved wires are
**local indices**, whereas `wires` and `discarded_global` use
global indices. `observed_slots=[]` requests the outcome-forgotten
channel; a populated list requires **instrument equality**, retaining
the corresponding classical measurement records. A substitution that
preserves a channel but changes these records must be rejected.

The source input is bounded to 2 MiB, 128 global quantum wires and
4,000 operations; local channel leaves are bounded to six quantum
wires, eight measurement events and 256 branches by default.
The default command runs an isolated subprocess with hard whole-worker
wall/CPU/address-space limits, in addition to the proof engine's
cooperative deadline. Bounds are not a proof of fast scaling.

## Public reproducible example: Qualtran GF2MulMBUC m=1 and m=2

```bash
python -m pip install -e ".[dev]"
python -m benchmarks.public_qualtran_hmr_p0 \
  --output-dir /tmp/symq-hmr-p0

python -m symq.labs.hmr_workflow replay \
  /tmp/symq-hmr-p0/m1-full-none/hmr-proof.json
```

The source derives from the actual public
[Qualtran](https://github.com/quantumlib/Qualtran) GF2Multiplication and
GF2MulMBUC **decomposition traversal**, upstream commit
`638777fac4379bc62e2a1e4a52cf1a1753895d48`,
licensed **Apache-2.0**. SymQ's
[pinned source and license receipts](../../benchmarks/corpus/qualtran/README.md)
include upstream source SHA-256, regenerated normalized streams,
classical/quantum wire maps and prepared-zero frame. No private
benchmark data or hidden holdout is used.

The workflow imports the entire source and applies a real prefix
and suffix around the replacement. It compares the **prepared
multiplication + coherent uncompute** against **prepared multiplication
+ X-basis measurement + classically conditioned corrective phase**,
checking all 16 input matrix units for m=1 and all 256 for m=2.
An independent exact Kraus oracle validates the positive and
missing-correction negative labels **before** workflow qualification.

Four source-pinned development cases are exported:

| Case | Expected result | Independent quantum oracle |
| --- | --- | --- |
| m=1, measurement cleanup with correction | channel equivalent, replayed candidate | 16 input coherences |
| m=1, missing conditional phase correction | not proved; no candidate | off-diagonal coherence witness |
| m=2, measurement cleanup with correction | channel equivalent, replayed candidate | 256 input coherences |
| m=2, missing conditional phase correction | not proved; no candidate | off-diagonal coherence witness |

**Measured negative cost result:** under the declared illustrative
weights (CCX=12, HMR=0, CZ=2; other kinds default to 1), the
coherently valid m=1/m=2 candidates have weighted deltas of **+1**
and **+4**, respectively. They are allowed here only because
`require_saving=false`; a contract that requires a strict saving
would refuse to apply them. This is useful evidence of correct
verification, **not an optimization win**.

Each generated directory contains `source.json`,
`replacement.json`, `request.json`, `hmr-proof.json` with a
`hmr-proof.json.sha256` sidecar, and `provenance.json`.
The report embeds the **full original and replacement operation
streams**, exact physical contract, source/request byte SHA-256,
oracle result, operation counts and explicit weighted cost.
A candidate is embedded **only after** a second fresh check on an
immutable source snapshot. The workflow can refuse application based
on the declared cost even when the channel is equivalent; a
hypothetical gate-weight proxy is **not** physical T-count,
surface-code volume or an official Kaggle score.

A report can be replayed after deleting the input files:

```bash
python -m symq.labs.hmr_workflow verify request.json \
  --report proof.json --timeout 45 --memory-mib 1024
python -m symq.labs.hmr_workflow replay proof.json \
  --timeout 45 --memory-mib 1024
```

Both commands recompute the exact oracle, rather than accepting
`"outcome": "equivalent"` from JSON as a proof. The sidecar and
semantic SHA-256 detect accidental changes; they are **not
signatures** or independent cryptographic proof certificates.
Even a re-signed, falsified outcome cannot authorize an
application without a fresh coherent proof.

## Negative controls, instrument semantics, and scope

The regression tests deliberately remove corrective CZ feedback,
supply an unprepared coherent ancilla, forge a result and cost,
mutate an input stream, and declare invalid mappings or unbounded
operations. They also compare a channel that forgets outcomes to
an instrument that exposes `b0`: the same quantum channel can
remain equivalent when the record is discarded while the instrument
becomes **non-equivalent** after the classical bit is inverted.
A positive, compensated instrument case establishes that
retained classical records are supported when the contract permits.

**Caveats:** these are already-explored public development fragments,
not new independent compiler-optimized holdout cases. The local
six-wire coherent oracle is exponential; connected global circuits
may be wider only through the explicit composition theorem. This
does not support arbitrary rotations, all QASM3 measurements,
general ancilla borrowing, all possible quantum phase debts or
standalone independently checkable UNSAT certificates. No claim
of competing tool performance or Qant/DQI score improvement follows.

Reproduction on a pinned commit:

```bash
python -m pytest -q \
  tests/test_hybrid_substitution.py \
  tests/test_hybrid_substitution_independent_kraus.py \
  tests/test_hmr_workflow.py
```

The mandatory GitHub CI job archives every successful and rejected
report along with source/contract fingerprints. Promotion to a
stable P2 API requires an independent semantic review, source
freeze and approval of the accepted theorem.
