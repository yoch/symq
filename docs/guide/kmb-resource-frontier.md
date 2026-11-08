# Pure-bit facts and reservations in complete KMB sources

The optional research adapter `symq.labs.kmb_resource_frontier` scans a complete,
independently pinned KMB v2 source with bounded NumPy buffers. Install
`pip install 'symq[source]'`. This is a sufficient resource analysis, not an
allocator, a substitution checker or an independent proof certificate.

For raw coordinates `[cut_op, lease_stop_op)`, the analyzer separates two facts:

- A quantum wire is a pure computational constant at `cut_op`, for every allowed
  quantum input (including external entanglement), classical input and measurement
  branch. An unconditional reset or HMR establishes zero; subsequent unconditional
  top-level X operations toggle it. An explicit independent input constant may
  instead supply the starting assumption. Every other possible value write forgets
  the fact. Missing writers leave arbitrary inputs, with no implicit zero.
- No source operation mentions that wire during the reservation. Controls and
  phase operations count as uses. The wire may carry a nonzero temporary value
  inside a proposed replacement; this analysis only reserves the source interval.

A proven one, an unknown value, source interference, unsupported semantics and an
expired budget have distinct diagnostics. An empty `available_zero_wires` list
means this sufficient rule found none; it does not prove no suitable ancilla exists.
A returned zero does not allocate a wire, prove the replacement restores it, or
prove its classical measurement slot is usable. Explicit input constants are a
nonempty declared product domain; no external preparation or correlated input
predicate is inferred. Cache relations and classical definition/use remain open.

## Accepted semantics

The complete source must use the exact KMB v2 enumeration: X/CX/CCX, SWAP/CSWAP,
Z/CZ/CCZ, NEG, R, HMR, classical stores/invert, PUSH/POP and INFO_TAG, with the
corresponding conditional variants. Z_POW, debug and unknown instructions are
rejected even outside the reservation. Conditional operations and operations under
a nonempty condition stack are treated as possible writes, never as known resets
or toggles. Empty POP is a no-op; a nonempty final stack is refused. Conditions
may depend on arbitrary classical state; this is not an SSA validation theorem.
All packets, counts, quantum aliases, operand ranges and header maxima are checked.
Coordinates are zero-based raw operation indices including INFO_TAG.

Only a private file-backed snapshot of the complete source is decoded. Copy and
hash share the same pass. An index is not built. Per-call limits bound source
bytes, operations, widths, observed wires, lease length and buffer size. The
single inherited wall deadline includes request validation, imports, snapshot,
validation, scanning, dependency hashing and cleanup. An expiration clears all
facts. Term/node/native-array-byte budgets are refused; use explicit adapter
limits and a process memory cap for this vector algorithm.

## Runnable example

This original MIT fixture resets one wire, then flips it. With NumPy absent the
adapter returns `unsupported` and no facts. With the extra installed it proves one.

```python
import hashlib
import struct
import tempfile
from pathlib import Path
from symq.hashing import canonical_sha256
from symq.labs.kmb_resource_frontier import assess_kmb_resources, replay_kmb_resources
from symq.resources import Budget

header = struct.pack('<16sIIII9Q', bytes.fromhex('d750c7d5c329d326e3cc9f6834f2b8bf'),
                     2, 1, 0, 0, 2, 0, 0, 2, 0, 0, 0, 0, 0)
payloads = {1: bytes([18, 17]), 7: bytes(8), 11: bytes(8)}
raw = header + b''.join(struct.pack('<QQ', k, len(payloads.get(k, b'')))
                       + payloads.get(k, b'') for k in range(1, 12))
source_pin = hashlib.sha256(raw).hexdigest()
request = {'kind': 'symq_kmb_resource_frontier', 'schema_version': 1,
           'source_file_sha256': source_pin, 'cut_op': 2, 'lease_stop_op': 2,
           'wires': [0], 'initial_constants': []}
query_pin = canonical_sha256(request)  # store independently with the source pin
pins = dict(expected_source_sha256=source_pin, expected_request_sha256=query_pin)
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'source.kmb'
    source.write_bytes(raw)
    report = assess_kmb_resources(source, request, **pins, budget=Budget(max_seconds=10))
    assert not report['candidate_authorized']
    assert report['status'] in ('assessed', 'unsupported')
    if report['status'] == 'assessed':
        assert report['facts'][0]['cleanliness'] == 'proved_one'
        assert report['available_zero_wires'] == []
        assert replay_kmb_resources(source, request, report, **pins,
                                    budget=Budget(max_seconds=10)) == report
```

Replay copies and rehashes the complete source, repeats validation and analysis,
and compares the entire receipt with strict types. The request separately pins
source, coordinates, wires and assumptions. Receipts pin analyzer, reader,
resource/request helpers and NumPy core content plus Python/NumPy versions.
Changes require fresh proof; a stored status or claimed dependency is no authority.
NumPy remains an execution dependency, not an independently verified kernel.

## Reproduce development qualification

```sh
python -m pip install -e '.[dev,source]'
python -m pytest -q tests/test_kmb_resource_frontier.py tests/test_kmb_resource_frontier_optional.py
python -m benchmarks.kmb_resource_frontier --output /tmp/frontier-dev.json --repetitions 3
```

The tests use an independent exhaustive scalar interpreter, a coherent Kraus
oracle, source/request/receipt/dependency mutations, conditional stacks, arbitrary
inputs, dirty inputs, phases and timeouts. The synthetic campaign records its
serial randomized schedule, repetitions, generation/write/hash, first and repeated
full scans, replay, logical bytes, disk and cumulative RSS. OS caches are not
controlled. CI retains raw results as artifacts. These are development fixtures;
no real-circuit or comparative performance claim follows from them.
