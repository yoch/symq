# Matched-driver benchmark — corpus `blind`

symq `23469829a0dcadf3503e5d60607e5fb0364ec190` (dirty: False), native extension SHA-256 `2e3f67910a34cfc0…`, Ubuntu clang version 18.1.3 (1ubuntu1), 3.12.3, Intel(R) Xeon(R) Processor (4 vCPU), started 2026-10-27T15:06:21Z.

Ratios are paired per circuit: baseline time / candidate time (> 1: candidate faster). Geometric mean with a 95% bootstrap interval over circuits, median, range and wins. `n` counts circuits both sides completed; one-sided completions are listed.

## Correctness

- Output groups checked: 70; fingerprint disagreements: 3; wrong verdicts: 0; invalid witnesses: 0.

| mode | killed | not_applicable | ok | timeout | timeout_censored |
|---|---:|---:|---:|---:|---:|
| `cudd-bdd-static/loop` | 0 | 0 | 63 | 12 | 15 |
| `cudd-bdd/loop` | 0 | 0 | 71 | 6 | 13 |
| `polybori/algebra` | 0 | 0 | 46 | 12 | 32 |
| `polybori/loop` | 0 | 0 | 46 | 12 | 32 |
| `polybori/loop-sorted` | 0 | 0 | 46 | 12 | 32 |
| `qcec` | 0 | 30 | 51 | 5 | 4 |
| `sparse/algebra` | 6 | 0 | 45 | 7 | 32 |
| `zdd-native/algebra` | 0 | 0 | 46 | 13 | 31 |
| `zdd-native/fused` | 4 | 0 | 48 | 11 | 27 |
| `zdd-native/loop` | 0 | 0 | 46 | 12 | 32 |
| `zdd-native/loop-sorted` | 1 | 0 | 46 | 13 | 30 |
| `zdd-python/algebra` | 0 | 0 | 42 | 12 | 36 |

