# Pilot C: memory, and whether a collector is worth building

> **SUPERSEDED (28 October 2026).** This file records an early measurement whose *method* was
> later shown to be wrong: the live-node count used the diagram of the union of the root families,
> which is not the set of nodes reachable from the roots, and the direction of the bound on the
> per-root sum was inverted. The corrected measurement is `reachable_union`, and the corrected
> results are in `RESULTS_C6.json` (sealed with a truth-table oracle) and `PILOT_C_CORRECTED.md`.
> The figures below are kept as a record and must not be quoted as live-node counts.



Files: `prototype/pilot_c.py` (live vs dead), `prototype/pilot_c2.py` (rebuild cost).
Raw numbers: `RESULTS.json`.

Issue #56 asks for a decision before implementation: are the nodes dead (build a collector) or
alive (stop, the explosion is structural)? This pilot answers it with instrumentation only. No
engine change, no GC, nothing merged.

## 1. The nodes are dead

Dense random circuits, outputs of one simulation treated as the live roots -- exactly the set that
must survive across a verification step:

| width | gates | nodes created | reachable | dead (upper bound) | fraction |
|---:|---:|---:|---:|---:|---:|
| 14 | 200 | 134 186 | 501 | 133 685 | 99.6 % |
| 16 | 300 | 2 190 632 | 4 179 | 2 186 453 | 99.8 % |
| 18 | 400 | budget (3 M nodes) | -- | -- | -- |

The live roots hold 0.2-0.4 % of the table. `dead` is an *upper* bound, because `manager.size`
counts a shared node once per root; the true dead population is at least as large, so this is the
conservative direction.

This settles the first half of #56: the memory is not structural, it is garbage.

## 2. But the measurement has a caveat that matters

The roots I used are the outputs of the *last* chunk of a partitioned simulation. In a real
verification, the live set is larger: the wire values of both circuits, the witness, the extracted
polynomials, and -- while a gate is being applied -- the intermediate product. A collector would
have to treat all of those as roots, and any of them can hold a large fraction of the table.

So the 99.6 % figure is the *favourable* case, and even then the second question has to be asked:
what does collecting cost?

## 3. The rebuild is affordable

Implemented the most expensive way possible -- expand every live root to explicit monomials, then
re-import into a fresh manager -- it still costs less than the simulation it interrupts:

| width | gates | simulation | rebuild | ratio |
|---:|---:|---:|---:|---:|
| 12 | 150 | 0.002 s | 0.002 s | 0.72 |
| 14 | 200 | 0.008 s | 0.004 s | 0.44 |
| 16 | 300 | budget (3 M nodes) | -- | -- |

44-72 % of the simulation is an upper bound on the cost of any smarter collector (one that
re-creates only the reachable sub-DAG without materialising monomials would be cheaper still).
The third instance hit the node budget before the comparison could be made, which is itself the
motivating case: that is a run a collector would have been able to continue.

## 4. What is *not* measured

* **Memory actually reclaimed.** I measured the node count left behind (`live_after_rebuild`),
  not the bytes freed, because the allocator is not instrumented. The node count is a proxy.
* **Whether the memory saving changes what can be verified.** The decisive experiment is to run
  a circuit that currently dies at 15 GiB -- the blind-corpus adders killed in the paper's
  campaign -- with and without a collector. That requires the collector to exist.
* **The cost of triggering.** I rebuilt after every chunk; a real collector would trigger on a
  growable threshold, and the trigger policy is a separate measurement.

## 5. Verdict

Category II, with a clean justification. The data say: build the collector (the memory is
garbage and reclaiming it is cheap), and do not present it as a contribution (CUDD has had one
for decades, and the mechanism is textbook). `NEXT_STEPS.md` item 2 names the instrumentation
that would turn this into the decisive experiment.
