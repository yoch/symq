# Contextual rewrites (experimental)

A *contextual rewrite* replaces the operations of a source program in an exact `[start, stop)`
interval by a replacement, and SymQ decides whether the replacement **at that site** preserves
the requested behaviour under an explicit contract. Validity there does not mean validity
everywhere: the surrounding prefix may establish facts, such as a clean scratch wire, that the
replacement relies on. The checkers live in `symq.labs` and carry no API promise.

Two theorems are available, and neither is chosen for you:

| Theorem | Checker | What is proved |
| --- | --- | --- |
| `classical` | `symq.labs.contextual_substitution.check_substitution` | Reversible X/CX/CCX/MCX circuits agree on every output for every basis input in a declared domain |
| `coherent` | `symq.labs.hybrid_substitution.check_hybrid_substitution` | The bounded local coherent channel (or instrument) of the replaced block is unchanged, on every `|x><y|` coherence |

A classical input restriction never becomes a quantum statement: the `classical` theorem says
nothing about superpositions, phases, measurements or entanglement with borrowed wires.

## From the command line

`symq rewrite` reads one request file that names a source and a replacement next to it:

```json
{"schema_version": 1, "kind": "symq_rewrite_request", "theorem": "classical",
 "source": "source.qasm", "replacement": "replacement.json", "span": [2, 3],
 "contract": {"initial_constants": [[4, 0]], "clean_at_cut": [4], "restored_at_cut": [],
              "cut_assumption": null},
 "weights": {"by_kind": [["ccx", 2], ["mcx", 10]], "unit": "declared_units", "default": 1},
 "require_saving": false}
```

```bash
symq rewrite examples/rewrite/request.json --report report.json
symq replay report.json
```

- **Sources.** Classical sources and replacements are OpenQASM, kickmix `.kmx` or the JSON
  circuit format of `symq check`. A coherent source is a `hybrid` program JSON
  (`symq.experimental.serialization`); its replacement is a `hybrid_fragment` JSON.
- **Exit codes.** 0 when the rewrite is proved, 2 when it is not (`not_proved`,
  `precondition_failed`, `inconclusive`, `unsupported`), 3 for invalid input or an edited
  report. A rewrite checker never reports a proved difference: a local counterexample need not
  be reachable from the global input.
- **Isolation.** `--isolate` runs the proof in a fresh process with hard wall-clock and memory
  limits (`--timeout`, `--memory-mib`); without it the deadline is cooperative.
- **Report.** Version 2 has two parts.
  - The reverifiable part holds `request` (both streams, the contract, the weights), `result`
    (every obligation and the declared cost), `application` and, when applied, `candidate`.
    `application` is `applied`, `not_proved` or `refused_by_cost_policy`.
  - `provenance` holds the digests of the input files and, with `--isolate`, how the proof ran.
    It is historical metadata: replay cannot authenticate it without the original bytes.
- **Replay.** `symq replay` reruns the checker from the embedded request. When the fresh outcome
  is decisive (`equivalent`, `not_proved` or `precondition_failed`), the stored `result`,
  `application` and `candidate` must equal the recomputed ones exactly. Otherwise the report is
  refused with exit 3 and every differing field is named. A stored negative result is never
  silently replaced by a fresh positive proof, nor the reverse. A replay that ends
  `inconclusive` or `unsupported` reverifies nothing and exits 2. The output says what was
  reverified and marks the provenance as not reverified. Replays are deterministic for the same
  code and SAT solver; another solver version can change a witness, which is then reported as a
  difference.
- **Candidates.** `symq.labs.rewrite_request.replayed_candidate(report)` is the only way to get
  the rewritten stream from a report. It replays the report first and returns the candidate of
  the fresh proof. A report is untrusted JSON until then.

## Typed CLI output, engine choice and cut locator

These features are **opt-in research ergonomics**. They do not extend the
mathematical semantics of a rewrite or authorize an unproved candidate.

### JSON output is now machine-readable even on early failure

For `symq rewrite` and `symq replay` the CLI emits **one JSON object**
on stdout for every normal, inconclusive or invalid-input runtime path,
rather than leaving a parser with an empty stdout or a flat status
lacking `result`. Every status has at least:

```json
{
  "schema_version": 1,
  "kind": "symq_rewrite_cli_result",
  "application": "not_applied",
  "result": {
    "outcome": "inconclusive",
    "reason": "whole-call deadline exhausted"
  }
}
```