## E1 — ablation of the native engine

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | compute | 13 | 6.21 [4.75, 8.38] | 5.68 | 2.79–18.01 | 13 | 1 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | end_to_end | 13 | 5.93 [4.49, 8.13] | 5.14 | 2.60–17.94 | 13 | 1 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | warm:compute | 13 | 1.23 [1.17, 1.30] | 1.18 | 1.11–1.45 | 13 | 1 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | compute | 14 | 7.39 [6.04, 8.93] | 7.80 | 3.87–13.72 | 14 | 2 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | end_to_end | 14 | 7.28 [5.74, 9.24] | 7.68 | 3.56–19.33 | 14 | 2 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | warm:compute | 14 | 1.20 [1.13, 1.28] | 1.18 | 0.99–1.51 | 13 | 2 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | compute | 15 | 7.34 [5.95, 9.08] | 7.17 | 3.77–16.34 | 15 | 1 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | end_to_end | 15 | 6.90 [5.49, 8.66] | 7.17 | 3.32–16.13 | 15 | 1 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | warm:compute | 14 | 1.21 [1.16, 1.28] | 1.17 | 1.09–1.48 | 14 | 1 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | compute | 14 | 1.65 [1.37, 1.98] | 1.62 | 1.01–2.75 | 14 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | end_to_end | 14 | 1.54 [1.32, 1.77] | 1.55 | 1.01–2.30 | 14 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | warm:compute | 14 | 3.22 [2.87, 3.56] | 3.48 | 2.15–4.06 | 14 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | compute | 16 | 1.45 [1.22, 1.72] | 1.42 | 0.94–2.52 | 13 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | end_to_end | 16 | 1.38 [1.19, 1.59] | 1.39 | 0.94–2.07 | 13 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | warm:compute | 14 | 3.17 [2.81, 3.54] | 3.48 | 2.03–4.01 | 14 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | compute | 16 | 1.45 [1.20, 1.75] | 1.37 | 0.82–2.85 | 12 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | end_to_end | 16 | 1.33 [1.15, 1.52] | 1.34 | 0.82–2.06 | 12 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | warm:compute | 15 | 3.22 [2.87, 3.56] | 3.48 | 2.08–4.04 | 15 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | compute | 14 | 0.92 [0.88, 0.96] | 0.94 | 0.76–1.06 | 2 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | end_to_end | 14 | 0.94 [0.90, 0.98] | 0.94 | 0.76–1.07 | 3 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | warm:compute | 14 | 0.80 [0.77, 0.82] | 0.82 | 0.67–0.86 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | compute | 16 | 0.95 [0.89, 1.01] | 0.97 | 0.70–1.14 | 7 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | end_to_end | 16 | 0.95 [0.88, 1.01] | 0.97 | 0.69–1.14 | 7 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | warm:compute | 14 | 0.82 [0.79, 0.84] | 0.81 | 0.75–0.88 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | compute | 16 | 0.92 [0.89, 0.96] | 0.91 | 0.82–1.12 | 2 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | end_to_end | 16 | 0.93 [0.88, 0.98] | 0.93 | 0.71–1.15 | 3 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | warm:compute | 15 | 0.82 [0.80, 0.84] | 0.84 | 0.75–0.93 | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | compute | 14 | 1.12 [0.99, 1.30] | 1.05 | 0.80–1.90 | 10 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | end_to_end | 14 | 1.11 [0.98, 1.27] | 1.04 | 0.77–1.77 | 10 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | warm:compute | 14 | 1.48 [1.25, 1.79] | 1.33 | 0.92–3.05 | 13 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | compute | 16 | 1.12 [1.01, 1.27] | 1.05 | 0.84–1.91 | 10 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | end_to_end | 16 | 1.11 [1.00, 1.25] | 1.03 | 0.84–1.86 | 9 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | warm:compute | 14 | 1.36 [1.12, 1.68] | 1.14 | 0.85–3.16 | 12 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | compute | 16 | 1.55 [1.26, 1.92] | 1.32 | 0.93–2.97 | 14 | 2 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | end_to_end | 16 | 1.39 [1.20, 1.61] | 1.31 | 0.93–2.28 | 14 | 2 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | warm:compute | 15 | 8.46 [7.83, 9.14] | 8.01 | 6.53–10.90 | 15 | 2 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | compute | 13 | 10.99 [9.08, 13.35] | 11.43 | 6.45–22.94 | 13 | 1 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | end_to_end | 13 | 9.75 [7.96, 12.06] | 9.19 | 5.32–21.56 | 13 | 1 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | warm:compute | 13 | 4.64 [4.10, 5.37] | 4.30 | 3.39–8.02 | 13 | 1 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | compute | 14 | 12.07 [9.68, 15.29] | 11.83 | 6.73–32.38 | 14 | 2 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | end_to_end | 14 | 10.96 [8.54, 14.70] | 9.79 | 6.68–40.11 | 14 | 2 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | warm:compute | 14 | 4.22 [3.57, 5.05] | 4.12 | 2.52–8.58 | 14 | 2 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | compute | 15 | 16.11 [11.83, 21.77] | 21.82 | 6.28–43.30 | 15 | 3 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | end_to_end | 15 | 12.35 [9.78, 15.86] | 13.09 | 6.28–37.93 | 15 | 3 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | warm:compute | 14 | 26.72 [24.08, 29.50] | 27.35 | 20.42–34.49 | 14 | 3 | 0 |

