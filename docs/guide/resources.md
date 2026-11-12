# Verification deadlines and isolated execution

## What each budget field bounds

| Field | Bounds | Enforced by |
| --- | --- | --- |
| `max_seconds` | wall-clock time of the whole call, from the guard's creation | every engine, cooperatively; SAT by polling during the encoding and the clause loading, then through a watchdog that interrupts the solver ([details](sat.md)) |
| `max_terms` | monomials of every wire value, XOR, product and explicit conversion | explicit, ZDD and `linear` backends (the native core checks every gate and operation), the phase reference |
| `max_nodes` | internal nodes of a ZDD unique table | Python and native ZDD backends |
| `max_bytes` | the native arrays of a native ZDD manager (nodes, unique table, cache) | native backends only; every other backend **refuses** a budget that sets it |

Exceeding any limit raises `ResourceLimitExceeded(resource, limit, observed)` or returns an
`inconclusive` verdict; nothing is approximated. A budget field that an engine cannot enforce is
refused rather than ignored, except in the low-level `check_sat_equivalence`, which documents that
only `max_seconds` applies. Cooperative deadlines and `max_bytes` are not operating-system limits:
for hard CPU, wall and address-space limits, run the work in an isolated subprocess (below).
`max_bytes` is not a process memory limit either: it counts only the native manager's node
arrays, unique table and operation cache. Temporary buffers of the C core, Python objects
(including exported ANFs) and the resident set size of the process are not counted.

`SymqError` is the base class of every SymQ exception; `ResourceLimitExceeded` additionally derives
from `RuntimeError` for compatibility.

## Deadlines and sessions

`Budget.max_seconds` is a duration relative to the creation of a guard. Every
nested guard intersects that duration with the active session's absolute
`perf_counter` deadline. `Guard.inherited_budget()` and
`VerificationSession.remaining_budget()` retain that absolute deadline for
same-process work; they never convert elapsed time into another relative limit.
Node and term limits are intersected independently. Exact deadline equality is
expiration. Public whole-call checks include witness replay and final cleanup.

Only `VerificationSession.subprocess_budget()` converts remaining time into a
fresh relative duration. A spawned interpreter has its own session; the parent
continues enforcing its original deadline across startup, receipt, decoding and
worker exit. An inherited absolute budget must not be used as a detached-worker
duration. An explicit orchestration session is intersected with any active
caller session; supplying another session cannot hide a tighter parent deadline.
The CLI and proof graph use this explicit boundary.

## Typed worker results

`run_isolated` accepts trusted, importable callables and trusted spawn-pickleable
arguments. Worker results cross a different boundary: the worker validates and
encodes a closed JSON language, and the parent uses `recv_bytes`, never
`recv`/pickle reconstruction. Returned custom objects, nonfinite numbers and
oversized results become nondecisive results.

The maximum encoded response is 1 MiB, with depth at most 64, at most 100,000
values and integer magnitudes of at most 4,096 bits. Dictionary keys are strings;
tuples normalize to JSON arrays. The response envelope is validated separately.
Receive and decode run in a daemon receiver under the caller's deadline. A
partial frame or a delayed decoder cannot block the caller or supply a late
proof. A receiver finishing after timeout cannot change the returned result.

`HardLimits.wall_seconds` is the admission deadline, including worker startup and
result handling. Expiration withdraws all results. Worker termination has a
separate cleanup grace of at most 0.2 seconds; OS scheduling can add latency.
On POSIX, concurrent child-status collection is synchronized per child. If a
collector is paused while cleanup expires, daemon cleanup preserves termination
requests and reaps the child when the collector resumes. The caller does not
extend its grace, and an unknown exit status cannot authorize a result.
This is not a real-time operating-system guarantee. Trusted caller argument
serialization and process-creation system calls are not a sandbox for blocking
caller callbacks. The result protocol never invokes such callbacks in the parent.

The research table and clean-ancilla checks are available as jobs for `run_isolated` in
`symq.labs.isolated_jobs`; [choosing an engine and a budget](engines-and-budgets.md) has a
recipe.

This is resource isolation, not a security boundary for hostile worker code.
Workers retain the caller's filesystem and network permissions. Arbitrary
returned Python objects are deliberately unsupported. CPU and RSS metrics sample
the worker before response encoding; whole-call wall time includes IPC and
cleanup. These boundaries must remain separate in performance reports.
