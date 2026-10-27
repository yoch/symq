# Matched-driver benchmark — corpus `blind`

symq `8d829fae5ff71ff80c4d48ca4b3b84872331893f` (dirty: False), native extension SHA-256 `2e3f67910a34cfc0…`, GCC: (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 3.12.3, Intel(R) Xeon(R) Processor (4 vCPU), started 2026-10-27T22:07:41Z.

Ratios are paired per circuit: baseline time / candidate time (> 1: candidate faster). Geometric mean with a 95% bootstrap interval over circuits, median, range and wins. `n` counts circuits both sides completed; one-sided completions are listed.

## Correctness

- Output groups checked: 34; fingerprint disagreements: 0; wrong verdicts: 0; invalid witnesses: 0.

| mode | error | ok | timeout | timeout_censored |
|---|---:|---:|---:|---:|
| `zdd-native/fused` | 2 | 34 | 10 | 14 |
| `zdd-native/loop` | 1 | 34 | 10 | 15 |
| `zdd-native/loop-sorted` | 4 | 34 | 9 | 13 |

## E1 — ablation of the native engine

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | compute | 16 | 0.94 [0.89, 0.99] | 0.91 | 0.81–1.17 | 4 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | end_to_end | 16 | 0.94 [0.89, 0.99] | 0.92 | 0.81–1.17 | 4 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | warm:compute | 16 | 0.82 [0.80, 0.84] | 0.83 | 0.76–0.89 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | compute | 18 | 0.94 [0.88, 1.01] | 0.94 | 0.72–1.39 | 5 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | end_to_end | 18 | 0.97 [0.91, 1.03] | 0.98 | 0.72–1.39 | 5 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | warm:compute | 16 | 0.82 [0.80, 0.84] | 0.83 | 0.73–0.87 | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | compute | 16 | 1.80 [1.38, 2.32] | 1.87 | 0.80–3.84 | 13 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | end_to_end | 16 | 1.55 [1.28, 1.88] | 1.64 | 0.80–2.64 | 13 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | warm:compute | 16 | 8.66 [8.10, 9.29] | 8.39 | 7.12–11.70 | 16 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | compute | 18 | 1.59 [1.29, 1.97] | 1.50 | 0.95–3.48 | 15 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | end_to_end | 18 | 1.38 [1.20, 1.59] | 1.33 | 0.95–2.21 | 15 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | warm:compute | 16 | 7.46 [6.48, 8.33] | 7.75 | 3.92–9.81 | 16 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 — matched drivers against native baselines

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/loop` | `polybori/loop` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## MQT QCEC (verdicts only)

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/fused` | `qcec` | equiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | end_to_end | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 by family (compute phase, simulate)

| candidate | baseline | family | n | geomean | range | only cand. | only base. |
|---|---|---|---:|---:|---|---:|---:|
