# Native core: per-call cost, throughput and thread scaling

Produced by `benchmarks/native_threads.py`, three alternating rounds per checkout, same
interpreter (CPython 3.12.3), `taskset -c 0,1` (two cores, so 2x is the ceiling for threads),
on a shared 4-vCPU VM. `main-base` is main at 1d33f80, `fixed` is this branch (ABI 3).

| metric (median of 3 rounds) | main-base | fixed |
|---|---|---|
| `xor` per call | 99 ns | 99 ns |
| `product` per call | 100 ns | 101 ns |
| 50 000 cheap gates (8 qubits) | 11.2 ms | 8.9 ms |
| 4 heavy circuits, sequential | 0.203 s | 0.202 s |
| 4 heavy circuits, 4 threads | 0.222 s | 0.157 s |
| thread speedup | 0.91x (0.81 to 0.91) | 1.25x (1.21 to 1.33) |

Per-call cost is unchanged: `xor` and `product` keep the GIL. The thread speedup varies across rounds on
this machine (values above, raw data in the JSON files); read it as "scales on independent managers
instead of serializing", not as a stable factor. These numbers say nothing about external
comparisons.
