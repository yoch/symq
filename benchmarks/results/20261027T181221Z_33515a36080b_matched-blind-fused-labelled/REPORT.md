# Matched-driver benchmark — corpus `blind`

symq `33515a36080b1e99958961d0ee25bfde19abc1e8` (dirty: False), native extension SHA-256 `2e3f67910a34cfc0…`, GCC: (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 3.12.3, Intel(R) Xeon(R) Processor (4 vCPU), started 2026-10-27T18:12:21Z.

Ratios are paired per circuit: baseline time / candidate time (> 1: candidate faster). Geometric mean with a 95% bootstrap interval over circuits, median, range and wins. `n` counts circuits both sides completed; one-sided completions are listed.

## Correctness

- Output groups checked: 17; fingerprint disagreements: 0; wrong verdicts: 0; invalid witnesses: 0.

| mode | killed | ok | timeout | timeout_censored |
|---|---:|---:|---:|---:|
| `zdd-native/fused` | 4 | 18 | 3 | 5 |
| `zdd-native/loop` | 0 | 18 | 5 | 7 |

## E1 — ablation of the native engine

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 — matched drivers against native baselines

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/loop` | `polybori/loop` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## MQT QCEC (verdicts only)

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|

## E2 by family (compute phase, simulate)

| candidate | baseline | family | n | geomean | range | only cand. | only base. |
|---|---|---|---:|---:|---|---:|---:|
| `zdd-native/loop` | `polybori/loop` | adder | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cadder | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | incr | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | mult | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | rand | 0 | — | — | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | adder | 0 | — | — | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cadder | 0 | — | — | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | incr | 0 | — | — | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | mult | 0 | — | — | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | rand | 0 | — | — | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | adder | 0 | — | — | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cadder | 0 | — | — | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | incr | 0 | — | — | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | mult | 0 | — | — | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | rand | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | adder | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cadder | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | incr | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | mult | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | rand | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | adder | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cadder | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | incr | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | mult | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | rand | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | adder | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cadder | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | incr | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | mult | 0 | — | — | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | rand | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | adder | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cadder | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | incr | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | mult | 0 | — | — | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | rand | 0 | — | — | 0 | 0 |
