# Raw runs behind derived result directories

Sealed runs (each with its own `SHA256SUMS`) that are not used directly by the paper, because
some of their cells were re-measured or re-labelled. `benchmarks/merge_runs.py` combines them
into the derived directories under `benchmarks/results/`, whose `merge.json` lists every
substituted cell with its source run and both statuses.

| run | role |
|---|---|
| `20261027T150621Z_23469829a0dc_matched-blind` | blind campaign as executed (1 080 cells) |
| `20261027T175051Z_9b62a753adb3_matched-blind-rerun-merge` | 8 `zdd-native/algebra` *equiv* cells that failed at start-up while the source tree was briefly replaced (16:51:19–16:51:29 UTC) |
| `20261027T175252Z_9b62a753adb3_matched-blind-rerun-merge-incr` | the 8 `incr_*` *simulate* cells around that window (4 `cudd-bdd/loop`, 4 `zdd-native/loop-sorted`) |
| `20261027T175255Z_9b62a753adb3_matched-blind-rerun-oom` | first isolated re-run of `adder_31` *equiv* `zdd-native/loop` and the cell after it |
| `20261027T2136…Z_9b62a753adb3_matched-blind-rerun-killed-*` (8 runs) | isolated re-runs, one worker at a time, of every remaining cell killed by the memory cgroup |
| `20261027T181221Z_33515a36080b_matched-blind-fused` | `zdd-native/fused` and `zdd-native/loop` on the blind corpus with the corrected harness (return codes recorded, random circuits censored per gate and control count) |
| `20261027T220741Z_8d829fae5ff7_matched-blind-fused-eq` | the same for *equiv* and *nonequiv*, with `zdd-native/loop-sorted` (`8d829fa` = `33515a3` + `merge_runs.py`); 7 workers killed (return code −9), not re-run |

`9b62a75` changes no file under `src/`, `benchmarks/` or `tools/` relative to `2346982`; all
runs use the same native binary (SHA-256 `2e3f6791…`). Kernel records of the kills and their
attribution to cells: `paper/evidence/oom_kills.md` on the paper branch.
