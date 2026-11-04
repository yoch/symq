# Streaming Kickmix hybrid windows — source-bound research interface

**Scope:** strict textual `.kmx` only. SymQ's Kickmix parser does **not** decode
binary `.kmb` files. Export a trusted **text** representation with a separately
pinned converter if the upstream source is binary. Never silently reinterpret
unsupported instructions (`R`, `BIT_*`, arbitrary `Z_POW`, condition stacks, or
other unrecognized gates). Physical lines are LF/CRLF-delimited; a line containing
any other separator recognized by Python `str.splitlines` (CR, VT, FF, NEL,
U+2028, ...) is refused so that line numbers match `symq.kickmix.load_kmx`.
This helper cannot establish correctness of the
original binary file or the binary-to-text conversion.

## Extract an operation range

This helper streams the complete `.kmx` input through the existing strict
parser, computes its exact raw-byte SHA-256, and retains only the selected
operations plus the latest classical measurement write per bit. The operation
range is **half-open and zero-based**, not physical line numbering: metadata
and comments do not count as operations.

```bash
sha256sum exported.kmx
symq kmx-window exported.kmx --start-op 1280 --stop-op 1300 \
    --expected-source-sha256 "$(sha256sum exported.kmx | cut -d' ' -f1)" \
    > selected-window.json
```

A returned `symq_kmx_window` JSON object contains the complete-file identity,
the total number of source operations, the physical input line span and line
numbers of the selected operations, and a `hybrid_fragment` expressed on a
compact local wire space with a complete `global_wires` map.

Classically conditioned `X/CX/CCX/SWAP/CSWAP ... if bN` may be
represented **exactly as conditioned `HOp` instructions** in the hybrid
fragment, subject to the full-file grammar and prefix classical dependency
checks. This is intentional: the narrower
`symq.kickmix.parse_kmx(...).to_circuit()` and
`.to_phase_program()` lowerings cannot express arbitrary measurement-based
conditions and **correctly refuse** them. A successful hybrid *extraction*
does not constitute a channel equivalence, a proved classical input or an
authorized contextual rewrite.

The fragment retains the exact **global classical slot names** (e.g. `b7`);
an input read from before the selected window is a declared **arbitrary
classical input**. Its last source HMR operation and physical line are
recorded. Reusing `b7` for a different measurement event changes this
binding. An undefined classical read, malformed instruction anywhere in the
file or a requested span beyond EOF is rejected, not silently ignored.

The document is always `advisory_only=true`, `proved=false`,
`candidate_authorized=false`. It is an exact structural extraction, **not** a
full-circuit rewrite, a proof of coherent quantum equivalence, a clean-ancilla
proof, an outcome-independent phase proof, or even a source certificate for
a binary `.kmb` file.

## Independent source pin and replay

```text
from symq.labs.kmx_window import extract_kmx_window, verify_kmx_window

record = extract_kmx_window("exported.kmx", start_op=1280, stop_op=1300)
fragment = verify_kmx_window(
    "exported.kmx", record,
    expected_source_sha256="..."  # exact 64-character digest pinned independently
)
```

`verify_kmx_window` rereads/reparses the entire file, checks the **caller-pinned**
SHA-256, all span/line/wire/slot metadata and the complete fragment. Simply
trusting the digest inside the record would authenticate nothing.

A later *separate* proof may use the fragment in a
`channel_composition.ChannelSlot` under explicit global prefix, frame,
outcome-liveness and suffix contracts. It must prove any clean wire and
classical-input assumptions at the actual cut. A hybrid local proof is
bounded to its named channel/instrument theorem and does not prove an
arbitrarily large global dynamic circuit.

## Failure and resource behavior

Input `.kmx` is read incrementally; one physical line is bounded, only the
selected window and last measurement writes are stored (memory is not
constant in the number of distinct classical slots). Current caps: file
512 MB, source operations 10 million, selected operations 20,000,
selected wires 256 and distinct classical bits 100,000. These are
**extraction caps**, not verifier width/event or proof-complexity guarantees.
The downstream coherent local checker has much smaller theorem-specific caps.

The CLI returns 0 for `extracted`, 2 for a resource-bound `inconclusive`
or explicitly unsupported binary/grammar, and 3 for malformed input,
an invalid span or a stale source pin. None represents a proof verdict.

The public source is never copied into the output record. Avoid exporting
private `.kmx` text, absolute paths or fixtures into this public repository.
See [contextual rewrites](rewrite.md) and
[local quantum composition](experimental-composition.md) for distinct proof
contracts and their boundaries.
