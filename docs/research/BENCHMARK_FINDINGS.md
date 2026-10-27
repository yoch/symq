# Findings of the first sealed QCEC run (27 Oct 2026)

Source: `benchmarks/results/20261027T122100Z_032df732465c_qcec-full/` (symq `032df73`,
CPython 3.12.3, 4 vCPU Intel Xeon, 15.6 GiB; 1 warmup + median of 7; 19 supported circuits
× 3 workloads × 9 backends = 513 cells, plus `c2_182` rejected). Python-only, one machine:
these are representation comparisons, not claims against native tools.

## Correctness

- Every completed cell agrees across backends (identical output polynomials; identical
  verdicts and first differing output). No wrong verdict, no worker error, no timeout.
- `packed` refuses all 57 cells (degree ≥3, never a false result). `truthtable` refuses the
  45 cells above 18 wires.

## Reproduction of the handoff claims (`simulate`)

| claim (handoff) | here | verdict |
|---|---|---|
| in-place XOR, median ~1.25× over `qant_set` on the 10 non-pathological circuits | 1.25× DEV (n=4), 1.12× holdout (n=6), 1.06× extension (n=8) | reproduced on DEV, smaller out of sample |
| `auto_zdd` ~99× on `c2_181` | 29.4× | direction reproduced, magnitude not |
| pure ZDD ~271× on `c2_181` | 42.4× | direction reproduced, magnitude not |
| `auto_zdd` switches at gate 33 on `c2_181` | gate index 32 (0-based), i.e. the 33rd gate | reproduced |
| `c2_181` tracemalloc peak ~10.1× lower with `auto_zdd` | 4 910 → 744 KiB (6.6×) | direction reproduced |
| ~400 ZDD nodes on `c2_181` | 2 919 nodes | not reproduced (variable order and/or implementation; see `BACKENDS.md`) |
| pure ZDD median ~5.1× slower than `fast_set` elsewhere | 0.21× of `sparse-copy` on DEV, 0.42× holdout, 0.59× extension | reproduced on DEV, milder elsewhere |
| `packed_only` refuses degree >2 | refuses every full circuit | reproduced |
| `adaptive` (packed + fallback) generally not competitive | `packed-fallback` 0.37–0.47× | reproduced |

The magnitude gap on `c2_181` comes from our ZDD being ~4.5× slower than the archived one
(3.8 ms vs 0.84 ms) while the sparse baselines are comparable (160 ms vs 226 ms). It cannot be
analysed further until the archived `src/zdd.py` is available (issue #2).

## New observations

1. **The 850-monomial threshold misses ZDD wins outside DEV.** On the extension split, pure
   `zdd` beats every sparse backend on `apla_203` (simulate 0.76 vs 1.26 ms; equiv 1.9 vs
   36 ms, 19×) and `dk17_224` (equiv 0.65 vs 2.8 ms, 4.3×), yet `auto-zdd` never switches
   there. The selector's only benefit in the whole corpus remains `c2_181`. Elsewhere it costs
   a median ~6% (holdout 0.94×). This argues for structural features beyond live monomial
   counts, evaluated on the untouched extension split.
2. **Product order matters for sparse ANF.** On `c2_181/equiv` the unoptimized `reference`
   (multiplying in gate order) takes 2.5 s against 4.5 s for `sparse` (smallest factor first).
   Ordering heuristics need their own ablation.
3. **`adaptive-wire` (per-wire promotion) is dominated by `auto-zdd`** on `c2_181`
   (10.3× vs 29.4×). Mixed representations pay repeated conversions of controls.
4. **ZDD variable order** changes `rd84_313` from 1 658 to 238 615 nodes. Order must be part
   of any selector, tuned on DEV only.

## Not covered

Restricted-input and synthetic GF(2¹²)/HMR workloads of the archive; native baselines
(issue #5); real 2026 circuits with X-basis erasure (see the phase/HMR fragment, issue #6).
