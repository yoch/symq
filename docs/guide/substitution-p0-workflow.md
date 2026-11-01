# P0 — Workflow de substitution contextualisée reproductible

**Experimental, Draft / research API.** This is a *complete narrow
workflow* for a local **classical basis-state** rewrite, not a stable
compiler API, universal quantum equivalence checker, quantum phase
proof, HMR support or independent portable SAT/UNSAT certificate.

It composes [the contextual SAT proof contract](contextual-substitution.md)
from PR #124 with the frozen application and replay qualified in PR #128.
No new SAT theorem, hidden input assumption, or private repository
dependency is introduced.

## In one command: import → contract → proof → cost → report

Input circuits may be strict `.json`, OpenQASM 2/3 `.qasm` /
`.qasm2` / `.qasm3`, or *classical-only* kickmix `.kmx`. Anything
unsupported (including binary `.kmb`, HMR, phase gates, reset,
conditional measurement) is **rejected**, never silently converted.
All input files are read once into a byte snapshot; the SHA-256
fingerprints reflect exactly the bytes that were parsed. For the
public KMB demonstration below, an independently tested adapter
converts the source KMB into the explicit JSON classical IR.

The request is one closed JSON document with relative source and
replacement filenames, an exact global gate index interval and
an explicit classical input/cut contract:

```json
{
  "schema_version": 1,
  "kind": "symq_contextual_substitution_request",
  "source": "source.qasm",
  "replacement": "replacement.json",
  "span": [2, 3],
  "contract": {
    "initial_constants": [[4, 0]],
    "clean_at_cut": [4],
    "restored_at_cut": [],
    "cut_assumption": null
  },
  "weights": {"x": 1, "cx": 1, "ccx": 2, "mcx": 10}
}
```

The exact, committed
[QASM source](../../examples/contextual_workflow/source.qasm),
[replacement](../../examples/contextual_workflow/replacement.json)
and [request](../../examples/contextual_workflow/request.json)
reproduce an **MCX with 3 controls** replaced by a compute/use/uncompute
sequence of three Toffolis. The source prefix computes/uncomputes an
explicitly declared zero scratch wire. The verifier must prove that
scratch really is zero at the insertion cut and that both local blocks
restore it. A dirty scratch state is *not* part of that declared
classical input domain.

```bash
python -m pip install -e ".[sat]"
python -m symq.labs.substitution_workflow verify \
  examples/contextual_workflow/request.json \
  --report /tmp/symq-contextual-report.json --timeout 30
python -m symq.labs.substitution_workflow replay \
  /tmp/symq-contextual-report.json --timeout 30
```

The first command returns `0` for a proven, freshly applied
rewrite, `1` for an unproved or failed cut precondition, `2`
for unsupported/inconclusive, and `3` for malformed inputs.
It writes a full self-contained JSON receipt plus a
`<filename>.sha256` sidecar on completed proof attempts.

The receipt contains the exact source and replacement gate streams,
the span and closed contract, the declared integer weights,
source-file SHA-256 values, the named proof obligations and their
outcomes, the original/optimized gate counts and weighted delta,
and — **only after a fresh proof and immutable replay succeeds** —
the completely assembled candidate circuit. Non-equivalent or
unproven cases contain `"candidate": null`. Replay checks both
SHA-256s, reconstructs from the *embedded* streams and re-runs
the proof; it never trusts a saved outcome or receipt flag.
Tampering is rejected, including attempts to edit the outcome and
recompute the report SHA-256. Replayed equality is theorem-relative
and **does not** upgrade a restricted classical input contract to
an unrestricted quantum coherent-channel proof.

The request schema rejects unknown fields, duplicate JSON keys,
non-integer or repeated wire indices, nonfinite durations and
unsupported Boolean assumptions. An optional
`cut_assumption` accepts only tagged arrays:
`["const", true]`, `["var", "u.4"]`,
`["not", ...]`, `["and", a, b]`,
`["xor", a, b]`, `["eq", a, b]`.
Every expression must be proved at the **actual cut**, and the AST
is bounded. The current research runner limits inputs to 2 MB,
15,000 gates and 128 wires. It cannot hard-enforce process RSS and
uses a cooperative same-process wall deadline. Failures before
source parsing or during output I/O may produce an explicit nonzero
exit code without a full report.

## Real, byte-pinned public case: GF(16)

```bash
python -m benchmarks.public_kaggle_contextual_p0 \
  --output-dir /tmp/symq-public-gf16-p0
```

This imports the original **`gf16-07.kmb`** from James Barlow's
[VQCC bilinear KMB agent evaluation dataset](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation)
(exposed *development* corpus, Apache-2.0 **declared in the
original README**). Its manifest SHA-256 and original KMB bytes are
authenticated by SymQ's existing independent
[source-pinned loader](../../benchmarks/corpus/kaggle_bilinear/SOURCE.md).
The KMB source is lowered to X/CX/CCX and checked against the
original independent byte-interpreter on **all 4,096 dirty-register
basis inputs**. It is inserted into a real 13-wire circuit with a
prefix establishing a clean cut wire and a nontrivial suffix.
The replacement is the independent rank-nine GF16 tower circuit
for the *same* `0x13` modulus. The script exports the original,
replacement, request/contract and full SAT proof/cost receipt,
then replays the exported report and writes a provenance summary.

This **does** constitute a complete imported external-source
substitution case. It is **not** a sealed holdout, a broad compiler
benchmark, a proof of practical HMR correctness or an official
Kaggle competition score improvement.

## Remaining gates

- **P0:** a second, independent source-produced and locally
  qualified *measurement/HMR* substitution with explicit physical
  channel/instrument obligations (the classical workflow here cannot
  establish these).
- **P1:** fresh external optimized pairs and a frozen, paired
  QCEC/PyZX/other baseline protocol (complete status distribution,
  wall/CPU/RSS and timeouts, no source leakage between dev/holdout).
- **P2:** reviewer-approved, small, stable Python façade and a
  versioned installer/compatibility policy. Keep this runner opt-in
  until that independent API review is complete.

For a reviewer, run
`python -m pytest -q tests/test_substitution_workflow.py`
and inspect the independent CI artifacts produced by the
`contextual-p0-workflow` job. Passing CI and replay qualify the
specific implementation and tested sources, **not** an externally
audited correctness theorem or a publication-grade performance ranking.
