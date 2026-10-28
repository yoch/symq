# Response to the second review of PR #63

Both reservations were correct, and the first was a real loss of coverage.

## 1. Five test files and the report were missing — **confirmed**

`git ls-tree` on #63 shows only `test_liveness_exact.py` and `test_adders.py`; the consolidation was
built from `main` and never picked up the files that lived on #60. Restored, with the combined suite
run:

| file | status |
|---|---|
| `tests/test_factored.py` | restored, 51 tests |
| `tests/test_channel_oracle.py` | restored, 11 tests |
| `tests/test_channel_criterion.py` | restored, 9 tests |
| `tests/test_continuous_simulation.py` | restored, 44 tests |
| `tests/test_liveness.py` | restored and **rewritten** for the corrected API |
| `research/engineering/2026-10-28/REPORT.md` | restored |

`test_liveness.py` is the one that mattered: it asserted the old, wrong definition. Rather than
delete it, it now checks the properties a liveness measure must have using `reachable_union`, and
its bounds are in the correct direction (`live <= sum(size(root))`). The two files coexist:
`test_liveness_exact.py` is the differential test between the two implementations,
`test_liveness.py` is the property test on circuits.

**Combined suite: 2 920 passed, 2 skipped** (was 2 720 before the restoration, which matches the
review's observation that #63 announced fewer tests than #60).

### Stale documents

Three files still carried superseded conclusions. None of them is erased:

- `prototype/liveness.py` -- **rewritten**: it now delegates to `reachable_union`. The old function
  is gone, not deprecated, because a script that imported it would silently produce wrong numbers.
  Its docstring records the error.
- `prototype/pilot_c4.py` -- updated to the new API, so every executable script in the pilot
  directory runs on the correct method.
- `PILOT_C.md` and `PILOT_C_CORRECTED.md` -- carry a `SUPERSEDED` banner naming the replacement.
- `RESULTS_FINAL.json` -- gains a `superseded_by` field pointing at the two files that replace it.

## 2. The collector is not in the engine — **confirmed, and now it is**

The review is right that the rebuild was a prototype. `NativeZDDAlgebra(collect_every=n)` is now a
constructor option, and `simulate()` uses it: the gate list runs in slices whose size adapts to the
threshold, and when the unique table crosses `n` the live wire values are moved into a fresh manager
and the computation continues there.

- Every node identifier returned belongs to the manager that is left, so a caller that keeps the
  returned tuple is unaffected (`tests/test_native_collection.py`, 58 tests, including 48
  differential cases at four thresholds and a check that the returned ids are not stale).
- `check_equivalence` uses it with no change, since it goes through `simulate`.

### What it does, measured in isolated processes

14 wires, 200 gates, seed 7, budget 40 M nodes:

| configuration | status | wall | peak RSS |
|---|---|---:|---:|
| no collection | **budget exceeded** | 65 s | 6 920 MiB |
| `collect_every=400_000` | **completes** | 44 s | **931 MiB** |

That is 7.4× less memory and a run that finishes where the other fails, with no change to the
outputs.

### The gain is in memory, not in time — and the sampling says so

`pilot_c7.py` repeats the comparison on four circuits (two widths, two seeds), one subprocess per
arm, each verified against a truth table:

| circuit | compute ratio | RSS ratio | node ratio |
|---|---:|---:|---:|
| 13×170 seed 7 | 0.80 | 0.32 | 0.22 |
| 13×170 seed 21 | 0.85 | 0.16 | 0.21 |
| 14×200 seed 7 | 0.71 | 0.15 | 0.13 |
| 14×200 seed 21 | **1.44** | 0.07 | 0.11 |

**Memory improves by 6-14× on every circuit; time improves on three and regresses 44 % on one.**
So the honest claim is a coverage and memory claim, not a speed claim, and it is stated that way.

## 3. `last_use` stays an option — agreed, and unchanged

`identity` remains the default. The per-family ratios the review recomputed are the ones in
`RESULTS_ORDER_CORRECTED.json`: adders 0.017, controlled adders 0.036, incrementers 1.105, MCX
chains 1.577. The holdout is new sizes of a known generator; that is an extrapolation, and
`src/symq/order.py` says so in the docstring rather than claiming generalisation.

## What is still not claimed

- The collector is **opt-in**. Turning it on by default would change the memory profile of every
  existing user for a 44 % time regression on some circuits; that is a decision for the owner, and
  the data to make it are now in `RESULTS_C7.json`.
- The GC verification covers 14-wire circuits, where truth tables are affordable. Wider circuits
  still have no independent oracle.
- No compiler output was used to validate the order policy.
