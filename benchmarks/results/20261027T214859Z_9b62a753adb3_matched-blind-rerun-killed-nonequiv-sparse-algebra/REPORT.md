# Matched-driver benchmark — corpus `blind`

symq `9b62a753adb3464505d148f371a96d0018d28649` (dirty: False), native extension SHA-256 `2e3f67910a34cfc0…`, Ubuntu clang version 18.1.3 (1ubuntu1), 3.12.3, Intel(R) Xeon(R) Processor (4 vCPU), started 2026-10-27T21:48:59Z.

Ratios are paired per circuit: baseline time / candidate time (> 1: candidate faster). Geometric mean with a 95% bootstrap interval over circuits, median, range and wins. `n` counts circuits both sides completed; one-sided completions are listed.

## Correctness

- Output groups checked: 1; fingerprint disagreements: 0; wrong verdicts: 0; invalid witnesses: 0.

| mode | error | ok |
|---|---:|---:|
| `sparse/algebra` | 2 | 1 |

## E1 — ablation of the native engine

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 — matched drivers against native baselines

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/loop` | `polybori/loop` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## MQT QCEC (verdicts only)

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/fused` | `qcec` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 by family (compute phase, simulate)

| candidate | baseline | family | n | geomean | range | only cand. | only base. |
|---|---|---|---:|---:|---|---:|---:|
