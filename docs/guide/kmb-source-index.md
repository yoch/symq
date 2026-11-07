# Strict classical KMB-v2 indexing (research)

`build_kmb_index` reuses the existing pinned-format KMB layout reader and the
owned SQLite dependency engine. `check_indexed_substitution` accepts its issued
handle; complete-source proof/replay selects the builder from the `.kmb` suffix.
This lot depends on the [origin composition rule](indexed-substitution.md).

The semantic fragment remains unconditional X/CX/CCX. INFO_TAG is inert metadata.
Every other opcode anywhere in the source is refused: SWAP/CSWAP, phase gates,
reset, HMR, classical writes, conditions, condition stacks, debug and unknown
operations. This is deliberately insufficient for general hybrid source files.
The first encountered unsupported instruction can refuse a pinned file before
the rest is decoded; such a refusal does not claim complete format validation.

Coordinates follow the existing KMB reader: zero-based **raw operations**,
including INFO_TAG. A cone's `gate_indices` contains retained raw positions;
metadata occupies positions but emits no gates. A complete window retains every
semantic instruction in its raw interval. A metadata-only window is refused.
The reduced local span counts emitted classical gates. Never transfer a KMX
semantic ordinal directly into a KMB raw ordinal.

The complete source is privately copied and hashed before parsing. The reused
reader validates exact v2 magic, canonical packet order/lengths, registers and
INFO_TAG strings. The builder checks whole-source opcode counts, operand arity,
distinctness/ranges and declared maxima before issuing a handle. Each query
rechecks opcode **and operand bytes** in the private struct-of-arrays snapshot.
Receipts keep opcode byte spans, operand-group ordinals and every operand byte
span; no fabricated physical text line numbers are returned. Versioned writer
links continue to include the previous target as well as all controls.

Returned metadata is detached, including nested packet-offset maps. Serialized
metadata/database files cannot reopen an index. The common limits and cleanup
policy match the KMX builder, including explicit source/disk/work/time bounds.
Query `read_bytes` charges opcode and operand reads before performing them.
`max_line_bytes` has no role in this binary format; header/register bounds are
those of the reused layout reader (100,000 registers, 5,000,000 entries).

```python
from symq.labs.kmb_source_index import build_kmb_index
from symq.resources import Budget

# Obtain source_pin independently of any untrusted receipt.
with build_kmb_index(path, expected_source_sha256=source_pin,
                     budget=Budget(max_seconds=30)) as index:
    selection = index.window(start_op=a, stop_op=b,
                             expected_source_sha256=source_pin)
    exact = index.verify_window(selection, start_op=a, stop_op=b,
                                expected_source_sha256=source_pin)
```

The source/request/dependency pin and fresh proof requirements are unchanged.
No binary conversion is inferred and no rewritten complete file is emitted.
There is no hybrid value, channel, measurement or phase theorem in this module.

```bash
SYMQ_TEST_REQUIRE=sat python -m pytest -q tests/test_kmb_source_index.py tests/test_kmb_window.py tests/test_kmx_source_index.py tests/test_indexed_substitution.py
```

The corpus includes the existing source-attributed public Qualtran binary
fixture, original synthetic SOA writers, complete scalar oracles, raw INFO_TAG
coordinates, changed operand/map/dependency receipts, closed handles, strict
resource failures, and unsupported instructions outside the chosen window.
No private fixture or production-size success is claimed.
