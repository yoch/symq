# Obligation receipts (research)

`symq.labs.obligation_receipt` runs one table or clean-ancilla check and returns a
**receipt**: a JSON object that records what was asked, of which inputs, under which
settings, and what the checker answered. It is for keeping track of many checks, for
example in a project that verifies hundreds of loaders and ancillas, and for rerunning
any of them later. It is **not a certificate**: it proves nothing by itself.

| Obligation | Checker | Engines |
| --- | --- | --- |
| `affine_table` | `affine_table.verify_affine_table` (version-2 contract) | `anf`, `sat` |
| `shared_table` | `shared_table.verify_shared_table` (version-3 contract) | `anf`, `sat` |
| `clean_ancilla` | `backward_ancilla.check_clean_ancilla` or `shift_diagonal_ancilla.check_shift_diagonal` | `pauli`, `shift_diagonal` |

```python
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.obligation_receipt import prove_obligation, replay_obligation

source = program_to_dict(HybridProgram(2, 1).ccx(0, 1, 2).ccx(0, 1, 2))
receipt = prove_obligation("clean_ancilla", source, {"target": 2}, engine="pauli")
assert receipt["verdict"]["status"] == "clean"
assert receipt["portable_certificate"] is False

replay = replay_obligation(receipt, source, {"target": 2})
assert replay["status"] == "confirmed"

other = program_to_dict(HybridProgram(2, 1).ccx(0, 1, 2))
assert replay_obligation(receipt, other, {"target": 2})["status"] == "mismatch"
```

## What a receipt records

- `obligation`, `engine`, and a readable `statement` summary (widths, legal domain size,
  clean and dirty wires, how records and measurements are treated, the theorem in words);
- `source_sha256` and `statement_sha256`: `symq.hashing.canonical_sha256` of the source
  document (`program_to_dict`) and of the statement (the contract, or `{"target": wire}`);
- `settings`: the budget (durations only: an absolute deadline is refused, it could not be
  replayed) and the limits or bounds of the call, with the checker's defaults written out,
  so that a replay under a later version runs the same check. A check is refused inside a
  `VerificationSession`, whose limits a receipt could not record;
- `checker`: the function that ran, and the proof kind the table verifiers report;
- `verdict`: status, failed obligation, witness and reason, as the checker gave them;
- `resources`: the checker's counters and, if it stopped, its resource report;
- `symq_version`, and `receipt_sha256`, a digest of the rest. Anyone can recompute that
  digest: it detects accidental edits, not forgery.

## Replay

`replay_obligation(receipt, source, statement)` refuses a malformed receipt, and a source
or a statement whose hash is not the receipt's, before running anything. It then runs the
same check with the receipt's settings and compares everything a fresh receipt would say:
the statement summary, the settings, the checker and the flags, the status and failed
obligation, and the witness where it is deterministic (every engine but SAT):

| Status | Meaning |
| --- | --- |
| `confirmed` | Same inputs and the same answer, as above. Only a decisive `confirmed` supports the receipt's claim, for these inputs; two `inconclusive` (or two `unsupported`) results are also `confirmed`: the same check stopped the same way |
| `concluded` | The receipt was `inconclusive`; the replay decided |
| `inconclusive` | The receipt was decisive; the replay ran out of resources |
| `unsupported` | The replay could not run the check here, for instance without a SAT solver |
| `mismatch` | Other inputs, a malformed or edited receipt, a field that describes the check differently from what it is, or another verdict |

SAT witnesses are not compared: the solver may return another valid one, and the table
verifiers replay every witness on the source before reporting it. The clean-ancilla
witnesses are computed exactly from the symbolic error effect, deterministically, and are
compared. Resources and timings are not compared. A replay under another SymQ version says
so (`same_version`).

## Scope

A table verdict is conditional on the declared contract, including its address domain;
that the caller prepares that domain is a separate proof. `clean` is about the final value
of one wire, not equality of channels. Integrating receipts with
`symq.labs.proof_graph` (as obligation nodes, with composition) is not part of this first
version; it is designed in [yoch/symq#261](https://github.com/yoch/symq/issues/261).

```bash
SYMQ_TEST_REQUIRE=sat python -m pytest -q tests/test_obligation_receipt.py
```
