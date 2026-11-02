# Finite-table XOR loader contract (research; issue #144)

Two compiler emissions can be equivalent and equally incorrect. This opt-in
adapter compares an actual emitted reversible program against a separately
supplied exact lookup table, not another emission or a serialized PASS flag.

## Precise theorem and physical frame

An admissible input has explicit address (a), target (z), clean scratch (s=0),
and borrowed dirty workspace (d), with **all** quantum outputs retained.
The required mapping is

  |a,z,0_s,d> -> |a,z XOR T[a],0_s,d>.

Legal addresses form a nonempty explicit set. The target is either the
explicit FULL cube or an explicit set of allowed encodings. Arbitrary borrowed
dirty bits are preserved, not assumed zero or traced. Restricted target
encodings are **not** theorems for full dirty targets. No external preparation
of the input support is silently proved.

The table has one exact integer row per address word, **including illegal
addresses**: missing rows, out-of-width entries and implicit padding are
rejected. Bit i of the table value is XORed into target_wires[i]. Each listed
wire tuple is ordered LSB-first; changing order changes the contract. The
table_id and slot_id are both source-bound. The four wire roles must partition
the entire physical width exactly, with no alias.

The named classical claim checks every declared basis input. The named
coherent claim additionally proves equality on the linear span of those basis
states, including |x><y| off-diagonals and external references. This lift is
sound **only because** the accepted gate grammar consists of X, CX, CCX and
MCX: each is a phase-free basis permutation. It does not generalize to HMR,
reset, measurement, feed-forward, relative-phase Toffoli or phase rotations.
Those programs are refused before verification. A basis-only check would be
unsound for HMR; branch amplitudes and phases, corrections and records must
be handled by a separately verified quantum channel or instrument contract.

For SAT, an independent table-to-gates construction implements row-wise
address-selective controlled-X, inverting and restoring negative controls.
The existing exact SAT miter checks the actual emitted program against this
reference under the legal address/target predicate and zero scratch, retaining
all outputs. A counterexample is replayed directly against the literal table,
not merely against the synthesized reference. There is no assumption of
correctness of the generator or a saved PASS flag. The conclusion depends on
the reference construction and SAT encoding/solver; no LRAT proof is emitted.

## Two explicit exact backends

- SAT (default): optional python-sat; symbolic all-input comparison.
- Exhaustive: enumerate all declared legal basis states with a strict cap.

They prove the same theorem for the phase-free grammar. Missing SAT or a
predicate larger than the existing closed expression grammar is UNSUPPORTED.
Resource exhaustion is INCONCLUSIVE, never a proof. A mismatch carries a
concretely checked witness. Time limits are cooperative, not hard OS caps.
The budget max_terms limits the construction or enumerated states; native
max_nodes/max_bytes are refused instead of silently ignored, including when
they come from an enclosing `VerificationSession`.

Practical envelope with the default caps (development measurements, one
machine): a non-full legal set or target domain is expressed as a balanced
disjunction in the SAT assumption grammar, so more than 64 listed values is
UNSUPPORTED on SAT (expression depth bound). SAT proved 12 address bits in
about 37 s; 13 bits exceed the default reference gate cap. Exhaustive proved
10 address bits in about 95 s. The 16-bit structural limit is not reachable
with the defaults.

## Public synthetic example

Files in examples/table_xor/ specify two address wires (0,1), two target
wires (2,3), zero scratch wire 4 and arbitrary dirty wire 5. Legal addresses
are 0,1,2; the complete table is [0,1,3,2], with a deliberately specified
illegal-address row 3. Both structurally different emitted circuits implement
the contract over all four target words.

From the public checkout after installing the dev dependencies:

```bash
python -m benchmarks.table_xor_contract \
  --source examples/table_xor/linear.json \
  --contract examples/table_xor/contract.json --backend sat \
  --repetitions 3 --max-seconds 10 --output evidence/table-xor-linear.json

python -m benchmarks.table_xor_contract \
  --source examples/table_xor/selector.json \
  --contract examples/table_xor/contract.json --backend exhaustive \
  --repetitions 3 --output evidence/table-xor-selector.json

python -m pytest -q tests/test_table_xor_contract.py
```

API example:

```python
import json
from symq.circuit import circuit_from_dict
from symq.labs.table_xor_contract import (
    TableXorContract, check_table_xor, replay_table_xor,
)
from symq.resources import Budget

with open("examples/table_xor/contract.json") as f:
    contract = TableXorContract.from_dict(json.load(f))
with open("examples/table_xor/linear.json") as f:
    source = circuit_from_dict(json.load(f))

proof = check_table_xor(source, contract, backend="sat", budget=Budget(max_seconds=10))
assert proof.equivalent

# In a real pipeline, pin BOTH these hashes independently before accepting
# an untrusted receipt. Reading its own hashes back is NOT a trust anchor.
trusted_source_sha = proof.source_sha256
trusted_spec_sha = contract.sha256
fresh = replay_table_xor(source, contract, proof.to_dict(),
    expected_source_sha256=trusted_source_sha,
    expected_contract_sha256=trusted_spec_sha,
    backend="sat", budget=Budget(max_seconds=10))
assert fresh.equivalent
```

Replays require consumer-supplied source/specification digests and a
fresh exact check. Pass the same caps (`max_states`, gate caps) that the
original check needed. A fresh check that refutes the record raises
`ReceiptMismatch`; one that cannot conclude (a cap, the deadline, SAT
unavailable) is returned as `inconclusive`/`unsupported` and says nothing
about the record. The qualification command accepts consumer pins with
`--expected-source-sha256`/`--expected-contract-sha256`; without them it pins
the files it read and records `pins.origin` as self-derived. The qualification command requires a successful fresh
replay of every positive trial; proof and replay share a whole-trial deadline.
Saved backend, reason and count fields must match the fresh check. Source, table, target domain, legal set, wire order, table
identity, slot identity and theorem intent are all included in the digest.
Changing one invalidates the old receipt. Hashes identify content; they are
not mathematical proof authority. A receipt obtained under a *classical*
intent is never re-labelled as a coherent theorem without a fresh check.

The development-only qualification preserves all repetitions and failures,
source-file and in-memory specification hashes, Python allocation peak,
process RSS high-water mark, environment, versions, timings and recorded
witnesses. It uses a synthetic public corpus: no untouched holdout, scaling
claim or SOTA comparison is implied. Process RSS is not a hard memory cap.

Not implemented in this milestone: several tables or slots in one emission
(a contract holds one table; `table_id`/`slot_id` are identities bound into
the digest, so a per-slot check must declare the other slot's wires, and a
concatenated table is needed for a multi-slot loader), a receipt field for
the verifier and SAT solver versions (record them with the environment),
HMR/channel and visible-instrument proof,
source-format conversions that can drop unsupported gates, conditional target
encodings, automatic proof of preparation at a connected cut, floating-point
factorization tolerances, and broad table-compression or speedup claims.
Any such extension needs independent source-bound obligations and audit.