On a successful proof the same envelope retains `application="applied"`
and the **full original proof result**. Timeout and unsupported checks exit
`2`, malformed runtime inputs exit `3` with `result.outcome="invalid"`, and
a stored report that contradicts its recomputed proof exits `3` with
`result.outcome="receipt_mismatch"`; none produces a candidate. `invalid`
and `receipt_mismatch` are *CLI statuses*, not verifier decisions or proof
theorems. The exit code remains authoritative. Replaying a
`symq_verification` artifact keeps its established contract: errors go to
stderr, not into this envelope.
Parser **usage errors** raised by argparse (e.g., missing required options)
are not part of this runtime JSON contract and still go to stderr. The
saved version-2 proof report and its strict replay semantics are unchanged.

### Choose a stronger total theorem explicitly

An optional classical-only `engine` key in the request or `--engine`
CLI argument selects the checker:

```bash
symq rewrite request.json --engine auto --report /tmp/rewrite-proof.json
symq replay /tmp/rewrite-proof.json
```

The default remains `sat` for older requests. **`auto` is explicit** and
follows this conservative policy:

| Real source/replacement and contract | Checker selected | Proof |
| --- | --- | --- |
| Any input restriction (constants or Boolean predicate), clean-cut predicate or restoration obligation | `sat` | Exact contextual SAT, all cut conditions established |
| No contract and only X/CX on both compared blocks | `linear` | Stronger total affine permutation |
| No contract and a conservative degree-two ANF bound on both blocks | `packed` | Stronger total degree-two ANF permutation |
| No contract and higher-degree blocks | `zdd` | Stronger total symbolic permutation |

A total proof is valid in every surrounding context, but **cannot replace
a contractual proof when restoration obligations are present**. The
actual engine and theorem are included in `result`, and `auto` is pinned
to the embedded request so replay recomputes the choice. No heuristic
success counts as proof, no silent fallback from a failed checker is made,
and no measurement/HMR theorem can use a classical engine. The conservative
degree test may decline to use `packed` even for a mathematically quadratic
circuit; that only changes performance, not correctness.

### Discover a cut and local-to-global wire map without guessing

For a locally numbered **original reference block**, `symq locate` finds
exact contiguous occurrences in a larger source. It does not reorder or
optimize gates, infer ancilla preparation or silently rename measurement
slots.

```bash
symq locate examples/locate/source.json examples/locate/reference.json \
  --theorem classical
```

The output is a JSON `symq_rewrite_locations` document containing
`matches[].span`, `matches[].wires`, SHA-256 identities for the source
and pattern, and `advisory_only=true`. For the example, the complete
wire map is `[4, 1, 6]` and the half-open instruction span `[1, 3]`.

`unique` returns exit 0; `ambiguous`, `unmapped_wires` and `not_found`
return exit 2, as does `inconclusive` when the comparison or match bound
(`--max-candidates`) is reached; invalid file/grammar input returns exit 3
as JSON.
If any local wire is unmentioned in the block, its map is explicitly
`null`; if multiple spans match, **every match is listed rather than
one being selected**. For coherent use
`--theorem coherent` with a versioned global `hybrid` program and a
local `hybrid_fragment`; classical slots, conditions and values must
match exactly.

**Locate is not a proof.** Copy a *complete, unambiguous* span into the
explicit `symq_rewrite_request`; construct the classical replacement on
the full global width (or provide the HMR local fragment and its full
`contract.wires`), and still run `symq rewrite` to establish the
proper theorem. Automatic application or guessed cuts are deliberately
unsupported in this version.

### Prepare a local original and replacement without writing a global wire map

The next experimental step is **mechanical request preparation**, separate
from the checker and from its proof. The global circuit can have many
wires, while the original/replacement are small blocks numbered from zero.
A single, **complete and unambiguous** structural location is required:

```bash
symq prepare-rewrite \
  examples/prepare/source.json \
  examples/prepare/original.json \
  examples/prepare/candidate.json \
  --contract examples/prepare/contract.json \
  --weights examples/prepare/weights.json \
  --engine auto --output-dir /tmp/symq-prepared

# Preparation never proves or authorizes application.
symq rewrite /tmp/symq-prepared/request.json \
  --isolate --report /tmp/symq-prepared/proof.json
symq replay /tmp/symq-prepared/proof.json
```

