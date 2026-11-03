# Kickmix binary v2 source-bound hybrid windows (research)

This is a **research-only source extractor** in `symq.labs.kmb_window`,
not a rewrite checker. It accepts native binary `.kmb` v2 directly:
the file has a 104-byte little-endian header and an ordered series of
struct-of-arrays packets. The decoder uses a **read-only mmap**, validates
the entire packet layout, operation types, counts and qubit/bit identities,
and retains only the requested window's operations and bounded classical
prefix metadata.

**Official source of the format:** Qualtran Developers / Google LLC,
Apache-2.0, [binary format specification](https://github.com/quantumlib/Qualtran/blob/9a0c11a4ee7697c082fbf8f2e1e8bf4a71fcb453/docs/kickmix/kickmix_binary_format.md),
upstream Git blob `debcf51c10d4840fc268f5452686976e96699c40`.
The repository-owned test corpus includes the official documented 351-byte
three-qubit-incrementer fixture, with attribution.

## Usage and source identity

```bash
sha256sum full-circuit.kmb
symq kmb-window full-circuit.kmb \
    --start-op 10500 --stop-op 10540 \
    --expected-source-sha256 <independently-pinned-64-character-hex> \
    --max-seconds 180 > window.json
```

```text
from symq.labs.kmb_window import extract_kmb_window, verify_kmb_window

report = extract_kmb_window("full-circuit.kmb", start_op=10500, stop_op=10540)
fragment = verify_kmb_window(
    "full-circuit.kmb", report,
    expected_source_sha256="<independent SHA-256 of the actual binary file>",
)
```

The operation span is **half-open** and counts raw KMB v2 operation-type
bytes, **including metadata/control operations**. No physical line numbers
exist in this format: the record includes each selected operation's absolute
type-byte offset instead. All file bytes, packet order and counters are
checked. Exact global wire IDs are compacted into the fragment with a
recorded complete local-to-global map.

Classical conditions read before their first write **inside the window**
become arbitrary classical inputs to the fragment. The last definite
prefix writer's operation index and kind are recorded. If the binary
source reads a classical bit before any in-file write, the record explicitly
marks SOURCE_INITIAL_UNKNOWN and a null predecessor: it is an **unproved
external classical input**, never an assumed zero. Ambiguous conditional
writers, underflow/unbalanced PUSH_CONDITION stacks and a stack active over
the selected window are refused.
Reused HMR slots are not assumed to identify the same measurement event.

Window support covers X/CX/CCX/SWAP/CSWAP, Z/CZ/CCZ/NEG,
unconditional **genuine** reset R, HMR, BIT_STORE0/1 and BIT_INVERT with
their explicitly supported classical conditions. The broader KMB source
may contain Z_POW, debug or other valid instructions **outside** the
selected window; these never silently become an accepted local HOp.
A selected Z_POW, condition-stack command, debug instruction,
conditional HMR/reset or conditional BIT_STORE is refused.

## Trust and resource boundary

This does not establish the validity of any **global** quantum substitution,
source-to-source compiler equivalence, clean ancilla, affine support or
instrument equivalence. It cannot certify the correctness of the entire
source circuit simply by matching the file digest. A KMB byte-string,
its semantic instruction sequence, the selected HybridFragment and the
actual global placement are separate objects with different proof obligations.

The record is marked `advisory_only=true`, `proved=false` and
`candidate_authorized=false`. It can only be fed to a separately bounded
local channel/instrument substitution checker with a proved prefix
support/frame and correct classical liveness.

Source-pinning requires the expected SHA-256 from an **independent**
caller; the bundle's own digest is not sufficient. The scanner hashes
the full mapped file before and after validation and refuses a file whose
size or digest differs at the end. This is **not** an atomic snapshot: a
concurrent writer that modifies bytes during the scan and restores them
before the second hash is not detected (the record then carries the pinned
digest but content that was never in the pinned file), and a concurrent
truncation can terminate the process with SIGBUS instead of producing a
refusal. For adversarial provenance, prepare an immutable file snapshot
(e.g. a private copy you own) before using the extractor or verifier.

Default caps: 8 GB mapped file, 500 million operations, 20,000 selected
instructions, 256 selected wires, 100,000 distinct classical slots,
100,000 registers, 5 million register entries and 180 seconds. The mmap
does not copy the entire binary into a Python bytes object. The validation
pass still takes **O(total operations)** time and has not yet been
performance-qualified on multi-GB real files. Outcome statuses:
`extracted` (not proved), `unsupported`, `inconclusive`, or `invalid`.

The independent Qualtran KMB-v2 fixture and malformed-packet tests establish
format handling only; they do not license claiming a real DQI/HMR loader has
been quantum-verified. See the separate [text KMX extractor](kickmix-windows.md)
and the [contextual rewrite proof contract](rewrite.md).
