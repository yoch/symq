# Verification deadlines and isolated execution

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
duration. The CLI and proof graph use this explicit boundary.

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
This is not a real-time operating-system guarantee. Trusted caller argument
serialization and process-creation system calls are not a sandbox for blocking
caller callbacks. The result protocol never invokes such callbacks in the parent.

This is resource isolation, not a security boundary for hostile worker code.
Workers retain the caller's filesystem and network permissions. Arbitrary
returned Python objects are deliberately unsupported. CPU and RSS metrics sample
the worker before response encoding; whole-call wall time includes IPC and
cleanup. These boundaries must remain separate in performance reports.