The preparer embeds the **actual full-width source**, the locally mapped
candidate, the exact `[start,stop)` span, the **caller-supplied** contract
and cost weights. It uses the same local-to-global map `[4,1,6]`
returned by `symq locate` and rechecks that the mapped original is
byte/IR-identical to the selected span. The output directory is new: it is
claimed with an exclusive `mkdir` (any existing entry, including an empty
directory, a file or a symlink, is refused) and every file is created
exclusively, so existing destinations are never replaced. This is
no-replace publication, not atomic visibility of the directory: the files
are written and fsynced one at a time, `source.json` and `replacement.json`
before the `request.json` that names them, and `preparation.json` last. A
concurrent reader or a crash can therefore see a prefix of that sequence.
`preparation.json` is an advisory record of the emitted file hashes, not a
lock, and `symq rewrite` does not need it: on every intermediate state it
either refuses the input as invalid (exit 3, missing or truncated file) or
proves exactly the complete bytes that the finished directory contains.
To confirm that a directory is the complete, unmodified output of one
preparation, compare its files with the hashes in `preparation.json`.
Immediately before publication the preparer rechecks its frozen source,
local candidate and location fingerprints, so a caller mutation cannot
produce a manifest describing a different stream. Each emitted input is
bounded by the same 2 MB parser limit as the proof CLI; oversized streams
are refused rather than advertised as ready to verify.

It emits `source.json`, `replacement.json`, `request.json` and
`preparation.json`. The last file lists the exact original-input
SHA-256 and the emitted proof-input SHA-256, but is explicitly marked
`proved=false`, `candidate_authorized=false`, `advisory_only=true`.
These are **historical byte identities, not trustable proof certificates**.
Only the subsequent `rewrite` and fresh `replay` can certify the circuit
on its actual declared domain.

A contract JSON file is **mandatory** (use `{}` for completely
unrestricted inputs). Preparation never supplies an implicit clean
ancilla, restoration guarantee, phase equivalence, unsupported gate, or
output projection. If the exact original occurs more than once, or if
any local wire is unmentioned, the command exits 2 with a typed
non-actionable status and **writes no candidate file**. Invalid
contract, input or output path exits 3 with a typed JSON reason.
The engine choice is still constrained exactly as in `symq rewrite`.

This first mechanical lowering works only on **classical X/CX/CCX/MCX**
blocks; coherent/HMR keeps the explicit `wires` and physical
`HybridFrame` contract. It is deliberately not a quantum-channel
optimizer and does not try to commute gates to locate a match.

### Native installation diagnostics

The optional native ZDD is named `symq.backends._zdd`. When no binary
extension is installed, `symq doctor` now explains that it is **not
installed** rather than reporting a misleading partially initialized
module / circular import. The pure-Python `zdd` engine remains available.
A stale native ABI or a missing extension dependency is a different error
and is not mislabelled as a normal missing build.

## The classical theorem

### Relational original-input domains

`SubstitutionContract.initial_assumption` optionally carries a closed Boolean
expression over the **original global input wires** `x.<wire>`. The legal
domain is its conjunction with `initial_constants`. Unmentioned inputs remain
arbitrary. This is distinct from `cut_assumption`, whose `u.<wire>` variables
refer to the state after the actual prefix.

For example, a correlation at input can establish a clean wire at the cut:

```python
from symq import Circuit
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.sat.assumptions import Eq, Var

source = Circuit(3).cx(0, 1).cx(1, 2)
contract = SubstitutionContract(
    initial_assumption=Eq(Var("x.0"), Var("x.1")),
    clean_at_cut=(1,),
)
proof = check_substitution(source, (1, 2), Circuit(3), contract=contract)
assert proof.equivalent
```

The input relation `x.0 = x.1` is a **declared domain restriction**, not a
claim that SymQ proved its external preparation. SymQ checks that the domain
is nonempty, proves `u.1 = 0` from the actual prefix on that domain, and checks
the replacement and restoration. A false or contradictory input predicate
returns `precondition_failed`, with no candidate. Supplying a domain predicate
does not automatically supply the cut fact a local lemma needs.

The optional contract JSON field uses the existing expression grammar:

```json
{"initial_assumption": {"kind": "eq",
  "left": {"kind": "var", "name": "x.0"},
  "right": {"kind": "var", "name": "x.1"}},
 "clean_at_cut": [1]}
```

`prepare-rewrite --contract`, `rewrite` and `replay` preserve this field. Its
wire names remain global even when the original and replacement are locally
numbered; the preparer does not rename or infer the input domain. The complete
predicate is included in the contract digest and embedded report. Changing,
removing or strengthening it invalidates the old receipt, even if a fresh
proof on the new domain also succeeds. `--engine auto` selects contextual SAT
for any such predicate; total symbolic engines require the empty contract.

