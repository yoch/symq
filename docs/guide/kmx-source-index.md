# Reusable strict KMX source index

`symq.labs.kmx_source_index` builds a private disk index once, then extracts
classical windows and backward dependency cones without rereading the entire
source. It is an opt-in research API and accepts **unconditional X/CX/CCX**
plus the metadata/comments already admitted by the strict KMX parser.

The entire source must fit this grammar. HMR, phase operations, conditional
operations, SWAP/CSWAP, resets and unknown instructions are refused even outside
the selected window. This first index intentionally avoids a theorem about
omitted measurements, phases, classical conditions or multi-target operations.
The existing [KMX hybrid window reader](kickmix-windows.md) and
[KMB binary reader](kmb-binary-windows.md) remain separate, broader extractors.

## Build once, query repeatedly

```python
from symq.labs.kmx_source_index import build_kmx_index

# Pin from a separately trusted manifest, not from the extraction receipt.
source_sha256 = "...64 lowercase hex characters..."
with build_kmx_index("source.kmx", expected_source_sha256=source_sha256) as index:
    window = index.window(
        start_op=10_500, stop_op=10_540,
        expected_source_sha256=source_sha256,
    )
    cone = index.cone(
        stop_op=10_540, observed_wires=(12, 31),
        expected_source_sha256=source_sha256,
    )
    checked = index.verify_cone(
        cone, stop_op=10_540, observed_wires=(12, 31),
        expected_source_sha256=source_sha256,
    )
    # checked is a local Circuit; cone['global_wires'] is its complete map.
```

Construction opens a regular source file without blocking on a FIFO, copies
it into an owned temporary snapshot and hashes those exact copied bytes. The
independent SHA-256 must match before parsing. Concurrent changes to the
original path cannot alter the private image subsequently indexed or queried.
Copying does not promise an atomic instant in a changing original file; the
digest identifies the complete snapshot actually obtained.

The parser then streams over that private image. Operations, physical source
positions and previous writers are inserted into SQLite on disk. Memory holds
the last writer per distinct wire, one bounded source line and SQLite's cache;
it does not hold every source operation as a Python object. An index on
`(wire, operation)` locates the last writer before an arbitrary cut.

The returned handle owns its snapshot and read-only database in a private
temporary directory. Use a context manager or call `close()`. Closed handles
refuse queries. The original source can be removed after a successful build
without affecting the owned snapshot. Rebuilding a changed source under an
old SHA pin fails.

**Reuse lasts for the issued handle's lifetime and creating thread.** There is
no API that opens an arbitrary SQLite database or reconstructs a handle from
JSON. A serialized manifest is untrusted and cannot replace a full build.
This is a deliberate boundary for the first version: persistent cross-process
reuse would need its own index-validation protocol. Private Python attributes
are not a sandbox against hostile code inside the same interpreter.

## Coordinates and identity

| Receipt field | Meaning |
| --- | --- |
| `source.source_file_sha256` | Digest of all raw source-file bytes, including metadata and comments |
| `source.index_sha256` | Deterministic identity of the format, complete logical records and source metadata |
| `op_span` | Zero-based, half-open **semantic KMX operation** interval; metadata/comments do not count |
| `gate_indices` | Absolute semantic operation index of each selected gate |
| `op_lines` | One-based physical LF/CRLF line numbers |
| `byte_spans` | Zero-based, half-open raw byte positions, including line endings |
| `global_wires` | Complete sorted local-to-global map for the returned circuit |
| `dependencies` | Previous writer operation for each gate input, in wire order; `-1` means source input |
| `boundary_predecessors` | Last source writer before `start_op`, for each mapped wire |

Only LF and CRLF are accepted as line separators. Unicode line separators,
vertical tab, form feed and bare CR are refused, so an instruction cannot hide
in a comment while changing physical-line coordinates. The logical index
digest is independent of SQLite's physical file layout; it is an identity,
not a certificate that an externally supplied index is correct.

## Exact backward dependency closure

For each selected output, the index finds its last writer before `stop_op`.
Every retained X/CX/CCX reads its old target and controls. The cone follows
the recorded previous writer of **each** input recursively, stopping at
`start_op`. This uses versions of wires at their actual reads: a later write
to a control is not accidentally substituted for the earlier value.

The selected operations are returned in original order. For every assignment
at `start_op`, the cone agrees with the original interval on the requested
output wires. Other mapped local outputs may differ; this is not permission
to replace the source interval by the cone. A contiguous window, by contrast,
retains every operation in its interval.

