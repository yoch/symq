# Matched-driver benchmark — corpus `qcec`

symq `33515a36080b1e99958961d0ee25bfde19abc1e8` (dirty: False), native extension SHA-256 `2e3f67910a34cfc0…`, GCC: (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 3.12.3, Intel(R) Xeon(R) Processor (4 vCPU), started 2026-10-27T17:54:56Z.

Ratios are paired per circuit: baseline time / candidate time (> 1: candidate faster). Geometric mean with a 95% bootstrap interval over circuits, median, range and wins. `n` counts circuits both sides completed; one-sided completions are listed.

## Correctness

- Output groups checked: 57; fingerprint disagreements: 0; wrong verdicts: 0; invalid witnesses: 0.

| mode | not_applicable | ok |
|---|---:|---:|
| `cudd-bdd-static/loop` | 0 | 57 |
| `cudd-bdd/loop` | 0 | 57 |
| `polybori/algebra` | 0 | 57 |
| `polybori/loop` | 0 | 57 |
| `polybori/loop-sorted` | 0 | 57 |
| `qcec` | 19 | 38 |
| `sparse/algebra` | 0 | 57 |
| `zdd-native/algebra` | 0 | 57 |
| `zdd-native/fused` | 0 | 57 |
| `zdd-native/loop` | 0 | 57 |
| `zdd-native/loop-sorted` | 0 | 57 |
| `zdd-python/algebra` | 0 | 57 |

## E1 — ablation of the native engine

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | compute | 19 | 4.19 [3.53, 5.09] | 3.95 | 2.57–11.64 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | end_to_end | 19 | 4.03 [3.36, 4.92] | 3.84 | 2.38–11.41 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | warm:compute | 19 | 1.20 [1.17, 1.22] | 1.21 | 1.10–1.33 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | compute | 19 | 4.29 [3.61, 5.26] | 3.98 | 2.61–15.82 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | end_to_end | 19 | 4.15 [3.50, 5.08] | 3.88 | 2.44–15.18 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | warm:compute | 19 | 1.21 [1.18, 1.24] | 1.23 | 1.09–1.29 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | compute | 19 | 5.41 [4.48, 6.73] | 5.24 | 2.94–20.43 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | end_to_end | 19 | 5.01 [4.12, 6.29] | 4.88 | 2.80–19.64 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | warm:compute | 19 | 1.21 [1.18, 1.23] | 1.22 | 1.11–1.31 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | compute | 19 | 2.11 [1.85, 2.39] | 2.26 | 1.30–3.06 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | end_to_end | 19 | 1.94 [1.75, 2.14] | 2.10 | 1.29–2.72 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | warm:compute | 19 | 3.43 [3.29, 3.58] | 3.47 | 2.93–3.96 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | compute | 19 | 2.40 [2.18, 2.61] | 2.50 | 1.54–3.08 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | end_to_end | 19 | 2.10 [1.96, 2.23] | 2.13 | 1.51–2.60 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | warm:compute | 19 | 3.41 [3.24, 3.59] | 3.44 | 2.81–4.06 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | compute | 19 | 2.13 [1.94, 2.33] | 2.08 | 1.38–2.97 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | end_to_end | 19 | 1.85 [1.74, 1.97] | 1.89 | 1.37–2.56 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | warm:compute | 19 | 3.40 [3.23, 3.58] | 3.32 | 2.80–4.09 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | compute | 19 | 0.89 [0.87, 0.92] | 0.90 | 0.79–0.97 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | end_to_end | 19 | 0.90 [0.88, 0.93] | 0.91 | 0.79–1.00 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | warm:compute | 19 | 0.81 [0.80, 0.82] | 0.81 | 0.78–0.87 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | compute | 19 | 0.88 [0.86, 0.90] | 0.88 | 0.78–0.96 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | end_to_end | 19 | 0.89 [0.85, 0.92] | 0.90 | 0.68–1.01 | 1 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | warm:compute | 19 | 0.81 [0.80, 0.83] | 0.82 | 0.75–0.86 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | compute | 19 | 0.90 [0.87, 0.93] | 0.90 | 0.76–1.08 | 2 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | end_to_end | 19 | 0.92 [0.89, 0.96] | 0.92 | 0.78–1.13 | 3 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | warm:compute | 19 | 0.81 [0.80, 0.82] | 0.81 | 0.77–0.87 | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | compute | 19 | 2.30 [1.85, 2.83] | 2.41 | 1.11–4.88 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | end_to_end | 19 | 1.83 [1.60, 2.10] | 1.97 | 1.11–3.52 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | warm:compute | 19 | 9.33 [8.61, 10.03] | 10.24 | 6.36–11.16 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | compute | 19 | 2.67 [2.30, 3.07] | 2.83 | 1.32–4.86 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | end_to_end | 19 | 2.02 [1.82, 2.25] | 2.08 | 1.30–3.55 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | warm:compute | 19 | 8.69 [7.97, 9.46] | 8.94 | 6.05–12.09 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | compute | 19 | 2.28 [2.02, 2.54] | 2.49 | 1.15–3.29 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | end_to_end | 19 | 1.81 [1.68, 1.96] | 1.83 | 1.18–2.42 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | warm:compute | 19 | 8.76 [7.94, 9.54] | 9.43 | 5.33–12.02 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | compute | 19 | 18.19 [15.30, 21.33] | 22.06 | 9.76–28.93 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | end_to_end | 19 | 12.89 [11.69, 14.21] | 13.52 | 9.05–19.13 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | warm:compute | 19 | 31.10 [29.19, 33.11] | 31.17 | 22.95–39.51 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | compute | 19 | 24.06 [21.26, 26.71] | 26.56 | 11.83–31.94 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | end_to_end | 19 | 15.70 [13.60, 18.10] | 17.60 | 8.24–29.13 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | warm:compute | 19 | 29.27 [27.24, 31.38] | 30.16 | 21.80–36.05 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | compute | 19 | 23.58 [21.31, 25.84] | 23.79 | 12.75–33.81 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | end_to_end | 19 | 15.56 [13.31, 18.22] | 16.77 | 8.71–32.09 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | warm:compute | 19 | 29.17 [27.03, 31.28] | 29.23 | 20.12–35.76 | 19 | 0 | 0 |

## E2 — matched drivers against native baselines

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/loop` | `polybori/loop` | equiv | compute | 19 | 3.00 [2.61, 3.42] | 3.26 | 1.61–4.37 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | end_to_end | 19 | 36.71 [23.65, 55.93] | 48.79 | 6.00–142.87 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | warm:compute | 19 | 2.14 [2.06, 2.21] | 2.17 | 1.74–2.36 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | compute | 19 | 3.46 [3.12, 3.80] | 3.46 | 2.16–4.68 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | end_to_end | 19 | 57.25 [41.04, 78.55] | 60.04 | 14.00–163.68 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | warm:compute | 19 | 2.15 [2.05, 2.26] | 2.18 | 1.75–2.48 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | compute | 19 | 3.94 [3.49, 4.41] | 3.94 | 2.17–5.52 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | end_to_end | 19 | 79.43 [55.62, 109.85] | 83.54 | 15.28–227.71 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | warm:compute | 19 | 2.11 [2.03, 2.19] | 2.13 | 1.77–2.46 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | compute | 19 | 3.12 [2.75, 3.49] | 3.68 | 1.60–4.07 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | end_to_end | 19 | 31.95 [20.13, 50.48] | 36.15 | 6.62–152.82 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | warm:compute | 19 | 2.65 [2.37, 3.05] | 2.44 | 2.02–5.76 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | compute | 19 | 3.55 [3.15, 3.98] | 3.78 | 2.06–5.74 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | end_to_end | 19 | 47.08 [33.35, 64.85] | 52.20 | 9.64–135.14 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | warm:compute | 19 | 2.59 [2.31, 3.01] | 2.33 | 1.98–6.43 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | compute | 19 | 4.09 [3.66, 4.50] | 4.41 | 2.35–5.18 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | end_to_end | 19 | 86.43 [65.53, 112.51] | 83.95 | 17.71–217.40 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | warm:compute | 19 | 2.57 [2.28, 2.99] | 2.24 | 1.95–6.50 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | compute | 19 | 2.92 [2.70, 3.17] | 2.75 | 2.20–3.99 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | end_to_end | 19 | 21.84 [15.35, 31.57] | 18.73 | 6.39–117.41 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | warm:compute | 19 | 2.68 [2.19, 3.36] | 2.42 | 1.57–7.76 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | compute | 19 | 3.24 [2.86, 3.73] | 3.01 | 2.13–7.27 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | end_to_end | 19 | 30.97 [23.85, 39.71] | 31.68 | 9.83–74.37 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | warm:compute | 19 | 2.59 [2.11, 3.27] | 2.51 | 1.51–8.82 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | compute | 19 | 3.62 [3.27, 4.04] | 3.50 | 2.17–7.12 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | end_to_end | 19 | 47.59 [35.43, 62.90] | 46.02 | 14.22–125.60 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | warm:compute | 19 | 2.54 [2.08, 3.18] | 2.27 | 1.51–8.78 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | compute | 19 | 6.15 [4.44, 8.39] | 6.93 | 1.64–15.46 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | end_to_end | 19 | 52.40 [30.11, 88.82] | 86.00 | 7.53–230.40 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | warm:compute | 19 | 16.19 [14.79, 17.56] | 16.87 | 10.08–20.36 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | compute | 19 | 8.06 [6.55, 9.82] | 8.07 | 3.24–15.71 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | end_to_end | 19 | 90.22 [62.32, 125.52] | 105.44 | 15.26–248.58 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | warm:compute | 19 | 15.26 [13.83, 16.80] | 15.22 | 9.88–21.28 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | compute | 19 | 8.07 [6.67, 9.68] | 8.51 | 3.80–16.02 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | end_to_end | 19 | 125.62 [86.54, 175.21] | 151.17 | 22.27–337.05 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | warm:compute | 19 | 14.99 [13.44, 16.52] | 15.05 | 8.87–21.30 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | compute | 19 | 2.74 [2.27, 3.26] | 2.97 | 0.91–6.23 | 18 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | end_to_end | 19 | 24.40 [15.41, 37.88] | 30.35 | 4.92–102.44 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | warm:compute | 19 | 2.60 [2.39, 2.86] | 2.42 | 2.12–4.33 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | compute | 19 | 3.15 [2.72, 3.64] | 2.96 | 1.82–5.93 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | end_to_end | 19 | 34.23 [24.23, 47.61] | 35.69 | 7.82–93.38 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | warm:compute | 19 | 2.49 [2.32, 2.70] | 2.39 | 1.93–3.77 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | compute | 19 | 3.48 [2.95, 4.10] | 3.65 | 1.71–7.66 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | end_to_end | 19 | 60.97 [42.36, 87.12] | 52.03 | 13.23–255.31 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | warm:compute | 19 | 2.48 [2.29, 2.71] | 2.29 | 1.91–3.88 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | compute | 19 | 2.71 [2.22, 3.26] | 2.89 | 1.00–5.70 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | end_to_end | 19 | 23.67 [15.18, 36.18] | 33.27 | 5.03–98.30 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | warm:compute | 19 | 2.59 [2.38, 2.86] | 2.37 | 2.10–4.50 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | compute | 19 | 3.10 [2.69, 3.58] | 3.09 | 1.75–5.81 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | end_to_end | 19 | 33.88 [23.25, 49.57] | 33.91 | 6.86–237.90 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | warm:compute | 19 | 2.45 [2.30, 2.63] | 2.35 | 2.09–3.51 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | compute | 19 | 3.38 [2.87, 3.96] | 3.49 | 1.65–7.16 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | end_to_end | 19 | 65.94 [46.72, 90.86] | 71.74 | 13.22–235.22 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | warm:compute | 19 | 2.49 [2.30, 2.72] | 2.31 | 2.00–3.86 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | compute | 19 | 21.27 [10.38, 52.93] | 13.53 | 4.00–10480.89 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | end_to_end | 19 | 15.09 [7.45, 38.54] | 8.57 | 3.92–9931.33 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | warm:compute | 19 | 186.14 [83.61, 566.63] | 94.77 | 30.73–573108.58 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | compute | 19 | 18.39 [11.16, 34.46] | 13.42 | 3.46–1489.09 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | end_to_end | 19 | 11.77 [7.15, 22.95] | 7.78 | 3.28–1360.56 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | warm:compute | 19 | 98.13 [56.21, 223.70] | 60.76 | 30.26–50098.68 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | compute | 19 | 12.58 [7.97, 22.48] | 9.25 | 2.96–730.05 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | end_to_end | 19 | 8.27 [5.29, 15.22] | 6.06 | 2.93–690.27 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | warm:compute | 19 | 95.12 [55.01, 214.69] | 57.46 | 28.89–48326.13 | 19 | 0 | 0 |

## MQT QCEC (verdicts only)

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/fused` | `qcec` | equiv | compute | 19 | 106.93 [53.94, 210.06] | 148.18 | 11.52–1226.99 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | end_to_end | 19 | 61.83 [36.05, 105.87] | 100.35 | 10.36–774.85 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | compute | 19 | 121.02 [71.12, 205.08] | 119.24 | 15.21–1064.98 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | end_to_end | 19 | 63.63 [42.65, 90.88] | 77.40 | 6.64–210.17 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 by family (compute phase, simulate)

| candidate | baseline | family | n | geomean | range | only cand. | only base. |
|---|---|---|---:|---:|---|---:|---:|
| `zdd-native/loop` | `polybori/loop` | 5xp1 | 1 | 3.59 | 3.59–3.59 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | C7552 | 1 | 3.62 | 3.62–3.62 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | add6 | 1 | 2.17 | 2.17–2.17 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | alu1 | 1 | 4.77 | 4.77–4.77 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | apla | 1 | 3.74 | 3.74–3.74 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | c2 | 1 | 3.94 | 3.94–3.94 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cm150a | 1 | 4.09 | 4.09–4.09 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cm151a | 1 | 5.52 | 5.52–5.52 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cm163a | 1 | 5.43 | 5.43–5.43 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cu | 1 | 5.51 | 5.51–5.51 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | dk17 | 1 | 4.99 | 4.99–4.99 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | dk27 | 1 | 5.07 | 5.07–5.07 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | example2 | 1 | 2.52 | 2.52–2.52 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | mlp4 | 1 | 3.39 | 3.39–3.39 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | mod5adder | 1 | 3.72 | 3.72–3.72 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | pcler8 | 1 | 5.03 | 5.03–5.03 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | rd73 | 1 | 2.97 | 2.97–2.97 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | rd84 | 1 | 3.08 | 3.08–3.08 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | sym9 | 1 | 4.21 | 4.21–4.21 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | 5xp1 | 1 | 3.70 | 3.70–3.70 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | C7552 | 1 | 3.00 | 3.00–3.00 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | add6 | 1 | 2.35 | 2.35–2.35 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | alu1 | 1 | 4.90 | 4.90–4.90 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | apla | 1 | 3.95 | 3.95–3.95 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | c2 | 1 | 4.49 | 4.49–4.49 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cm150a | 1 | 3.85 | 3.85–3.85 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cm151a | 1 | 5.18 | 5.18–5.18 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cm163a | 1 | 5.06 | 5.06–5.06 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cu | 1 | 5.18 | 5.18–5.18 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | dk17 | 1 | 4.66 | 4.66–4.66 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | dk27 | 1 | 4.41 | 4.41–4.41 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | example2 | 1 | 2.51 | 2.51–2.51 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | mlp4 | 1 | 3.29 | 3.29–3.29 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | mod5adder | 1 | 4.87 | 4.87–4.87 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | pcler8 | 1 | 4.69 | 4.69–4.69 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | rd73 | 1 | 4.34 | 4.34–4.34 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | rd84 | 1 | 4.40 | 4.40–4.40 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | sym9 | 1 | 4.72 | 4.72–4.72 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | 5xp1 | 1 | 3.14 | 3.14–3.14 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | C7552 | 1 | 2.17 | 2.17–2.17 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | add6 | 1 | 4.21 | 4.21–4.21 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | alu1 | 1 | 2.76 | 2.76–2.76 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | apla | 1 | 3.40 | 3.40–3.40 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | c2 | 1 | 3.63 | 3.63–3.63 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cm150a | 1 | 4.17 | 4.17–4.17 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cm151a | 1 | 3.47 | 3.47–3.47 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cm163a | 1 | 3.24 | 3.24–3.24 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cu | 1 | 3.73 | 3.73–3.73 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | dk17 | 1 | 3.55 | 3.55–3.55 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | dk27 | 1 | 3.36 | 3.36–3.36 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | example2 | 1 | 3.33 | 3.33–3.33 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | mlp4 | 1 | 3.30 | 3.30–3.30 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | mod5adder | 1 | 3.50 | 3.50–3.50 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | pcler8 | 1 | 3.54 | 3.54–3.54 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | rd73 | 1 | 4.41 | 4.41–4.41 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | rd84 | 1 | 4.78 | 4.78–4.78 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | sym9 | 1 | 7.12 | 7.12–7.12 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | 5xp1 | 1 | 8.64 | 8.64–8.64 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | C7552 | 1 | 8.27 | 8.27–8.27 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | add6 | 1 | 3.80 | 3.80–3.80 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | alu1 | 1 | 8.90 | 8.90–8.90 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | apla | 1 | 8.51 | 8.51–8.51 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | c2 | 1 | 4.33 | 4.33–4.33 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cm150a | 1 | 8.75 | 8.75–8.75 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cm151a | 1 | 16.02 | 16.02–16.02 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cm163a | 1 | 12.76 | 12.76–12.76 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cu | 1 | 12.18 | 12.18–12.18 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | dk17 | 1 | 11.26 | 11.26–11.26 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | dk27 | 1 | 12.71 | 12.71–12.71 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | example2 | 1 | 3.82 | 3.82–3.82 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | mlp4 | 1 | 8.42 | 8.42–8.42 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | mod5adder | 1 | 7.90 | 7.90–7.90 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | pcler8 | 1 | 12.79 | 12.79–12.79 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | rd73 | 1 | 6.47 | 6.47–6.47 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | rd84 | 1 | 4.91 | 4.91–4.91 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | sym9 | 1 | 5.90 | 5.90–5.90 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | 5xp1 | 1 | 2.74 | 2.74–2.74 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | C7552 | 1 | 2.90 | 2.90–2.90 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | add6 | 1 | 4.17 | 4.17–4.17 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | alu1 | 1 | 4.04 | 4.04–4.04 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | apla | 1 | 2.58 | 2.58–2.58 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | c2 | 1 | 1.80 | 1.80–1.80 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cm150a | 1 | 2.49 | 2.49–2.49 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cm151a | 1 | 3.97 | 3.97–3.97 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cm163a | 1 | 3.65 | 3.65–3.65 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cu | 1 | 3.46 | 3.46–3.46 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | dk17 | 1 | 2.82 | 2.82–2.82 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | dk27 | 1 | 4.92 | 4.92–4.92 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | example2 | 1 | 1.71 | 1.71–1.71 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | mlp4 | 1 | 2.99 | 2.99–2.99 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | mod5adder | 1 | 3.97 | 3.97–3.97 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | pcler8 | 1 | 3.78 | 3.78–3.78 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | rd73 | 1 | 5.35 | 5.35–5.35 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | rd84 | 1 | 5.93 | 5.93–5.93 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | sym9 | 1 | 7.66 | 7.66–7.66 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | 5xp1 | 1 | 2.73 | 2.73–2.73 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | C7552 | 1 | 3.49 | 3.49–3.49 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | add6 | 1 | 4.50 | 4.50–4.50 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | alu1 | 1 | 3.54 | 3.54–3.54 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | apla | 1 | 2.71 | 2.71–2.71 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | c2 | 1 | 1.65 | 1.65–1.65 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cm150a | 1 | 2.59 | 2.59–2.59 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cm151a | 1 | 3.98 | 3.98–3.98 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cm163a | 1 | 3.15 | 3.15–3.15 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cu | 1 | 3.22 | 3.22–3.22 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | dk17 | 1 | 2.75 | 2.75–2.75 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | dk27 | 1 | 3.65 | 3.65–3.65 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | example2 | 1 | 1.69 | 1.69–1.69 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | mlp4 | 1 | 2.87 | 2.87–2.87 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | mod5adder | 1 | 3.75 | 3.75–3.75 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | pcler8 | 1 | 3.89 | 3.89–3.89 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | rd73 | 1 | 5.04 | 5.04–5.04 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | rd84 | 1 | 6.09 | 6.09–6.09 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | sym9 | 1 | 7.16 | 7.16–7.16 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | 5xp1 | 1 | 9.40 | 9.40–9.40 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | C7552 | 1 | 11.09 | 11.09–11.09 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | add6 | 1 | 3.18 | 3.18–3.18 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | alu1 | 1 | 7.40 | 7.40–7.40 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | apla | 1 | 39.20 | 39.20–39.20 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | c2 | 1 | 730.05 | 730.05–730.05 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cm150a | 1 | 6.83 | 6.83–6.83 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cm151a | 1 | 13.27 | 13.27–13.27 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cm163a | 1 | 9.06 | 9.06–9.06 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cu | 1 | 18.78 | 18.78–18.78 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | dk17 | 1 | 38.69 | 38.69–38.69 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | dk27 | 1 | 17.15 | 17.15–17.15 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | example2 | 1 | 2.96 | 2.96–2.96 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | mlp4 | 1 | 7.04 | 7.04–7.04 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | mod5adder | 1 | 7.55 | 7.55–7.55 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | pcler8 | 1 | 9.25 | 9.25–9.25 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | rd73 | 1 | 8.73 | 8.73–8.73 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | rd84 | 1 | 8.35 | 8.35–8.35 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | sym9 | 1 | 10.22 | 10.22–10.22 | 0 | 0 |