Compatibility is additive within request schema 1 and report schema 2. When
`initial_assumption` is absent or `None`, it is omitted from canonical output:
legacy contract hashes and report forms are unchanged. Older closed-schema
readers reject the new field rather than discard the restriction. The
expression depth bound remains in force; arbitrary callbacks, unknown nodes
and names outside the declared input wires are refused. This is a classical
SAT-backed proof/replay path, not a quantum preparation proof or a new LRAT
export capability.

### Source and restoration obligations

```python
from symq import Circuit
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.rewrite import Weights

source = Circuit(3).cx(0, 2).cx(0, 2).cx(2, 0).cx(0, 1)
contract = SubstitutionContract(initial_constants=((2, 0),), clean_at_cut=(2,))
result = check_substitution(source, (2, 3), Circuit(3), contract=contract,
                            weights=Weights.from_mapping({"cx": 3}))
assert result.equivalent and result.cost.weighted_delta == -3
assert result.candidate is not None   # the frozen rewritten program
```

The replacement uses the source's global wire numbering. With `P` the declared input domain, `A`
the prefix, `B` and `B'` the original and replacement blocks, the checker proves:

1. `P` is satisfiable;
2. for every `x` in `P`, the cut predicate holds on `A(x)`: the listed clean wires are zero and
   the optional `cut_assumption` (a Boolean formula over `u.<wire>`) is true;
3. `B` and `B'` agree on every output for every cut state satisfying that predicate;
4. both blocks restore every clean and `restored_at_cut` wire to its own cut value.

