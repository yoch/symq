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
- **Report.** The report embeds both streams, the contract, the result with every obligation,
  the declared cost and, when proved, the rewritten candidate. `application` is `applied`,
  `not_proved` or `refused_by_cost_policy`.
- **Replay.** `symq replay` reruns the checker from the embedded streams. It refuses a report
  whose pinned hashes, costs or candidate do not belong to its request (exit 3). The fresh
  outcome is the one reported: a replay that times out is `inconclusive`, not tampering.

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
`candidate`: the checker attaches it, and a result rebuilt from JSON or edited by hand cannot
(`symq.labs.rewrite.attach_candidate`). Each input is frozen on entry and proved once; the
whole-call deadline starts before freezing and hashing.

`replay_substitution` and `replay_hybrid_substitution` rerun the checker with a receipt's
weights and raise `ReceiptMismatch` if the source, candidate, contract, span or cost differ. A
receipt and its hashes are not a portable proof certificate.

Costs are a declared integer proxy, `Weights`: a price per operation name, where `mcx` and `mcz`
are named by their wire count (a three-wire `mcx` is priced as `ccx`). Unlisted operations cost
`default`. The weighted delta is meaningful only under those declared units; it is not a T-count,
a depth, a hardware cost or any competition score, and it never changes a proof decision.

## Public evidence

`python -m benchmarks.rewrite_qualtran_hmr` runs the coherent theorem on the public Qualtran
GF2MulMBUC decompositions (Apache-2.0, commit `638777f`), inside a synthetic one-gate prefix and
suffix. The measurement-based uncompute replaces the reference decomposition; a mutant drops
the conditional phase correction. The independent Kraus-trajectory oracle of
`tests/testkit/kraus_oracle.py`, which shares no code with the checker, then compares the whole
programs on every data coherence. These fixtures were explored during development, so this is
not a holdout; the weights are the declared proxy `ccx = 12, hmr = 0, cz = 2`.

| Case | Checker | Oracle: coherences differing | Declared weighted delta |
| --- | --- | --- | --- |
| m = 1, with correction | equivalent, applied | 0 of 16 | −10 |
| m = 1, correction dropped | not proved | 6 of 16, none on the diagonal | — |
| m = 2, with correction | equivalent, applied | 0 of 256 | −40 |
| m = 2, correction dropped | not proved | 96 of 256, none on the diagonal | — |

`tests/test_rewrite_qualtran_hmr.py` reruns the table. The classical theorem has no external
evidence yet beyond the tests: its tower-multiplier example uses SymQ's own generators.

## Limits

- No output projection, garbage or phase in the classical theorem; no arbitrary rotations, H/S/T
  or general QASM 3 in the coherent one.
- The coherent oracle is exact but small; a refusal at its bounds says nothing about validity.
- Both checkers verify one site at a time. They are not optimizers and do not search for
  replacements.
