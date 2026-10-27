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
| in-place XOR, median ~1.25× over `copy_set` on the 10 non-pathological circuits | 1.25× DEV (n=4), 1.12× holdout (n=6), 1.06× extension (n=8) | reproduced on DEV, smaller out of sample |
| `auto_zdd` ~99× on `c2_181` | 29.4× | direction reproduced, magnitude not |
| pure ZDD ~271× on `c2_181` | 42.4× | direction reproduced, magnitude not |
| `auto_zdd` switches at gate 33 on `c2_181` | gate index 32 (0-based), i.e. the 33rd gate | reproduced |
| `c2_181` tracemalloc peak ~10.1× lower with `auto_zdd` | 4 910 → 744 KiB (6.6×) | direction reproduced |
| ~400 ZDD nodes on `c2_181` | 2 919 nodes | explained below: 443 nodes with the archive's product recursion and order |
| pure ZDD median ~5.1× slower than `fast_set` elsewhere | 0.21× of `sparse-copy` on DEV, 0.42× holdout, 0.59× extension | reproduced on DEV, milder elsewhere |
| `packed_only` refuses degree >2 | refuses every full circuit | reproduced |
| `adaptive` (packed + fallback) generally not competitive | `packed-fallback` 0.37–0.47× | reproduced |

The magnitude gap on `c2_181` comes from our ZDD being ~4.5× slower than the archived one
(3.8 ms vs 0.84 ms), while the sparse baselines are comparable (160 ms vs 226 ms).

### Root cause, from the imported archive (issue #2)

The archived engines were rerun on this machine, in-process, with 1 warmup and the median of 7
runs:

| `c2_181` simulate | archive | symq at `032df73` |
|---|---:|---:|
| copy-on-XOR sparse | 159 ms | 159 ms |
| ZDD | 1.15 ms (443 nodes) | 3.88 ms (2 919 nodes) |

So the machine does not explain the gap; the ZDD implementation does, for two reasons:

1. **Product recursion.** symq used the two-product form `v((P0 + P1)(Q0 + Q1) + P0Q0)`. The
   archive uses the three-product form `v(P0Q1 + P1Q0 + P1Q1)`. With the three-product form,
   symq allocates exactly the archive's node counts. The two-product form builds large cofactor
   sums, for example 238 615 nodes instead of 1 436 on `rd84_313` under the reversed order.
   symq now uses the three-product form.
2. **Variable order.** The archive puts the highest wire at the root. On `c2_181` this order
   gives 443 nodes and 0.64 ms with the three-product form. It is 1.5× slower on `rd84_313` and
   `sym9_317`, so symq's default order is unchanged.

A second sealed run, `benchmarks/results/20261027T125339Z_d5427d4d5204_zdd-three-product/`,
covers `sparse-copy`, `sparse`, `zdd` and `auto-zdd` on all 19 circuits at the fixed commit:

- All 228 fingerprints are identical to the first run, so the outputs and verdicts are
  unchanged.
- The sparse backends move by at most ±8% (medians 0.98–1.00×), so the two runs are comparable.
- `zdd` gains up to 3.2×: `rd84_313` simulate goes from 2.16 to 0.90 ms, and `c2_181` simulate
  from 3.77 to 2.65 ms (2 919 → 2 232 nodes).
- On `c2_181`, the speedup over `sparse-copy` rises from 42× to 61× for `zdd` and from 29× to
  37.5× for `auto-zdd`.
- The `zdd` median over `sparse-copy` on DEV goes from 0.21× to 0.49×. The remaining gap to the
  handoff (271× and 99×) is the variable order and our generic `Algebra` layer.

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
4. **ZDD variable order** still matters, but less than the first run suggested. The
   238 615-node blow-up on `rd84_313` came from the two-product recursion. With the
   three-product form, reversing the order changes `c2_181` from 2 232 to 443 nodes, and
   `rd84_313` from 910 to 1 436. Order must be part of any selector, tuned on DEV only.

## Not covered

Restricted-input and synthetic GF(2¹²)/HMR workloads of the archive; native baselines
(issue #5); real 2026 circuits with X-basis erasure (see the phase/HMR fragment, issue #6).
