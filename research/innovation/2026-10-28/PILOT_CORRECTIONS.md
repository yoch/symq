# Corrections to the 2026-10-28 pilots

Every defect below is reproducible, and every one is fixed in code that now has a test. The
historical `PILOTS.md`, `PILOT_A.md`, `PILOT_B.md`, `PILOT_C.md`, `RESULTS.json` and
`DECISION.md` are **left untouched**: they record what was measured, including what was wrong.
The corrected results live in `RESULTS_C_CORRECTED.json`, `RESULTS_C4.json`, `RESULTS_C5.json`
and in the new documents `PILOT_C_CORRECTED.md`, `PILOT_A_CORRECTED.md`, `PILOT_B_CORRECTED.md`.

## C1. The fragmented simulation was not continuous

`NativeZDDAlgebra.simulate(circuit)` builds its own state from the identity and calls the native
loop with ``None`` as the initial state, so `algebra.simulate(fragment)` **restarts** every time.
`pilot_c.py` and `pilot_c2.py` called it once per chunk, so every "chunk" was an independent
simulation of a different circuit, and the node counts and liveness figures described a state
the pilot never had.

Fixed by `prototype/continuous.py::apply_fragment`, which passes the previous wire values through
the native entry point that already accepted them. Verified by
`tests/test_continuous_simulation.py`: 30 random circuits, split at every gate boundary, outputs
equal to the monolithic run monomial for monomial, against the independent Python ZDD backend.
44 tests.

## C2. The liveness figure double counted shared nodes

`sum(manager.size(root) for root in roots)` walks one DAG per root, so a node shared by two wires
was counted twice and the "dead" figure was an upper bound of unknown tightness.

Fixed by `prototype/liveness.py::union_node_count`, which rebuilds the union of the root families
in a scratch manager. Because ZDDs are canonical, the node count of the union is exactly the
number of nodes reachable from the roots. Verified by `tests/test_liveness.py` (28 tests):
the exact count lies between the per-root sum and the total, the union reproduces every root
family, an identity circuit keeps all its nodes, and `A ; A^{-1}` leaves garbage behind.

The corrected numbers are **larger** dead fractions than reported before, not smaller: at
13 wires and 170 gates, 9 426 530 nodes created against **24 live**.

## C3. The "rebuild" continued in the old manager

`pilot_c2.py::run` built a fresh manager, imported the roots, then called
`algebra.simulate(part)` on the **old** algebra and discarded the new one. The measurement
described a rebuild that never happened.

Fixed by `pilot_c_corrected.py::run_rebuild`, which returns the new algebra and continues in it,
and by `pilot_c4.py`, which additionally checks that two different rebuild schedules produce
identical outputs (they do, on every instance that completed).

A second bug in the same place: rebuilding *after the last fragment* transfers roots nobody
uses again, and the returned ids then belong to a manager that receives no further work, so the
final ``to_anf`` raised ``node id outside this manager``. Now the rebuild only happens when gates
remain.

## A1. `constant_outcomes` was wrong

It returned true for any coefficient with a single monomial, so `g_j = x_0` -- a coefficient that
depends on the input and therefore restricts the kernel -- was reported as constant. Fixed to
accept only the empty family and the family `{1}`; `tests/test_channel_criterion.py` pins both
cases.

## A2. The pair space was built over the full width

The criterion built its ZDD over `2 * (data + ancillas)` variables, which caps the circuit width
at half of the engine's limit for no reason: `phi0` and every `g_j` are functions of the data
inputs only (F1, F2). Fixed to `2 * data`; the reported `pairs` count now reflects that.

## A3. The factorisation escaped the budget

`factor(program)` ran plain ANF arithmetic before any budgeted backend was created, so a
program with a large phase could consume unbounded memory on the way in. It now takes the same
`Budget` and checks time between instructions and the monomial count after each one.

## A4. The partial trace was not a partial trace

`trace_out_ancillas` dropped the ancilla bits and *added* the coefficients, without requiring
the ancilla configuration to agree between the row and the column. On a Bell pair this returned
a matrix with trace 2 instead of the maximally mixed state, and on any entangled state it
manufactured coherences that do not exist.

Fixed by `partial_trace`, which keeps only the terms with equal ancilla patterns.
`tests/test_channel_oracle.py` (11 tests) pins it on a Bell pair, on product states, on a phase
and on a bit flip, and checks that the reduced state is physical.

## A5. Pair keys could collide

`channel_matrix` packed ``(x, y)`` into ``x << 16 | y``, so two pairs collided as soon as either
component needed 16 bits. Fixed by using explicit `(x, y, u, v)` tuples; the test pins the key
shape.

## A6. The A2b comparison used the wrong specification

`pilot_a2.py` compared every AND gadget with the identity, including the gadgets that *change*
the data wires, so "channel-equivalent to identity" was the wrong question and the answers mixed
two effects. `PILOT_A_CORRECTED.md` redoes the comparison against each gadget's own functional
specification.

## B1. The miter pilot measured nodes only

`pilot_b2.py` reported node counts and nothing else, so a strategy that halves nodes but doubles
time would have looked like a win. `PILOT_B_CORRECTED.md` redoes it with wall time, peak nodes
and the construction cost of the composed circuit, and adds the case the old pilot lacked: two
circuits with similar structure but no textually identical prefix.
