# Source-pinned classical cones and cut predicates

`symq.labs.classical_cone` connects an exact backward slice to a proof of a
known Boolean predicate at a particular source position. It is an opt-in
research API for the existing X/CX/CCX/MCX `Circuit` grammar. The source is an
already materialized circuit; this first version is not an indexed reader for
large KMB files and makes no throughput claim on a 56-million-operation input.

The useful distinction is between a sufficient *dependency cone* and a
sufficient *initial cut*. The cone preserves the selected outputs exactly.
A cut too close to the insertion point can still lose a preparation relation.
Its inputs remain arbitrary until an earlier part of the actual source
establishes that relation. A local violating assignment is not automatically
a reachable source input.

## Prove a predicate and use the existing substitution checker

```python
from symq import Circuit
from symq.labs.classical_transcript import Program, digest
from symq.labs.classical_cone import prove_cone_predicate, replay_cone_predicate
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.sat.assumptions import And, Eq, Var

source = Circuit(5).x(4).ccx(0, 1, 2).x(4).cx(2, 3)
# Obtain this pin from the separately trusted source in a real workflow.
source_pin = digest(Program.freeze(source))
initial = ((2, 0),)
predicate = Eq(Var("u.2"), And(Var("u.0"), Var("u.1")))

proof = prove_cone_predicate(
    source, at=3, start_op=2, predicate=predicate,
    initial_constants=initial, expected_source_sha256=source_pin,
)
assert proof.proved
assert [a.start_op for a in proof.attempts] == [2, 1, 0]

fresh = replay_cone_predicate(
    source, proof.to_dict(), at=3, predicate=predicate,
    initial_constants=initial, expected_source_sha256=source_pin,
)
assert fresh.proved
contract = SubstitutionContract(
    initial_constants=fresh.initial_constants,
    cut_assumption=fresh.cut_assumption(source, at=3),
)
replacement = Circuit(5).ccx(0, 1, 3)
rewrite = check_substitution(source, (3, 4), replacement, contract=contract)
assert rewrite.equivalent
```

The first two attempts have arbitrary cut inputs. Even the cone containing
the CCX cannot conclude `u.2 = u.0 AND u.1` if its target can be initially one.
Only the attempt reaching operation zero may use the declared initial zero.
The two changes to wire 4 are irrelevant to the predicate and disappear from
the final cone. The substitution checker still proves its own full prefix,
local equivalence and restoration obligations: the new API does not bypass
that checker or attach an authorized replacement to its result.

`start_op=0` is the default. A later start opts into a shorter first attempt;
`expand_cut=True` doubles its lookback until the source origin, subject to
limits. Set `expand_cut=False` to inspect a single proposed cut. Failure to
prove at that cut is `not_proved`, not a global counterexample.

## The exact cone theorem

For a source interval `[start_op, at)` and selected global output wires `O`,
walk the interval backwards with `O` live. Keep a gate exactly when its target
is live, then add its controls to the live set. A controlled-X reads its old
target, so the target stays live. Reverse the selected gate list and remap all
used wires with a complete, sorted, injective local-to-global map `W`.

For every assignment `y` to the global wires at `start_op`, the extracted
circuit on `y` restricted to `W` agrees with the original interval on `O`.
This follows by reverse induction: a dropped gate writes no currently needed
value; a retained gate brings in every value needed to compute its target.
The analysis is conservative and need not produce the smallest semantic cone.

**Only the requested outputs are preserved.** Another mapped wire can differ
at the end of the sliced program if a later write to it is irrelevant to the
requested outputs. It would be unsound to treat the slice as an equivalent
replacement for the whole source interval.

```python
from symq.labs.classical_cone import extract_classical_cone, verify_classical_cone

selection = extract_classical_cone(
    source, at=3, observed_wires=(0, 1, 2),
    expected_source_sha256=source_pin,
)
assert selection.outcome == "extracted"
rechecked = verify_classical_cone(
    source, selection.to_dict(), at=3, observed_wires=(0, 1, 2),
    expected_source_sha256=source_pin,
)
assert rechecked.outcome == "extracted"
```

The receipt pins the entire source's canonical IR digest, source width and
gate count, exact half-open interval, selected outputs, local-to-global map,
absolute source gate indices and local circuit. Verification reconstructs the
closure from the separately supplied source and compares every field with
strict scalar types. A changed suffix also changes the source identity.
An extraction has `predicate_proved=false` and `candidate_authorized=false`.

## Predicate theorem, domains and outcomes

Let `F[:at]` be the source prefix and `P(x)` the conjunction of the explicitly
supplied initial constants. A proved result establishes

\[
\forall x,\quad P(x) \Longrightarrow Q(F[:at](x)).
\]

