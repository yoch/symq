# Choosing an engine and a budget (research checks)

This page is for the research checks of `symq.labs` that decide table loaders and clean
ancillas, and for the SAT miter they are often combined with. They carry no API promise
([stability policy](../stability.md)). For the stable `verify` and its engines, see
[the backends](backends.md); for the meaning of each `Budget` field in the stable core, see
[resources](resources.md).

## Which check answers which question

| Question | Check | Engines |
| --- | --- | --- |
| Does a loader XOR a table into its targets, for every legal address, with every record forgotten? (version-1 contract, up to 12 address and 16 target bits) | `anchored_kraus.verify` (reference), `anchored_stream.verify_stream` | ANF (`backend="anf"`), Boolean DAG with exact SAT queries (`backend="sat"`) |
| The same, with up to 16 address bits and targets in an affine space of up to 256 bits | `affine_table.verify_affine_table` ([lab note](../labs/affine-target-tables.md)) | ANF, SAT |
| The same, for a shared table with a predicate address domain | `shared_table.verify_shared_table` ([guide](shared-affine-tables.md)) | compiled to the affine check; ANF, SAT |
| Does an ancilla end at \|0> for every data input? | `backward_ancilla.check_clean_ancilla` ([guide](backward-ancilla.md)): Pauli error observables, a receipt that `replay_clean_ancilla` re-proves | Pauli observables |
| The same question | `shift_diagonal_ancilla.check_shift_diagonal` ([guide](shift-diagonal-ancilla.md)): Boolean-first, then shift-diagonal polynomials; no receipt | Boolean ANF, rational polynomials |
| The same, with a target that starts dirty or slots set before the program | `ancilla_inputs.with_inputs`, then either checker | as above |
| Are two classical reversible circuits equal on every input (or under a contract)? | `symq.sat.check_sat_equivalence` ([guide](sat.md)) | SAT |

Every check is exact: `equivalent`, `not_proved`, `clean`, `not_clean` and `different` are
decisions, and the negative ones come with a witness (replayed on the source by the table and
SAT checks, computed exactly by the ancilla checkers). Exhaustion is `inconclusive` and never a
verdict. A table check given a well-formed contract beyond the sizes it supports returns
`unsupported`; the ancilla checkers report their structural caps (width, gate arity, ...) as
`inconclusive`. Malformed input raises.

## What each limit counts

The same name does not count the same thing in every engine.

| Limit | Table checks, ANF | Table checks, SAT | `check_clean_ancilla` | `check_shift_diagonal` | `check_sat_equivalence` |
| --- | --- | --- | --- | --- | --- |
| `max_terms` (keyword or `Budget`) | monomials of one polynomial (default 100,000) | generated CNF clauses (same default) | Pauli terms of one observable or gate expansion (`terms`, `gate_terms`; 4,096 when no budget is given) | terms of one Boolean or rational polynomial (same default) | not applied, listed in `ignored_limits` |
| `max_products` | term-pair products of the whole call (default 1,000,000) | not used | `AncillaLimits.max_products`: elementary Pauli products (default 1,000,000) | `AncillaLimits.max_products`: polynomial products | not used |
| `max_graph_nodes`, `max_clauses` | not used | Boolean DAG nodes (100,000), CNF clauses (500,000) | not used | not used | not used |
| `max_operations`, `max_json_items` | source operations (100,000), JSON values read (1,000,000) | same | `AncillaLimits.max_operations` (10,000) | same | not used |
| `max_nodes`, `max_bytes` | refused (`ValueError`) | refused | refused | refused | not applied, listed in `ignored_limits` |
| deadline: `max_seconds`, `absolute_deadline`, an enclosing `VerificationSession` | cooperative; default 10 s (30 s for the whole shared-table call) | cooperative, and the solver is interrupted | cooperative | cooperative | polled while encoding, solver interrupted |

