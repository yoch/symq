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

## The classical theorem

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