An unwritten wire below the inferred global width is an arbitrary identity
input. A zero-length cone can therefore be meaningful, even though windows
must contain at least one operation. Initial ancilla cleanliness is never
inferred from wire numbering, lack of a writer, metadata or `-1` predecessors.

The receipt explicitly has `boundary_inputs="arbitrary"`, `proved=false`,
`advisory_only=true` and `candidate_authorized=false`. A previous-writer
identity describes context; it does not prove that writer prepares zero or
establishes a relation. Proving a cut predicate, prepared quantum support,
phase correction, resource restoration or global substitution remains a
separate obligation. Treating a returned window as a new source loses the
incoming context unless that context is proved and composed explicitly.

## Receipt replay and work bounds

`verify_window` and `verify_cone` require the caller's expected source pin and
query coordinates. They re-extract from the owned snapshot and compare every
receipt field with strict scalar types. Cone replay traverses the dependency
closure again, including source positions, map and boundary predecessors; a
matching hash of the selected circuit alone cannot pass it. Each retained
operation is re-read and parsed from the private source bytes as an additional
consistency check. The returned `Circuit` comes from the fresh extraction.

Queries expose `work.sql_queries`, `work.result_rows`,
`work.dependency_visits` and `work.read_bytes`. Every SQL query and returned
row, pending dependency visit and selected source byte is charged. SQL progress
callbacks and Python loops share the deadline. A query reads no original
source path and does not scan unselected source lines.

| Default construction cap | Value |
| --- | ---: |
| Private source snapshot | 2 GiB |
| Main SQLite index file | 4 GiB |
| Source operations | 100,000,000 |
| Physical line | 1,000,000 bytes |
| Distinct wires | 100,000 |
| Largest global wire ID | 2³¹ − 1 |
| SQLite cache target | 8 MiB |
| Whole-call time | 180 seconds |

| Default per-query cap | Value |
| --- | ---: |
| Selected operations / wires | 20,000 / 256 |
| Dependency visits | 100,000 |
| SQL queries / returned rows | 100,000 / 100,000 |
| Selected source bytes read | 32 MiB |
| Whole-call time, including replay comparison | 30 seconds |

Use `IndexLimits`, `QueryLimits` and `Budget(max_seconds=...)` to tighten or
adjust these bounds. Explicit `Budget()` removes the time deadline. Generic
symbolic term/node/byte budgets are refused. The page-count limit bounds the
main SQLite file; source snapshot storage is bounded separately. Cache size
is a SQLite target and not a process-RSS promise. Deadlines are cooperative,
including SQL interruption, not separately killable worker deadlines.

Resource failures raise `ResourceLimitExceeded`: extraction is inconclusive
and no partial selection is returned. Unsupported source semantics raise
`UnsupportedOperation`; malformed inputs, stale pins and contradictory
receipts raise errors. SQLite's full-storage error can mean the configured
page cap or exhausted filesystem space; its diagnostic does not pretend to
measure a process-memory or disk overshoot. A failed build removes partial
owned files and never issues a usable handle.

Construction copies and parses all source bytes once each and builds indexed
disk records; SQLite maintenance is additional work. Later queries depend on
the requested window or visited dependency cone and indexed writer lookups.
This changes the repeated-query cost structure; it does **not** establish a
measured speedup, a 56-million-operation qualification or support for arbitrary
large hybrid circuits. A cone can still cover the whole relevant prefix and
hit a resource limit.

## Reproduce the bounded qualification

```bash
python -m pytest -q tests/test_kmx_source_index.py tests/test_kmx_window.py
python -m benchmarks.kmx_source_index --output /tmp/kmx-index.json --repetitions 3
```

Tests exhaustively compare windows and cones against an independent scalar
interpreter on seeded small sources. Adversarial cases include missing writer
links, changed coordinates/map, forged manifests, changed/deleted original
sources, unsupported operations outside the selection, strict line grammar,
closed handles, FIFO refusal and every configured resource cap. One synthetic
source exceeds 2 MB and contains 80,001 operations; repeated queries read only
the retained CCX line after the original path has been deleted.

The harness records build costs separately from repeated queries, source and
code identities, environment/SQLite versions, wall/CPU times, disk sizes,
cumulative process-peak RSS, work counters and all failure outcomes. Its
fixtures are original synthetic development data under the repository MIT
license, not private qant circuits or untouched holdout evidence. Raw results
belong in CI artifacts.