## E2 — matched drivers against native baselines

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/loop` | `polybori/loop` | equiv | compute | 14 | 3.34 [2.15, 4.96] | 4.14 | 0.60–15.67 | 12 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | end_to_end | 14 | 15.77 [5.73, 40.11] | 16.09 | 0.61–228.46 | 12 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | warm:compute | 14 | 15.93 [3.68, 99.96] | 3.06 | 1.72–21606.88 | 14 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | compute | 15 | 3.00 [1.94, 4.22] | 4.07 | 0.28–6.12 | 14 | 1 | 1 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | end_to_end | 15 | 12.94 [5.13, 30.58] | 18.57 | 0.29–137.27 | 14 | 1 | 1 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | warm:compute | 14 | 8.17 [2.81, 33.31] | 2.74 | 1.81–6981.74 | 14 | 1 | 1 |
| `zdd-native/loop` | `polybori/loop` | simulate | compute | 15 | 3.47 [2.23, 5.04] | 5.35 | 0.49–7.47 | 13 | 1 | 1 |
| `zdd-native/loop` | `polybori/loop` | simulate | end_to_end | 15 | 18.27 [6.57, 48.00] | 25.40 | 0.49–231.28 | 13 | 1 | 1 |
| `zdd-native/loop` | `polybori/loop` | simulate | warm:compute | 15 | 16.24 [4.08, 87.27] | 3.40 | 1.68–28252.60 | 15 | 1 | 1 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | compute | 14 | 3.30 [2.12, 4.70] | 4.53 | 0.55–6.42 | 12 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | end_to_end | 14 | 15.04 [5.52, 38.18] | 17.14 | 0.56–260.77 | 12 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | warm:compute | 14 | 24.52 [5.45, 148.70] | 3.62 | 2.44–16684.43 | 14 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | compute | 15 | 3.73 [2.28, 5.50] | 4.41 | 0.28–13.04 | 14 | 1 | 1 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | end_to_end | 15 | 13.67 [5.64, 31.10] | 12.66 | 0.29–134.39 | 14 | 1 | 1 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | warm:compute | 14 | 23.85 [5.77, 114.65] | 4.76 | 2.47–5280.18 | 14 | 1 | 1 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | compute | 15 | 3.98 [2.46, 5.89] | 5.79 | 0.46–9.69 | 13 | 1 | 1 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | end_to_end | 15 | 21.50 [7.41, 60.16] | 31.38 | 0.46–407.39 | 13 | 1 | 1 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | warm:compute | 15 | 37.94 [7.98, 218.17] | 4.62 | 2.16–24970.97 | 15 | 1 | 1 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | compute | 14 | 3.10 [2.07, 4.31] | 3.56 | 0.59–8.85 | 12 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | end_to_end | 14 | 12.73 [5.22, 28.24] | 14.45 | 0.59–106.10 | 12 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | warm:compute | 14 | 20.85 [4.84, 117.75] | 3.21 | 1.87–7199.82 | 14 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | compute | 15 | 3.78 [2.21, 6.13] | 3.71 | 0.26–21.99 | 14 | 1 | 1 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | end_to_end | 15 | 13.51 [5.72, 29.29] | 17.07 | 0.27–193.90 | 14 | 1 | 1 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | warm:compute | 14 | 20.25 [4.92, 97.31] | 3.99 | 1.93–4484.42 | 14 | 1 | 1 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | compute | 15 | 3.80 [2.38, 5.71] | 4.49 | 0.50–12.51 | 13 | 1 | 1 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | end_to_end | 15 | 19.09 [7.41, 45.92] | 21.49 | 0.50–274.71 | 13 | 1 | 1 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | warm:compute | 15 | 29.49 [6.55, 155.61] | 3.52 | 1.89–8421.27 | 15 | 1 | 1 |
| `zdd-native/fused` | `polybori/best` | equiv | compute | 14 | 3.25 [2.03, 4.84] | 4.25 | 0.57–8.00 | 12 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | end_to_end | 14 | 15.02 [5.52, 36.36] | 24.64 | 0.59–100.43 | 12 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | warm:compute | 14 | 17.47 [4.01, 110.13] | 4.27 | 1.34–26260.06 | 14 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | compute | 15 | 3.16 [1.97, 4.65] | 3.79 | 0.27–8.19 | 14 | 1 | 1 |
| `zdd-native/fused` | `polybori/best` | nonequiv | end_to_end | 15 | 12.56 [4.94, 30.07] | 19.33 | 0.28–129.43 | 14 | 1 | 1 |
| `zdd-native/fused` | `polybori/best` | nonequiv | warm:compute | 14 | 9.00 [3.14, 35.20] | 4.16 | 1.35–6118.48 | 14 | 1 | 1 |
| `zdd-native/fused` | `polybori/best` | simulate | compute | 15 | 5.03 [2.78, 8.52] | 9.20 | 0.49–15.26 | 13 | 3 | 1 |
| `zdd-native/fused` | `polybori/best` | simulate | end_to_end | 15 | 23.44 [7.52, 68.99] | 34.39 | 0.49–323.10 | 13 | 3 | 1 |
| `zdd-native/fused` | `polybori/best` | simulate | warm:compute | 15 | 112.15 [27.10, 626.06] | 21.42 | 9.41–231420.52 | 15 | 3 | 1 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | compute | 14 | 1.08 [0.34, 2.91] | 3.43 | 0.02–12.26 | 9 | 0 | 9 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | end_to_end | 14 | 4.87 [1.03, 18.97] | 10.69 | 0.02–88.34 | 10 | 0 | 9 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | warm:compute | 14 | 4.87 [3.46, 7.45] | 4.08 | 2.25–41.03 | 14 | 0 | 9 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | compute | 16 | 0.64 [0.13, 2.31] | 3.18 | 0.00–13.12 | 9 | 0 | 8 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | end_to_end | 16 | 2.58 [0.36, 13.54] | 11.01 | 0.00–142.67 | 10 | 0 | 8 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | warm:compute | 14 | 3.87 [2.77, 6.05] | 3.34 | 1.50–38.15 | 14 | 0 | 8 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | compute | 16 | 0.69 [0.15, 2.41] | 3.65 | 0.00–13.22 | 9 | 0 | 8 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | end_to_end | 16 | 3.68 [0.50, 20.48] | 15.17 | 0.00–163.68 | 10 | 0 | 8 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | warm:compute | 15 | 4.69 [3.29, 7.04] | 3.70 | 1.92–38.06 | 15 | 0 | 8 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | compute | 14 | 1.38 [0.41, 3.60] | 3.71 | 0.01–10.47 | 10 | 0 | 7 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | end_to_end | 14 | 6.66 [1.34, 25.30] | 13.40 | 0.01–130.33 | 11 | 0 | 7 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | warm:compute | 14 | 8.37 [4.10, 21.00] | 5.20 | 2.46–738.22 | 14 | 0 | 7 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | compute | 15 | 1.32 [0.29, 4.07] | 3.84 | 0.00–14.27 | 11 | 1 | 6 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | end_to_end | 15 | 7.34 [1.18, 30.82] | 18.23 | 0.00–196.98 | 12 | 1 | 6 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | warm:compute | 14 | 11.56 [4.52, 35.94] | 5.14 | 2.66–1017.15 | 14 | 1 | 6 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | compute | 15 | 1.63 [0.45, 4.52] | 3.96 | 0.00–12.04 | 11 | 1 | 6 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | end_to_end | 15 | 10.60 [2.19, 40.08] | 20.62 | 0.01–260.96 | 12 | 1 | 6 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | warm:compute | 15 | 12.77 [5.10, 38.22] | 5.84 | 2.56–1029.80 | 15 | 1 | 6 |
| `zdd-native/fused` | `sparse/algebra` | equiv | compute | 13 | 5.82 [4.23, 8.46] | 5.25 | 2.68–25.22 | 13 | 1 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | end_to_end | 13 | 5.20 [3.73, 7.71] | 4.80 | 2.57–25.18 | 13 | 1 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | warm:compute | 13 | 74.98 [15.19, 516.62] | 14.35 | 6.35–90283.56 | 13 | 1 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | compute | 15 | 4.41 [3.26, 6.02] | 4.44 | 1.46–16.33 | 15 | 1 | 1 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | end_to_end | 15 | 3.90 [2.90, 5.39] | 3.52 | 1.42–15.97 | 15 | 1 | 1 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | warm:compute | 14 | 76.27 [19.00, 363.97] | 17.60 | 6.43–27819.02 | 14 | 1 | 1 |
| `zdd-native/fused` | `sparse/algebra` | simulate | compute | 15 | 4.41 [2.69, 6.86] | 5.46 | 0.67–15.71 | 13 | 3 | 1 |
| `zdd-native/fused` | `sparse/algebra` | simulate | end_to_end | 15 | 3.41 [2.25, 5.01] | 4.39 | 0.67–15.68 | 13 | 3 | 1 |
| `zdd-native/fused` | `sparse/algebra` | simulate | warm:compute | 14 | 422.12 [93.80, 2283.15] | 81.43 | 31.91–222033.79 | 14 | 3 | 1 |

## MQT QCEC (verdicts only)

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/fused` | `qcec` | equiv | compute | 14 | 6.97 [1.01, 35.22] | 36.11 | 0.01–200.28 | 10 | 0 | 14 |
| `zdd-native/fused` | `qcec` | equiv | end_to_end | 14 | 5.32 [0.84, 25.09] | 30.28 | 0.01–68.31 | 10 | 0 | 14 |
| `zdd-native/fused` | `qcec` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 14 |
| `zdd-native/fused` | `qcec` | nonequiv | compute | 16 | 4.64 [0.48, 30.33] | 16.11 | 0.00–212.75 | 13 | 0 | 7 |
| `zdd-native/fused` | `qcec` | nonequiv | end_to_end | 16 | 3.50 [0.38, 22.21] | 17.33 | 0.00–81.15 | 13 | 0 | 7 |
| `zdd-native/fused` | `qcec` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 7 |

