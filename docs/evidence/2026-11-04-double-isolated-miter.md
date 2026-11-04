# Stage 3: two independently resource-limited processes for SAT proofs

**Scope:** [#193](https://github.com/yoch/symq/issues/193), stacked on
[#195](https://github.com/yoch/symq/pull/195) (bounded CNF) and
[#199](https://github.com/yoch/symq/pull/199) (isolated producer).
**Base at authoring:** #199 \`30f541de77f4d902e7bc30f7b2b6120c0b0f6db8\`.
**Status:** research-only, no main/default-engine/API mutation.

## Purpose and model

Previously, a Linux producer was isolated under `RLIMIT_AS` / `RLIMIT_CPU`,
but the **parent** still executed the source-to-CNF encoder and RUP proof
checker after receiving an untrusted proof. That allowed a bounded proof
producer to trigger expensive in-parent parsing, encoding and proof checking.

`isolated_miter_supervisor.prove_separately_verified_miter_request` now
makes the **top-level parent a transport-only supervisor**:

1. Validate exact input bytes/length, independent lowercase source SHA,
   explicit positive resource parameters, an outer time budget and
   inherited `VerificationSession` policy; refuse unsupported inherited
   node/term/byte limits. The parent does **not** allocate a Circuit.
2. Write the bounded original request bytes to an internal temporary file.
   Launch the existing *untrusted* SAT proof producer with a fixed
   `python -I -c` bootstrap which installs Linux `RLIMIT_AS` and
   `RLIMIT_CPU` before importing SymQ. Read bounded stdout/stderr under
   a monotonic parent watchdog. Kill/reap the process group even on a
   seemingly valid proposal.
3. Never accept the producer's `proposal` as evidence. Only if the exact
   bounded response schema is valid, put those bytes in a second internal
   file, and launch a **separate trusted verifier** with another fixed
   bootstrap, its own OS address-space and CPU limits, and the *remaining*
   parent wall budget.
4. The verifier independently reparses the **original request**, rebuilds
   the normalized source-bound SAT-miter CNF and checks the positive-hint
   RUP trace using the solver-free `check_classical_miter_proof`. The
   expected source SHA is inherited **from the caller**, never from the
   producer. The verifier never runs the untrusted SAT solver.
5. The parent only accepts a closed `verified` frame from this
   fixed-code trusted verifier, with independently matching source SHA,
   after both worker processes exited and their process groups were
   cleaned up. Failure/timeout/OOM/oversize/forgery always produces no
   positive theorem. `controlled_use_authorized` remains false.

## Exact security boundary and remaining trusted components

The verifier process code is **trusted**, the proof producer is not.
The Python source→CNF encoder, the positive-hint RUP checker and the
canonical source serializer are still trusted software, not proved
equivalent to arbitrary Python implementations in Lean. `RLIMIT_AS`
bounds Linux *virtual address space*, not RSS; `RLIMIT_CPU` bounds
per-process CPU usage; the parent enforces the same monotonic deadline
over both workers but cleanup can add bounded extra time.
Both subprocesses may be reaped via process-group kill, yet arbitrary
Python code execution is **not sandboxed**: processes share the OS user,
files and installed interpreter, and could evade process groups or
tamper with same-UID resources if malicious code were actually executed.
The accepted threat model is untrusted **data** and an untrusted proof
result, not attacker-provided executable code or a compromised Python
installation.

The outer supervisor still handles bounded framing, subprocess
creation, temporary file writes and small JSON dictionaries. It has
no OS-enforced independent RSS cap, nor a durable cgroup-v2 unified
worker+parent memory cap. There is no request-independent machine
proof of source semantics. Consequently it is **not yet a secure,
general public untrusted-input service** and no stable API promise
or deployment authorization follows from this research.

## Adversarial qualification

`tests/test_isolated_miter_supervisor.py` checks:
- real two-CCX cancellation proof through Glucose in the first worker
  and fresh independent source/CNF/RUP checking in the second;
- explicit injection of a failing in-parent parser/RUP checker without
  disrupting the true separate verifier, proving the normal parent no
  longer imports or calls the heavy proof path;
- satisfiable miter and wrong independent source SHA;
- forged producer proof response, worker stdout floods, timeout of the
  *verifier*, and verifier virtual-address-space exhaustion;
- source byte cap, closed framing, repeated keys, inherited unsupported
  resource budgets, Linux-only memory-policy refusal on other OSes;
- fatal fail-closed behavior when process-group cleanup fails.

These tests do not automatically establish a universal security
property. A security review must separately attack inherited
file descriptors, process groups with descendants, signal handling,
temporary-file mutation, both RLIMIT policy failures, proof-size and
JSON parse complexity, CPU/RSS peaks and max wall overrun.
A dedicated Linux GitHub workflow requires SAT to be installed, runs
all new positive/negative cases without skipping them, and repeats
the source-bound proof and CNF budget regressions.

## Merge criteria

The new Draft PR is stacked on #199, not on `main`. Before any merge,
re-read its current HEAD, the upstream #195/#199 heads, base tree,
full diff and review threads; require 14/14 CI + focused Linux run
on the **exact proposed tree**, source-level security audit and
verified wheel/sdist behavior. If the stack is eventually approved,
prefer one reviewable, requalified integration commit from the exact
then-current `main`; no success on earlier HEADs validates a changed
tree.

Keep issue #193 open until the maintainers agree that the complete
untrusted-data resource model is covered. No release, default SAT
change, remote-input service or stable API promotion is authorized.


## Group cleanup and supervisor deadline adversaries

Additional research regressions require refusal when a verifier spawns a
same-process-group descendant holding the output pipe open, when its
stdout grows beyond the transport cap, and when a verifier emits an
apparently well-formed positive result but exits nonzero. An enclosing
`VerificationSession` with a shorter deadline must win over the
per-request wall argument; the existing session may itself raise at
context exit after its deadline. These are tests of **fail closed**,
not proof of safety under arbitrary hostile-code execution.


## Process-group identity lifetime

After a successful worker exit, `Popen.wait()` would **reap** the
leader and allow its PID to be reused before the supervisor's
unconditional `killpg` of the group. The two-stage supervisor instead
uses Linux `waitid(P_PID, ..., WEXITED|WNOWAIT|WNOHANG)` to observe
exit **without reaping the leader**. The group signal is sent while
the leader PID still exists; only afterwards does `Popen.wait()` reap
it. This closes the normal PID/PGID reuse window between successful
worker exit and group cleanup. A Linux runtime without the required
`waitid` / `WNOWAIT` primitives is explicitly rejected as `unsupported`
before spawning any worker. The group cleanup path also attempts
to reap the leader if signalling fails, and refuses any provisional
positive verdict when cleanup remains ambiguous.

The corresponding regression inspects `Popen.returncode` and a
second `waitid(WNOWAIT)` at the exact moment of the group signal,
requiring the leader to remain unreaped. This does not prevent
code-execution-level process-group escape using `setsid` by a hostile
child, which remains outside the trust model.