`Q` uses the closed Boolean grammar `Const`, `Var`, `Not`, `And`, `Xor`, `Eq`
with canonical names `u.<global wire>` and must reference at least one wire.
The predicate is copied and bounded; no callback or arbitrary expression is
executed. Constants are unique `(wire, 0/1)` pairs, so this initial domain is
nonempty by construction. Every unspecified wire is arbitrary, including an
ancilla. General relational initial assumptions are not supported by this
first API; there is no `assumption` argument, and passing one raises `TypeError`.
The existing [cut-invariant learner](cut-invariants.md) remains the route for
discovery and its richer input-domain contract.

At an intermediate cut, all cone inputs are arbitrary. An UNSAT violation
query therefore proves a stronger property valid on every reachable cut
state. At source origin, the query applies only the initial constants on cone
wires; omitted constants are independent and cannot affect selected outputs.
A SAT witness is first checked by concrete cone execution. At origin it is
lifted to a complete legal source input, filling omitted constant wires, and
then replayed on the full actual prefix before any global refutation is issued.

| Outcome | Meaning | Usable cut assumption |
| --- | --- | --- |
| `proved` | Exact cone and SAT query establish the requested source predicate | Yes, through an issued or freshly replayed result |
| `not_proved` | An arbitrary intermediate-cut assignment violates it; reachability is unproved | No |
| `precondition_failed` | A complete legal source input was replayed and violates it | No |
| `inconclusive` | Deadline, allocation/work cap, or undecided SAT | No |
| `unsupported` | No interruptible SAT solver, or a gate outside the classical grammar | No |

Malformed types, source-pin mismatch and invalid receipts raise exceptions.
Every result keeps `candidate_authorized=false`. Positive receipts require
fresh SAT replay against the caller's source, position, predicate and initial
constants. Replay rebuilds the cut search and concretely checks saved local
witnesses, which may differ from a fresh solver model. Solver labels and
reason strings are historical metadata. A result's private seal prevents
accidental in-process field edits from yielding a usable predicate; it is not
a cryptographic signature or a defense against hostile Python in the process.

The trust boundary is structural slicing, exact Boolean encoding and the SAT
solver decision. This is a replayable receipt, not a solver-independent UNSAT
certificate, and it proves no phase, measurement, instrument or quantum-support
property.

## Bounds and relation to source-window readers

| Default `ConeLimits` cap | Value |
| --- | ---: |
| Materialized source gates / width | 200,000 / 100,000 |
| Retained cone gates / width | 20,000 / 256 |
| Total backward-scanned gates across attempts | 1,000,000 |
| Cut attempts / predicate nodes | 16 / 4,096 |
| SAT clauses / variables per query | 250,000 / 100,000 |

`budget=None` gives a 30-second whole-call deadline. Explicit `Budget()` removes
it; an inherited absolute deadline still applies. Source snapshotting, slicing,
encoding, solver setup, model replay and cleanup share the deadline. Clause and
variable limits are checked during allocation. These are cooperative limits,
not process termination or RSS limits; generic symbolic term/node/byte budgets
are refused. No partially extracted cone becomes a successful extraction and
no partially completed proof becomes `proved`.

Source snapshotting and hashing inspect the entire materialized source; each
backward attempt scans its interval. There is no reusable disk index yet.
The existing [KMX](kickmix-windows.md) and [KMB](kmb-binary-windows.md) readers
already extract source-pinned hybrid windows and should be reused by a future
file adapter. Their window coordinate systems differ, and a window's own
operation zero is not the original source origin. Passing a decoded window
as a new `Circuit` proves a theorem about that circuit only; it does not prove
its incoming preparation in the original file. No implicit KMB/KMX conversion,
measurement-bit mapping or source-to-window proof is added here.

## Reproducible bounded qualification

```bash
python -m pytest -q tests/test_classical_cone.py
python -m benchmarks.classical_cones --output /tmp/classical-cones.json --repetitions 3
```

Tests use an independent scalar bit-list interpreter on every boundary state
of seeded small circuits. Positive and adversarial cases cover temporal
dependencies, missing dependencies, stale source, wrong position/mapping,
dirty ancilla, overwritten product, spurious cut witnesses, expansion,
receipt mutation, SAT absence and resource failures. One positive continues
through the existing contextual substitution checker.

The harness records randomized serial trials, source/content identities,
software and machine versions, wall/CPU timings, cumulative process-peak RSS,
limits, outcomes and independent full-prefix checks. All fixtures are original
synthetic development cases under the repository MIT license. They are not
private qant data, an untouched holdout or evidence of production scalability.
Raw measurements belong in CI artifacts, not in the repository.
