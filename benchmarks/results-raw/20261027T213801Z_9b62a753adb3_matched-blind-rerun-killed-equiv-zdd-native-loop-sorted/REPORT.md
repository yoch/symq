# Matched-driver benchmark — corpus `blind`

symq `9b62a753adb3464505d148f371a96d0018d28649` (dirty: False), native extension SHA-256 `2e3f67910a34cfc0…`, Ubuntu clang version 18.1.3 (1ubuntu1), 3.12.3, Intel(R) Xeon(R) Processor (4 vCPU), started 2026-10-27T21:38:01Z.

Ratios are paired per circuit: baseline time / candidate time (> 1: candidate faster). Geometric mean with a 95% bootstrap interval over circuits, median, range and wins. `n` counts circuits both sides completed; one-sided completions are listed.

## Correctness

- Output groups checked: 0; fingerprint disagreements: 0; wrong verdicts: 0; invalid witnesses: 0.

| mode | error | timeout | timeout_censored |
|---|---:|---:|---:|
| `zdd-native/loop-sorted` | 1 | 1 | 1 |

## E1 — ablation of the native engine

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 — matched drivers against native baselines

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/loop` | `polybori/loop` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## MQT QCEC (verdicts only)

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/fused` | `qcec` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 by family (compute phase, simulate)

| candidate | baseline | family | n | geomean | range | only cand. | only base. |
|---|---|---|---:|---:|---|---:|---:|
