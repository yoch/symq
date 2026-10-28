# Matched-driver benchmark — corpus `qcec`

symq `23469829a0dcadf3503e5d60607e5fb0364ec190` (dirty: False), native extension SHA-256 `2e3f67910a34cfc0…`, Ubuntu clang version 18.1.3 (1ubuntu1), 3.12.3, Intel(R) Xeon(R) Processor (4 vCPU), started 2026-10-27T15:06:21Z.

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
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | compute | 19 | 4.16 [3.33, 5.40] | 3.99 | 1.58–20.78 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | end_to_end | 19 | 3.98 [3.15, 5.20] | 3.87 | 1.41–20.31 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | equiv | warm:compute | 19 | 1.20 [1.17, 1.23] | 1.22 | 1.09–1.39 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | compute | 19 | 3.91 [3.12, 4.76] | 4.19 | 0.85–8.74 | 18 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | end_to_end | 19 | 3.73 [2.95, 4.56] | 4.04 | 0.75–8.49 | 18 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | nonequiv | warm:compute | 19 | 1.13 [0.99, 1.23] | 1.21 | 0.37–1.30 | 18 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | compute | 19 | 4.92 [4.37, 5.56] | 4.97 | 3.00–7.85 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | end_to_end | 19 | 4.56 [4.04, 5.17] | 4.82 | 2.91–7.58 | 19 | 0 | 0 |
| `zdd-native/algebra` | `zdd-python/algebra` | simulate | warm:compute | 19 | 1.23 [1.20, 1.25] | 1.22 | 1.13–1.34 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | compute | 19 | 2.13 [1.84, 2.49] | 2.08 | 1.34–5.00 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | end_to_end | 19 | 1.93 [1.70, 2.19] | 1.82 | 1.33–3.98 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | equiv | warm:compute | 19 | 3.39 [3.26, 3.52] | 3.34 | 2.83–3.85 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | compute | 19 | 2.47 [2.12, 3.01] | 2.46 | 1.32–10.54 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | end_to_end | 19 | 2.19 [1.91, 2.65] | 2.08 | 1.31–9.61 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | nonequiv | warm:compute | 19 | 3.61 [3.25, 4.18] | 3.46 | 2.75–11.52 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | compute | 19 | 2.18 [1.99, 2.37] | 2.23 | 1.36–2.81 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | end_to_end | 19 | 1.90 [1.80, 2.00] | 1.96 | 1.35–2.26 | 19 | 0 | 0 |
| `zdd-native/loop` | `zdd-native/algebra` | simulate | warm:compute | 19 | 3.34 [3.17, 3.53] | 3.38 | 2.72–3.98 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | compute | 19 | 0.89 [0.83, 0.95] | 0.90 | 0.55–1.25 | 2 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | end_to_end | 19 | 0.91 [0.84, 0.98] | 0.89 | 0.56–1.35 | 5 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | equiv | warm:compute | 19 | 0.82 [0.81, 0.83] | 0.83 | 0.77–0.86 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | compute | 19 | 0.91 [0.88, 0.95] | 0.92 | 0.79–1.14 | 3 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | end_to_end | 19 | 0.93 [0.90, 0.96] | 0.93 | 0.81–1.13 | 3 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | nonequiv | warm:compute | 19 | 0.81 [0.80, 0.82] | 0.81 | 0.71–0.86 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | compute | 19 | 0.85 [0.81, 0.90] | 0.87 | 0.65–1.00 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | end_to_end | 19 | 0.86 [0.82, 0.90] | 0.89 | 0.66–0.99 | 0 | 0 | 0 |
| `zdd-native/loop-sorted` | `zdd-native/loop` | simulate | warm:compute | 19 | 0.78 [0.73, 0.82] | 0.81 | 0.55–0.88 | 0 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | compute | 19 | 1.13 [1.05, 1.21] | 1.10 | 0.84–1.63 | 17 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | end_to_end | 19 | 1.12 [1.06, 1.20] | 1.11 | 0.91–1.63 | 17 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | equiv | warm:compute | 19 | 1.28 [1.14, 1.44] | 1.19 | 0.81–1.99 | 16 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | compute | 19 | 1.10 [1.02, 1.19] | 1.05 | 0.78–1.50 | 15 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | end_to_end | 19 | 1.10 [1.03, 1.17] | 1.08 | 0.80–1.46 | 14 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | nonequiv | warm:compute | 19 | 1.27 [1.11, 1.46] | 1.20 | 0.79–2.25 | 16 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | compute | 19 | 1.14 [1.03, 1.27] | 1.07 | 0.80–1.81 | 13 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | end_to_end | 19 | 1.14 [1.04, 1.26] | 1.12 | 0.80–1.75 | 12 | 0 | 0 |
| `zdd-native/fused` | `zdd-native/loop-sorted` | simulate | warm:compute | 19 | 1.31 [1.12, 1.54] | 1.15 | 0.77–2.62 | 14 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | compute | 19 | 8.92 [7.90, 10.42] | 8.93 | 5.83–26.42 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | end_to_end | 19 | 7.84 [6.75, 9.37] | 8.05 | 4.40–25.49 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | equiv | warm:compute | 19 | 4.28 [3.96, 4.63] | 4.12 | 2.99–5.68 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | compute | 19 | 9.76 [8.68, 11.15] | 9.79 | 5.48–22.47 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | end_to_end | 19 | 8.31 [7.21, 9.67] | 8.80 | 4.13–20.99 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | nonequiv | warm:compute | 19 | 4.21 [3.78, 4.72] | 3.98 | 2.85–6.91 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | compute | 19 | 10.45 [9.39, 11.58] | 10.73 | 6.74–15.06 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | end_to_end | 19 | 8.56 [7.40, 9.76] | 9.76 | 4.21–12.06 | 19 | 0 | 0 |
| `zdd-native/fused` | `zdd-python/algebra` | simulate | warm:compute | 19 | 4.16 [3.75, 4.62] | 3.90 | 2.80–6.11 | 19 | 0 | 0 |

