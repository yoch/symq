# Pilot C, corrected: a rebuild that actually saves circuits

> **CORRECTED AGAIN (28 October 2026, audit of PR #63).** Two things in this file were still
> provisional: the time figures included the ANF export and the truth-table check, and the
> memory comparison used `ru_maxrss` across several arms in one process. Both are fixed in
> `prototype/pilot_c6.py`, whose results replace the wall-time column below. The *memory* finding
> stands and is now measured per subprocess: 1 741 MiB for eight fragments against **262 MiB** for
> a per-gate rebuild, with 0 mismatches on all 16 384 inputs.



Replaces `PILOT_C.md`. The original measured a state that never existed: `simulate(fragment)`
restarts from the identity, `manager.size` double counted shared nodes, and the "rebuild"
continued in the old manager. `PILOT_CORRECTIONS.md` items C1-C3 record the defects.

## The three facts

**1. The live set is tiny.** 13 wires, 170 gates, with a continuous simulation sampled after each
quarter:

| after chunk | nodes created | live nodes (exact, union over roots) | live monomials |
|---:|---:|---:|---:|
| 0 | 18 383 | 729 | 1 942 |
| 1 | 1 508 552 | 354 | 7 961 |
| 2 | 6 262 136 | 49 | 8 188 |
| 3 | 9 426 530 | 24 | 8 191 |

Nine million nodes created, twenty-four live. The memory the plain engine needs is set by the
garbage, not by the function.

**2. Transferring the live roots is cheap.** Rebuilding into a fresh manager by expanding every
live root to monomials and re-importing costs 14 000-27 000 nodes at those points, i.e. 0.2-0.3 %
of the table it replaces, and 0.01-0.33 s of the 7-12 s run.

**3. Rebuild frequency is the lever, and more is better.** 13 wires, 170 gates, one rebuild
whenever the table exceeds 400 000 nodes:

| fragments | peak created nodes | rebuilds | total | transfer |
|---:|---:|---:|---:|---:|
| 1 (none) | 9 426 530 | 0 | 11.76 s | 0.00 s |
| 4 | 4 929 668 | 2 | 9.96 s | 0.05 s |
| 16 | 1 945 478 | 9 | 8.17 s | 0.15 s |
| 64 | 1 207 289 | 20 | 7.54 s | 0.27 s |
| 170 (per gate) | **717 290** | 25 | **7.24 s** | 0.33 s |

Every schedule produces the same outputs (checked monomial for monomial against the identity-order
baseline), so the gain is free: **-92 % peak nodes and -38 % wall time** at the finest schedule.

## Does it save a circuit the plain engine cannot finish?

Yes. 14 wires, 200 gates, 12 M-node budget:

| arm | status | peak created | time |
|---|---|---:|---:|
| plain (one manager) | **budget exceeded** | 12 000 000 | 14.6 s |
| rebuild at 1 M nodes | **completed, exact** | 11 250 955 | 52.0 s |

The plain engine cannot finish this circuit at any budget tried (it also hit a 30 M-node limit);
the rebuild completes it. The cost is 3.5x the wall time of a run that fails, which is the price
of not failing.

The reason it still needs 11 M nodes at the peak is the *chunk size*: with eight fragments each
creates ~1.4 M nodes between two checks. Running the same circuit with a per-gate schedule
confirms the extrapolation:

| schedule | status | peak created | rebuilds | time |
|---|---|---:|---:|---:|
| monolithic | budget exceeded | 12 000 000+ | 0 | -- |
| 8 fragments, 1 M threshold | completed | 11 250 955 | 5 | 52.0 s |
| 200 fragments (per gate), 1 M | completed | **2 102 404** | 33 | 40.1 s |
| 200 fragments, 400 k | completed | **1 438 659** | 54 | **38.1 s** |

So on this circuit the collector turns a hard failure into a 38 s verification, with **-87 % peak
nodes and -27 % time** against the best rebuild schedule that does not fragment per gate.

## Decision

**Build the collector.** The evidence is: 99.99 % of the table is unreachable, the transfer costs
0.2-0.3 % of it, the fastest schedule is also the leanest, and it turns a hard budget failure into
a completed verification with identical outputs.

It is **engineering**, not a scientific contribution: CUDD has had a collector for decades and the
mechanism here is a rebuild, not a new idea. It is also the single change with the largest measured
effect on what this engine can finish.

## What is still not measured

* **Memory actually returned to the allocator.** The node counts are exact, but the bytes freed
  depend on `malloc` behaviour; a `malloc_trim` or a dedicated arena may be needed to see the RSS
  drop.
* **A native collector.** All of this rebuilds through the public API, where the live roots are
  re-imported as monomials. A native path would copy the live sub-DAG directly, which the transfer
  cost (0.3 %) suggests is unnecessary, but it is the version that would ship.
* **Interaction with the operation cache.** A rebuild drops the cache; the measured times already
  include that loss, so the numbers are conservative.