The unchanged suffix then preserves equality. Obligations 1–3 use the relational composition
engine of [the SAT guide](sat.md#relational-composition); each obligation is listed in the result
with its status and, for a failure, a typed witness (an input, or a cut state).

`symq.labs.bilinear_substitution.apply_tower_substitution` uses this theorem to replace a GF(2^n)
multiplier block (n = 4 or 6) by the certified tower multiplier on chosen wires; the factor
certificate is never taken as a proof of the cut.

## The coherent theorem

```python
from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.channel_composition import HybridFragment
from symq.labs.hybrid_substitution import check_hybrid_substitution

source = HybridProgram(3, 1, [HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)), HOp("ccx", (0, 1, 3))])
replacement = HybridFragment(4, (HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
                                 HOp("hmr", (3,), slot="b0"), HOp("cz", (0, 1), condition="b0")))
result = check_hybrid_substitution(source, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,))
assert result.equivalent and result.theorem == "local_coherent_channel"
```

The replacement uses local wires mapped injectively by `wires`. The data wires of the source are
arbitrary coherent inputs and its ancillas start in `|0>`. The checker delegates to
`symq.labs.channel_composition.verify_channel_transcript`:

- the actual prefix must prove every `clean` cut wire zero; a declaration is not enough;
- `preserved` wires must keep the identity channel, including off-diagonal correlations;
- `discarded` wires must be terminal and globally discarded;
- if a later operation reads a measurement record written in the block, the block is compared as
  an **instrument** (records kept) rather than a channel. The result's `theorem` is
  `local_coherent_instrument` and `instrument_slots` names those records.

The local oracle enumerates coherences and measurement branches, so it is bounded:
`max_local_width`, `max_events` and `max_branches` default to 6, 8 and 256 and are capped at 8,
12 and 4096 (`LIMIT_CAPS`). Exceeding a bound gives `inconclusive`. A connected circuit may be
wider than the block, because the prefix and suffix are handled compositionally.

## Results, receipts and costs

Both checkers return a frozen result satisfying the `Verdict` protocol. Its `outcome` is
`equivalent`, `not_proved`, `precondition_failed`, `inconclusive` or `unsupported`. Only an
`equivalent` result is `certified`, and only a result proved in the same call carries a
`candidate`. Each input is frozen on entry and proved once; the whole-call deadline starts
before freezing and hashing.

An `equivalent` result can only be built by the checker, in the call that ran the proof. It
carries a private seal that pins every compared field: outcome, reason, hashes, contract, span,
cost, obligations, theorem, and for the coherent theorem the wire map, `checked_pairs` and
`instrument_slots`. `dataclasses.replace` therefore cannot turn a `not_proved` result into an
`equivalent` one, attach a candidate to it, or move a proof to another rewrite: each attempt
raises `ValueError`.

`replay_substitution` and `replay_hybrid_substitution` rerun the checker with a receipt's
weights. They raise `ReceiptMismatch` if the source, candidate, contract, span or cost differ,
or if a decisive fresh result differs from the receipt on any field. A receipt and its hashes
are not a portable proof certificate.

**Trust boundary.** Through the public API, a result is `equivalent` and carries a candidate
only if a checker proved it in this process, on a frozen snapshot of its inputs, and a stored
report authorizes nothing until it is replayed. This is not cryptography. Code running in the
same interpreter can import private names or call `object.__setattr__` and forge anything; SymQ
does not defend against hostile code in its own process.

Costs are a declared integer proxy, `Weights`: a price per operation name, where `mcx` and `mcz`
are named by their wire count (a three-wire `mcx` is priced as `ccx`). Unlisted operations cost
`default`. The weighted delta is meaningful only under those declared units; it is not a T-count,
a depth, a hardware cost or any competition score, and it never changes a proof decision.

## Public evidence

Two P0 paths run both theorems on external public sources, end to end through the command line.
Each case is a set of versioned files: the source, the replacement and a `symq_rewrite_request`.
`symq rewrite --isolate` proves it under hard limits, the input files are deleted, and
`symq replay` reproves the report alone. CI runs both in the `research-evidence` job and keeps
the files and reports as artifacts. Both sources were explored during development, so neither is
a holdout, and the weights are declared proxies, not hardware costs.

| | Classical: public KMB multiplier | Coherent: public Qualtran uncompute |
| --- | --- | --- |
| Source | `gf16-07.kmb`, James Barlow's VQCC bilinear dataset, Apache 2.0, SHA-256 `636c554e…0f8c`, GF(16) modulo `0x13` | GF2MulMBUC m = 1 and m = 2, Qualtran `638777f`, Apache 2.0, fixture SHA-256 in the manifest |
| Files | `benchmarks/corpus/bilinear_kmb/rewrite/` | `benchmarks/corpus/qualtran/rewrite/` |
| Command | `python -m benchmarks.rewrite_kmb_context --output-dir DIR` | `python -m benchmarks.rewrite_qualtran_hmr --output-dir DIR` |
| Theorem | `classical` (SAT, basis states of the declared domain) | `coherent` (bounded local channel) |
| Context | 13 wires: three-gate prefix, the decoded KMB, two-gate suffix | One-gate prefix and suffix around the decomposition |
| Contract | Ancilla 12 declared 0 on input and clean at the cut | Data wires preserved, ancillas clean |
| Replacement | SymQ's 9-product tower multiplier | Qualtran's measurement-based uncompute |
| Independent check | Field arithmetic of `tests/testkit/field_oracle.py` on all 4,096 states of the KMB; candidate equal to the source on all 4,096 legal context states | Kraus-trajectory oracle of `tests/testkit/kraus_oracle.py` on every data coherence |
| Refusals required | Unprepared ancilla (`precondition_failed`), corrupted replacement (`not_proved`), edited report (replay exit 3) | Missing phase correction (`not_proved`), differing only off the diagonal |
| Declared weighted delta | −328 under `ccx = mcx = 32` | −10 and −40 under `ccx = 12, hmr = 0, cz = 2` |

### Classical: the public KMB multiplier

The KMB file is read from the corpus, which checks its SHA-256 against the manifest. It is
decoded by the strict reader of `benchmarks/kmb.py` and compared with the independent field
arithmetic on every state. It is then placed in the 13-wire context of the original #128 path.
Every SAT obligation must pass:
- `domain`: the declared input domain is nonempty;
- `prefix`: the actual prefix establishes the clean ancilla at the cut;
- `interface` and `suffix`: the block and its replacement agree on every output under the cut;
- `restore_original` and `restore_candidate`: both blocks restore the ancilla.

The candidate, taken only from a fresh replay, is checked on all legal states. The theorem says
nothing about phases or superpositions.

### Coherent: the public Qualtran uncompute

The measurement-based uncompute replaces the reference decomposition; a mutant drops the
conditional phase correction. The Kraus-trajectory oracle shares no code with the checker and
compares the whole programs on every data coherence.

| Case | Checker | Oracle: coherences differing | Declared weighted delta |
| --- | --- | --- | --- |
| m = 1, with correction | equivalent, applied | 0 of 16 | −10 |
| m = 1, correction dropped | not proved | 6 of 16, none on the diagonal | — |
| m = 2, with correction | equivalent, applied | 0 of 256 | −40 |
| m = 2, correction dropped | not proved | 96 of 256, none on the diagonal | — |

`tests/test_rewrite_kmb_context.py` and `tests/test_rewrite_qualtran_hmr.py` rerun both paths.

## Limits

- No output projection, garbage or phase in the classical theorem; no arbitrary rotations, H/S/T
  or general QASM 3 in the coherent one.
- The coherent oracle is exact but small; a refusal at its bounds says nothing about validity.
- Both checkers verify one site at a time. They are not optimizers and do not search for
  replacements.