## E2 — matched drivers against native baselines

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/loop` | `polybori/loop` | equiv | compute | 19 | 2.98 [2.59, 3.42] | 3.06 | 1.76–4.70 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | end_to_end | 19 | 36.68 [22.01, 60.80] | 45.04 | 5.94–186.65 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | equiv | warm:compute | 19 | 2.12 [2.05, 2.18] | 2.15 | 1.84–2.39 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | compute | 19 | 3.28 [2.97, 3.61] | 3.16 | 2.21–4.54 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | end_to_end | 19 | 49.68 [34.43, 69.38] | 48.34 | 10.36–132.20 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | nonequiv | warm:compute | 19 | 2.15 [2.07, 2.24] | 2.22 | 1.80–2.42 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | compute | 19 | 4.16 [3.68, 4.67] | 4.13 | 2.22–5.92 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | end_to_end | 19 | 85.80 [57.06, 126.24] | 91.55 | 14.28–347.97 | 19 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | simulate | warm:compute | 19 | 2.11 [2.03, 2.19] | 2.15 | 1.79–2.37 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | compute | 19 | 3.00 [2.51, 3.48] | 3.53 | 0.94–4.31 | 18 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | end_to_end | 19 | 34.13 [21.18, 54.67] | 47.06 | 7.12–236.18 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | equiv | warm:compute | 19 | 2.67 [2.39, 3.05] | 2.43 | 1.98–5.75 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | compute | 19 | 3.64 [3.21, 4.10] | 3.85 | 2.07–6.43 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | end_to_end | 19 | 51.39 [36.14, 70.69] | 56.33 | 9.85–149.27 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | nonequiv | warm:compute | 19 | 2.57 [2.28, 2.97] | 2.28 | 1.83–5.48 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | compute | 19 | 4.01 [3.43, 4.57] | 4.44 | 1.58–5.63 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | end_to_end | 19 | 69.18 [48.11, 98.05] | 71.71 | 13.65–209.67 | 19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | simulate | warm:compute | 19 | 2.42 [2.12, 2.86] | 2.18 | 1.50–6.71 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | compute | 19 | 2.75 [2.46, 3.04] | 2.73 | 1.39–3.77 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | end_to_end | 19 | 19.21 [13.80, 26.74] | 18.63 | 6.15–84.11 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | equiv | warm:compute | 19 | 2.67 [2.17, 3.37] | 2.42 | 1.50–8.00 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | compute | 19 | 3.04 [2.46, 3.68] | 2.99 | 0.70–7.80 | 18 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | end_to_end | 19 | 29.35 [22.34, 38.65] | 30.40 | 9.49–112.04 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | nonequiv | warm:compute | 19 | 2.44 [1.87, 3.19] | 2.50 | 0.51–8.74 | 18 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | compute | 19 | 3.83 [3.44, 4.31] | 3.76 | 2.28–6.79 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | end_to_end | 19 | 56.02 [38.33, 80.89] | 55.60 | 12.10–245.59 | 19 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | simulate | warm:compute | 19 | 2.71 [2.20, 3.43] | 2.53 | 1.50–8.74 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | compute | 19 | 2.98 [2.59, 3.36] | 3.40 | 1.53–4.19 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | end_to_end | 19 | 31.03 [19.94, 47.58] | 46.79 | 5.96–155.69 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | equiv | warm:compute | 19 | 2.23 [1.95, 2.54] | 2.19 | 1.32–3.61 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | compute | 19 | 3.31 [3.12, 3.50] | 3.31 | 2.64–4.23 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | end_to_end | 19 | 47.60 [35.56, 61.99] | 55.46 | 12.27–109.85 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | nonequiv | warm:compute | 19 | 2.22 [1.89, 2.61] | 2.14 | 1.30–4.08 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | compute | 19 | 4.01 [3.67, 4.37] | 4.07 | 2.85–6.00 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | end_to_end | 19 | 71.30 [52.02, 95.84] | 82.75 | 17.87–171.87 | 19 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | simulate | warm:compute | 19 | 2.14 [1.83, 2.52] | 1.94 | 1.22–3.86 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | compute | 19 | 2.62 [2.16, 3.17] | 2.65 | 0.99–5.47 | 18 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | end_to_end | 19 | 21.03 [13.61, 32.31] | 27.29 | 4.46–89.04 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | equiv | warm:compute | 19 | 2.58 [2.37, 2.85] | 2.38 | 2.13–4.56 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | compute | 19 | 3.33 [2.77, 4.00] | 3.34 | 1.59–7.91 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | end_to_end | 19 | 32.58 [22.96, 45.26] | 36.37 | 6.77–86.34 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | nonequiv | warm:compute | 19 | 2.63 [2.35, 3.03] | 2.35 | 2.07–7.15 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | compute | 19 | 3.86 [3.08, 5.18] | 3.36 | 1.92–32.16 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | end_to_end | 19 | 57.81 [39.95, 81.88] | 57.09 | 11.42–264.68 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | simulate | warm:compute | 19 | 2.46 [2.27, 2.72] | 2.28 | 2.01–4.13 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | compute | 19 | 2.58 [2.11, 3.12] | 2.57 | 0.94–5.37 | 18 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | end_to_end | 19 | 22.21 [13.89, 35.79] | 24.22 | 4.65–147.69 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | equiv | warm:compute | 19 | 2.62 [2.41, 2.89] | 2.46 | 2.13–4.59 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | compute | 19 | 3.21 [2.77, 3.73] | 3.04 | 1.65–5.55 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | end_to_end | 19 | 33.78 [23.12, 48.43] | 40.68 | 7.38–174.26 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | nonequiv | warm:compute | 19 | 2.47 [2.31, 2.68] | 2.31 | 2.12–3.63 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | compute | 19 | 3.54 [2.99, 4.24] | 3.30 | 1.84–8.14 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | end_to_end | 19 | 53.81 [40.15, 71.45] | 55.01 | 12.58–178.90 | 19 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | simulate | warm:compute | 19 | 2.43 [2.25, 2.66] | 2.31 | 2.02–3.84 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | compute | 19 | 10.21 [5.15, 26.25] | 5.19 | 3.26–8447.76 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | end_to_end | 19 | 9.70 [4.80, 25.30] | 4.76 | 2.52–8104.24 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | equiv | warm:compute | 19 | 25.88 [11.58, 77.51] | 15.18 | 3.87–64284.61 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | compute | 19 | 7.74 [4.78, 15.27] | 4.68 | 2.72–1143.08 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | end_to_end | 19 | 6.53 [4.02, 12.96] | 4.02 | 2.47–1044.82 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | nonequiv | warm:compute | 19 | 14.03 [7.90, 31.54] | 8.23 | 3.98–5846.22 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | compute | 19 | 6.13 [3.89, 11.67] | 4.40 | 2.39–696.26 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | end_to_end | 19 | 4.95 [3.10, 9.57] | 3.35 | 1.72–638.92 | 19 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | simulate | warm:compute | 19 | 13.13 [7.51, 29.70] | 7.99 | 3.96–6097.09 | 19 | 0 | 0 |

## MQT QCEC (verdicts only)

| candidate | baseline | workload | phase | n | geomean [95% CI] | median | range | wins | only cand. | only base. |
|---|---|---|---|---:|---|---:|---|---:|---:|---:|
| `zdd-native/fused` | `qcec` | equiv | compute | 19 | 50.50 [30.76, 84.80] | 46.18 | 10.92–512.39 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | end_to_end | 19 | 32.50 [21.34, 50.63] | 36.12 | 7.43–422.77 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | equiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | compute | 19 | 64.96 [44.75, 93.36] | 53.42 | 12.57–283.92 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | end_to_end | 19 | 38.35 [27.49, 51.06] | 45.45 | 5.72–97.81 | 19 | 0 | 0 |
| `zdd-native/fused` | `qcec` | nonequiv | warm:compute | 0 | — | — | — | 0 | 0 | 0 |

## E2 by family (compute phase, simulate)

| candidate | baseline | family | n | geomean | range | only cand. | only base. |
|---|---|---|---:|---:|---|---:|---:|
| `zdd-native/loop` | `polybori/loop` | 5xp1 | 1 | 4.53 | 4.53–4.53 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | C7552 | 1 | 3.53 | 3.53–3.53 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | add6 | 1 | 2.22 | 2.22–2.22 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | alu1 | 1 | 5.43 | 5.43–5.43 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | apla | 1 | 3.94 | 3.94–3.94 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | c2 | 1 | 3.72 | 3.72–3.72 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cm150a | 1 | 4.13 | 4.13–4.13 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cm151a | 1 | 5.08 | 5.08–5.08 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cm163a | 1 | 5.46 | 5.46–5.46 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | cu | 1 | 5.92 | 5.92–5.92 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | dk17 | 1 | 5.82 | 5.82–5.82 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | dk27 | 1 | 5.15 | 5.15–5.15 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | example2 | 1 | 2.62 | 2.62–2.62 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | mlp4 | 1 | 3.43 | 3.43–3.43 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | mod5adder | 1 | 3.65 | 3.65–3.65 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | pcler8 | 1 | 5.92 | 5.92–5.92 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | rd73 | 1 | 4.15 | 4.15–4.15 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | rd84 | 1 | 3.31 | 3.31–3.31 | 0 | 0 |
| `zdd-native/loop` | `polybori/loop` | sym9 | 1 | 3.80 | 3.80–3.80 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | 5xp1 | 1 | 2.74 | 2.74–2.74 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | C7552 | 1 | 3.23 | 3.23–3.23 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | add6 | 1 | 1.58 | 1.58–1.58 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | alu1 | 1 | 4.78 | 4.78–4.78 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | apla | 1 | 3.76 | 3.76–3.76 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | c2 | 1 | 4.15 | 4.15–4.15 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cm150a | 1 | 4.74 | 4.74–4.74 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cm151a | 1 | 5.49 | 5.49–5.49 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cm163a | 1 | 5.22 | 5.22–5.22 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | cu | 1 | 5.05 | 5.05–5.05 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | dk17 | 1 | 4.98 | 4.98–4.98 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | dk27 | 1 | 5.02 | 5.02–5.02 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | example2 | 1 | 2.58 | 2.58–2.58 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | mlp4 | 1 | 3.08 | 3.08–3.08 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | mod5adder | 1 | 4.19 | 4.19–4.19 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | pcler8 | 1 | 5.42 | 5.42–5.42 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | rd73 | 1 | 3.52 | 3.52–3.52 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | rd84 | 1 | 4.44 | 4.44–4.44 | 0 | 0 |
| `zdd-native/loop-sorted` | `polybori/loop-sorted` | sym9 | 1 | 5.63 | 5.63–5.63 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | 5xp1 | 1 | 4.51 | 4.51–4.51 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | C7552 | 1 | 2.28 | 2.28–2.28 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | add6 | 1 | 4.28 | 4.28–4.28 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | alu1 | 1 | 3.07 | 3.07–3.07 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | apla | 1 | 3.08 | 3.08–3.08 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | c2 | 1 | 3.56 | 3.56–3.56 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cm150a | 1 | 3.76 | 3.76–3.76 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cm151a | 1 | 3.29 | 3.29–3.29 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cm163a | 1 | 3.40 | 3.40–3.40 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | cu | 1 | 4.06 | 4.06–4.06 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | dk17 | 1 | 3.50 | 3.50–3.50 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | dk27 | 1 | 3.11 | 3.11–3.11 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | example2 | 1 | 3.35 | 3.35–3.35 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | mlp4 | 1 | 6.32 | 6.32–6.32 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | mod5adder | 1 | 3.84 | 3.84–3.84 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | pcler8 | 1 | 3.77 | 3.77–3.77 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | rd73 | 1 | 4.37 | 4.37–4.37 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | rd84 | 1 | 4.86 | 4.86–4.86 | 0 | 0 |
| `zdd-native/algebra` | `polybori/algebra` | sym9 | 1 | 6.79 | 6.79–6.79 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | 5xp1 | 1 | 4.82 | 4.82–4.82 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | C7552 | 1 | 4.07 | 4.07–4.07 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | add6 | 1 | 2.85 | 2.85–2.85 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | alu1 | 1 | 3.93 | 3.93–3.93 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | apla | 1 | 4.64 | 4.64–4.64 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | c2 | 1 | 3.75 | 3.75–3.75 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cm150a | 1 | 4.20 | 4.20–4.20 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cm151a | 1 | 4.47 | 4.47–4.47 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cm163a | 1 | 5.00 | 5.00–5.00 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | cu | 1 | 5.02 | 5.02–5.02 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | dk17 | 1 | 6.00 | 6.00–6.00 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | dk27 | 1 | 3.60 | 3.60–3.60 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | example2 | 1 | 3.00 | 3.00–3.00 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | mlp4 | 1 | 4.60 | 4.60–4.60 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | mod5adder | 1 | 2.94 | 2.94–2.94 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | pcler8 | 1 | 4.18 | 4.18–4.18 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | rd73 | 1 | 3.74 | 3.74–3.74 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | rd84 | 1 | 3.24 | 3.24–3.24 | 0 | 0 |
| `zdd-native/fused` | `polybori/best` | sym9 | 1 | 3.54 | 3.54–3.54 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | 5xp1 | 1 | 3.00 | 3.00–3.00 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | C7552 | 1 | 3.55 | 3.55–3.55 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | add6 | 1 | 4.08 | 4.08–4.08 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | alu1 | 1 | 3.24 | 3.24–3.24 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | apla | 1 | 2.50 | 2.50–2.50 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | c2 | 1 | 1.98 | 1.98–1.98 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cm150a | 1 | 2.95 | 2.95–2.95 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cm151a | 1 | 3.80 | 3.80–3.80 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cm163a | 1 | 3.30 | 3.30–3.30 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | cu | 1 | 3.55 | 3.55–3.55 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | dk17 | 1 | 3.07 | 3.07–3.07 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | dk27 | 1 | 3.36 | 3.36–3.36 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | example2 | 1 | 1.92 | 1.92–1.92 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | mlp4 | 1 | 3.07 | 3.07–3.07 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | mod5adder | 1 | 4.00 | 4.00–4.00 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | pcler8 | 1 | 4.34 | 4.34–4.34 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | rd73 | 1 | 5.94 | 5.94–5.94 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | rd84 | 1 | 32.16 | 32.16–32.16 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd/loop` | sym9 | 1 | 7.40 | 7.40–7.40 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | 5xp1 | 1 | 3.20 | 3.20–3.20 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | C7552 | 1 | 3.07 | 3.07–3.07 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | add6 | 1 | 4.27 | 4.27–4.27 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | alu1 | 1 | 3.40 | 3.40–3.40 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | apla | 1 | 2.51 | 2.51–2.51 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | c2 | 1 | 1.84 | 1.84–1.84 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cm150a | 1 | 2.79 | 2.79–2.79 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cm151a | 1 | 4.23 | 4.23–4.23 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cm163a | 1 | 3.02 | 3.02–3.02 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | cu | 1 | 3.46 | 3.46–3.46 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | dk17 | 1 | 2.80 | 2.80–2.80 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | dk27 | 1 | 3.30 | 3.30–3.30 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | example2 | 1 | 1.91 | 1.91–1.91 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | mlp4 | 1 | 2.98 | 2.98–2.98 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | mod5adder | 1 | 3.68 | 3.68–3.68 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | pcler8 | 1 | 4.23 | 4.23–4.23 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | rd73 | 1 | 8.14 | 8.14–8.14 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | rd84 | 1 | 7.26 | 7.26–7.26 | 0 | 0 |
| `zdd-native/loop` | `cudd-bdd-static/loop` | sym9 | 1 | 6.70 | 6.70–6.70 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | 5xp1 | 1 | 4.53 | 4.53–4.53 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | C7552 | 1 | 5.44 | 5.44–5.44 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | add6 | 1 | 2.39 | 2.39–2.39 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | alu1 | 1 | 4.15 | 4.15–4.15 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | apla | 1 | 20.15 | 20.15–20.15 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | c2 | 1 | 696.26 | 696.26–696.26 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cm150a | 1 | 3.48 | 3.48–3.48 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cm151a | 1 | 3.69 | 3.69–3.69 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cm163a | 1 | 3.20 | 3.20–3.20 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | cu | 1 | 6.69 | 6.69–6.69 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | dk17 | 1 | 19.61 | 19.61–19.61 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | dk27 | 1 | 4.66 | 4.66–4.66 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | example2 | 1 | 2.39 | 2.39–2.39 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | mlp4 | 1 | 3.75 | 3.75–3.75 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | mod5adder | 1 | 2.83 | 2.83–2.83 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | pcler8 | 1 | 2.81 | 2.81–2.81 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | rd73 | 1 | 4.40 | 4.40–4.40 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | rd84 | 1 | 5.23 | 5.23–5.23 | 0 | 0 |
| `zdd-native/fused` | `sparse/algebra` | sym9 | 1 | 6.39 | 6.39–6.39 | 0 | 0 |