## E2 by family (compute phase, simulate)

| candidate | baseline | family | n | geomean | range | only cand. | only base. |
|---|---|---|---:|---:|---|---:|---:|
| `zdd-native/loop` | `polybori/loop` | adder | 3 | 5.10 | 2.94–7.34 | 1 | 0 |
| `zdd-native/loop` | `polybori/loop` | cadder | 3 | 4.00 | 2.58–6.47 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | incr | 4 | 5.61 | 5.35–6.07 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | mult | 4 | 2.24 | 0.49–7.47 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | rand | 1 | 0.60 | 0.60–0.60 | 0 | 1 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | adder | 3 | 5.97 | 4.01–8.54 | 1 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cadder | 3 | 5.82 | 4.45–6.86 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | incr | 4 | 5.84 | 5.40–6.26 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | mult | 4 | 2.45 | 0.46–9.69 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | rand | 1 | 0.57 | 0.57–0.57 | 0 | 1 |
| `zdd-native/algebra` | `polybori/algebra` | adder | 3 | 7.86 | 3.81–12.51 | 1 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cadder | 3 | 6.37 | 4.49–8.24 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | incr | 4 | 4.42 | 3.86–4.71 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | mult | 4 | 2.00 | 0.50–4.45 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | rand | 1 | 0.66 | 0.66–0.66 | 0 | 1 |
| `zdd-native/fused` | `polybori/best` | adder | 3 | 7.21 | 2.54–15.26 | 1 | 0 |
| `zdd-native/fused` | `polybori/best` | cadder | 3 | 5.48 | 2.39–13.55 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | incr | 4 | 12.44 | 9.20–14.05 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | mult | 4 | 2.50 | 0.49–12.19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | rand | 1 | 0.58 | 0.58–0.58 | 2 | 1 |
| `zdd-native/loop` | `cudd-bdd/loop` | adder | 4 | 0.25 | 0.00–13.22 | 0 | 1 |
| `zdd-native/loop` | `cudd-bdd/loop` | cadder | 3 | 1.23 | 0.09–6.11 | 0 | 2 |
| `zdd-native/loop` | `cudd-bdd/loop` | incr | 4 | 4.06 | 3.75–4.37 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | mult | 4 | 0.23 | 0.02–3.84 | 0 | 1 |
| `zdd-native/loop` | `cudd-bdd/loop` | rand | 1 | 0.47 | 0.47–0.47 | 0 | 4 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | adder | 3 | 9.47 | 7.19–12.04 | 1 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cadder | 3 | 5.00 | 3.96–6.82 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | incr | 4 | 3.90 | 3.83–3.97 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | mult | 4 | 0.15 | 0.00–5.31 | 0 | 2 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | rand | 1 | 0.13 | 0.13–0.13 | 0 | 4 |
| `zdd-native/fused` | `sparse/algebra` | adder | 4 | 2.64 | 0.67–10.14 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cadder | 3 | 2.62 | 0.88–8.23 | 0 | 1 |
| `zdd-native/fused` | `sparse/algebra` | incr | 4 | 8.17 | 5.46–10.52 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | mult | 3 | 7.65 | 4.76–15.71 | 1 | 0 |
| `zdd-native/fused` | `sparse/algebra` | rand | 1 | 2.68 | 2.68–2.68 | 2 | 0 |
