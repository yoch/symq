# Compact `Node` (24 to 12 bytes): measured effect

Produced by `benchmarks/native_nodes.py`: one fresh process per repetition (9), `taskset -c 0`,
CPython 3.12.3, two alternating rounds, shared 4-vCPU VM. `main` is main at 136d3a1, `compact`
is this branch. Random circuits (width, gates, max controls, seed). Raw data in the JSON files.

| case | nodes | time median main / compact (s) | RSS growth main / compact (MiB) |
|---|---|---|---|
| 12, 80, 4, 1 | 774 238 | 0.56, 0.62 / 0.59, 0.65 | 118 / 115 |
| 14, 80, 4, 1 | 1 669 521 | 2.33, 2.41 / 2.33, 2.33 | 455 / 440 |
| 18, 80, 4, 2 | 3 054 774 | 3.77, 4.10 / 4.13, 3.72 | 467 / 467 |

Reading: the `Node` array halves, but per-node storage also holds the term count, the
minimum-monomial arrays, the unique table and the cache, so peak memory moves by 0 to 3%
(capacity is doubled in steps, which quantizes RSS). Run time is unchanged within the noise
of this machine. No speed-up is claimed.
