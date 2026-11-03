# Stage 2 — isolated classical-miter proof producer (Linux research pilot)

**Issue:** [#193](https://github.com/yoch/symq/issues/193).
**Stacked dependency:** [#195](https://github.com/yoch/symq/pull/195),
HEAD `78b6f0c5dd2382c30f86048d6e43bb9d9e1a96ef` at construction.
**No changes to default SAT or stable APIs.**

## Trust boundary

The child process is **not trusted for positive evidence**. A Linux parent
accepts only byte-limited, canonical JSON containing two classical reversible
circuits and a closed subset of `symq.sat.Contract`. The source fingerprint
must be supplied independently by the caller, not taken from the child
or request itself. The worker never receives a code path, executable name,
module selector or arbitrary output filename from the request.

The child is launched as a fresh isolated interpreter (`python -I -c`)
with a **fixed bootstrap** which installs Linux `RLIMIT_AS` for its virtual
address space and `RLIMIT_CPU` for its CPU time before importing the
SymQ worker module. The parent starts it in a new session/process group.
The parent observes a `time.monotonic()` wall deadline, reads stdout and
stderr nonblockingly with explicit byte ceilings, and kills/reaps the
worker group on timeout, oversized output, malformed response or failed
exit. A failed cleanup cannot authorize a proof.

The child may supply a positive-hint RUP *proposal* only. The parent then
reparses the **original bounded request bytes**, freezes the source,
regenerates the canonical normalized SAT CNF and checks the actual RUP trace
using `check_classical_miter_proof` and the independent expected source pin.
No worker-supplied `proved` or hash is proof authority. Even a valid
result has `controlled_use_authorized = False` and carries only the
restricted *global classical miter* theorem, not local-cut or quantum-channel
equivalence.

The worker and parent use the same source grammar and explicit proof limits.
Contract assumptions outside the documented subset, invalid/duplicate
JSON keys, oversized byte streams and too many gates are refused before
constructing a circuit. Qiskit, other external compilers and private
resources are not imported.

## Concrete non-goals and caveats

This is **not a Python untrusted-code sandbox**. An attacker able to modify
the Python code, installed packages or interpreter is outside the threat
model. A Linux `RLIMIT_AS` bound is on *virtual address space*, not measured
RSS or a cgroup memory usage guarantee. The parent has a hard watchdog for
the **child process**, not for its own JSON parsing, CNF reconstruction
or RUP verification; these use bounded input sizes and cooperative limits.
The combined API therefore must **not** be advertised as a strict
end-to-end wall-time or process-RSS guarantee for arbitrary remote data.

The test envelope is Linux; other OSes return `unsupported` when a
Linux `RLIMIT_AS` guarantee cannot be established. A macOS runner can
execute parser/refusal regressions but is not used to claim memory
confinement. Integration into any remote-input-facing service still
requires a separately reviewed, OS-enforced parent verification boundary,
hard-limit benchmarks, process-group cleanup fault injection and
independent security review. Issue #193 remains open.

## Qualification tests and decision

The research test module includes:
- a real optional Glucose proof proposal checked again by the parent
  after source-bound CNF reconstruction;
- a satisfiable miter and wrong externally supplied source pin;
- malformed, noncanonical, duplicated-key or oversized requests;
- an intentionally sleeping child killed on deadline;
- a stdout-flooding child cut off at the output byte cap;
- a forged positive payload rejected by the parent RUP consumer;
- non-Linux refusal without a false resource guarantee.

The parent verifier must never grant an applicable candidate or a
general quantum theorem. The source/cost and solver limitations of
[#194](https://github.com/yoch/symq/pull/194) remain.

**Required before any merge:** exact-head main CI on Python 3.10–3.14,
Linux and macOS, wheel and sdist; a real Linux producer test that did
not skip; repeatable group kill/output caps; independent adverse audit
and full diff review. Parent memory, child memory, and time must be
reported separately. Research PR only; no merge, release or API
promotion is authorized by this document.


## Inherited parent-session budgets

The parent additionally initializes a local `Guard` at API entry. A live
`VerificationSession` deadline tightens the child's monotonic parent
deadline; inherited node/term/byte budgets are **refused** rather than
silently discarded, because this worker protocol cannot account for
them as process-wide memory or symbolic resources. The corresponding
regression exercises the inherited byte-budget refusal.

The Linux CI also injects a child that allocates above an OS
`RLIMIT_AS` cap: a memory failure and nonzero exit must return
`inconclusive`, never a fabricated positive result. This does not
replace an OS kernel-level independent audit of enforcement or a
parent-side hard memory boundary.