The tightest deadline applies, whichever sets it. No limit on this page bounds the memory of
the process: for that, see [hard limits](#hard-limits-run-the-check-in-another-process) below.

## Reading an inconclusive result

An `inconclusive` result names the limit it reached and the limits of the call (the fields
are described in `symq.labs.resource_report`):

```python
from symq.experimental.hybrid import HybridProgram
from symq.labs.backward_ancilla import AncillaLimits, check_clean_ancilla

program = HybridProgram(2, 1).ccx(0, 1, 2).ccx(0, 1, 2)
stopped = check_clean_ancilla(program, 2, limits=AncillaLimits(max_products=10))
assert stopped.status == "inconclusive" and stopped.certificate is None
assert stopped.resource == "pauli_products" and stopped.limit == 10
assert stopped.observed > 10 and stopped.pauli_products == stopped.observed
assert "AncillaLimits.max_products" in stopped.hint
assert dict(stopped.limits)["max_products"] == 10
assert check_clean_ancilla(program, 2).clean  # with the default limits it concludes
```

`observed` is where the call stopped, not the size of a proof: a larger limit may let it
conclude, or may not. Raise one limit at a time, and keep a deadline.

## Two synthetic programs, two engines

Neither ancilla checker dominates the other. With the same 64-term budget, on two small
synthetic programs, each concludes where the other stops:

```python
from symq.experimental.hybrid import HybridProgram
from symq.labs.backward_ancilla import check_clean_ancilla
from symq.labs.shift_diagonal_ancilla import check_shift_diagonal
from symq.resources import Budget

budget = Budget(max_terms=64)

# Compute and uncompute a 6-control AND. The Boolean-first engine never holds more than
# 2 terms; the observable engine must expand the gate into 2**7 Pauli terms.
uncompute = HybridProgram(6, 1)
uncompute.mcx(*range(7)).mcx(*range(7))
boolean = check_shift_diagonal(uncompute, 6, budget=budget)
assert boolean.status == "clean" and boolean.peak_terms == 2
pauli = check_clean_ancilla(uncompute, 6, budget=budget)
assert pauli.status == "inconclusive" and (pauli.resource, pauli.observed) == ("gate_terms", 128)

# The parity of 8 wires, then a flip conditioned on a measured coin. The observable engine
# holds at most 4 Pauli terms; the other needs a shift-diagonal polynomial of 513 terms.
parity = HybridProgram(9, 1).hmr(0, "b0")
for wire in range(1, 9):
    parity.cx(wire, 9)
parity.x(9, condition="b0")
assert check_clean_ancilla(parity, 9, budget=budget).status == "not_clean"
assert check_shift_diagonal(parity, 9, budget=budget).status == "inconclusive"
unbounded = check_shift_diagonal(parity, 9, budget=Budget(max_terms=10**6))
assert unbounded.status == "not_clean" and unbounded.peak_terms == 513
```

These are illustrations of where each representation grows, not a benchmark: no timing or
ranking follows from them. The qualifications of both checkers (see their guides) keep such
adverse cases on purpose.

## Hard limits: run the check in another process

Engine limits are cooperative and count explicit data. For a hard bound on wall time, CPU
time and address space, run the check in a spawned worker with
`symq.experimental.execution.run_isolated`. `symq.labs.isolated_jobs` provides the table
and ancilla checks as jobs it accepts: the source, contract or program as JSON documents
(`program_to_dict`), `Budget` and `AncillaLimits` as they are, and a JSON value back.

```python
import sys

from symq.experimental.execution import HardLimits, run_isolated
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.isolated_jobs import shift_diagonal_job
from symq.resources import Budget

linux = sys.platform.startswith("linux")  # see below for other systems
program = HybridProgram(2, 1).cx(0, 2).cx(1, 2)
outcome = run_isolated(
    shift_diagonal_job, program_to_dict(program), 2,
    kwargs={"budget": Budget(max_seconds=20, max_terms=4096)},
    limits=HardLimits(wall_seconds=30, memory_bytes=2 * 1024**3 if linux else None,
                      cpu_seconds=25 if linux else None),
)
assert outcome.status == "completed"
assert outcome.value["status"] == "not_clean" and outcome.value["probability"] == "1"
print(outcome.wall_seconds, outcome.cpu_seconds, outcome.peak_rss_bytes)
```

- `outcome.status` describes the execution. A worker stopped by a limit gives `inconclusive`
  or `error` and no value: never a verdict, never "different".
- A completed job can itself be `inconclusive`; its report is in `outcome.value`.
- The budget inside the job is a duration measured in the worker, from when the job starts:
  after the worker has started and imported SymQ. Keep `max_seconds` below `wall_seconds` with
  a margin for that start, as above, so that a check that runs out of time returns its own
  report instead of being killed without one. A job refuses an absolute deadline, which is a
  clock reading of the calling process; inside a session, derive the duration from
  `session.subprocess_budget()` and leave the same margin. An absolute deadline that a check
  computes for itself inside the worker is dropped from the `limits` of its report.
- `memory_bytes` (2 GiB by default) limits the address space of the worker, interpreter
  included, and `cpu_seconds` its CPU time, through resource limits that SymQ relies on only
  on Linux. On macOS the address-space limit may be refused or not enforced: pass
  `memory_bytes=None` there. On Windows any memory or CPU limit, the default one included,
  makes the call `unsupported`: pass `memory_bytes=None`. Wall time is enforced everywhere,
  from the parent.
- The function and its arguments are trusted: this is resource isolation, not a sandbox. The
  [resources guide](resources.md#typed-worker-results) describes the result protocol.

## What a result does not say

- `clean` is a statement about the final value of one wire. It is not equality of the data
  channel, and it does not authorise removing a reset, a wire or a correction.
- A table verdict is conditional on the declared contract. `verify_shared_table` proves the
  loader for the declared address support only (`source_preparation_scope`), and reports
  `actual_context_preparation_proved=False`: that the caller prepares that support is a separate
  proof (`prove_shared_table_preparation`).
- No result here is a portable certificate (`portable_certificate` is false); the ancilla
  receipt is data that `replay_clean_ancilla` re-proves from the source.
- A green CI run, a semantic verdict, a reproducible measurement and a performance comparison
  are four separate claims; this page makes none of the last.
