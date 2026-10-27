# Benchmark report

- symq commit `b7f604567098da6c3b4b81ddbf1ab003a745fb25` (dirty: False), started 2026-10-27T13:56:51Z
- CPython 3.12.3 on Linux-6.12.94+-x86_64-with-glibc2.39
- CPU: Intel(R) Xeon(R) Processor (4 usable of 4), RAM 15.6 GiB
- Corpus: https://github.com/munich-quantum-toolkit/qcec @ `98d6784176bfeb6ef923d4d0220e8d486dc1982f`, manifest sha256 `d3771d0cba987d7f…`
- Protocol: 1 warmup + median of 7 timed runs per cell; time.perf_counter around one run, no instrumentation; tracemalloc peak from a separate untimed run; ru_maxrss of the worker; one fresh worker process per cell, cells run sequentially; per-run budget 60.0 s.
- Times are milliseconds. Sub-millisecond medians are sensitive to scheduling, GC and CPU frequency; no confidence interval is claimed.

## Correctness checks

- All backends that completed a cell produced identical output polynomials (simulate) or verdicts and differing output (equiv/nonequiv). No wrong verdict, no worker error.
- `qcec` gives verdicts only; they are checked against the expected verdict (`wrong_verdict` otherwise), not against output polynomials.

| backend | not_applicable | ok |
|---|---:|---:|
| `sparse-copy` | 0 | 57 |
| `sparse` | 0 | 57 |
| `zdd` | 0 | 57 |
| `zdd-native` | 0 | 57 |
| `auto-zdd` | 0 | 57 |
| `polybori` | 0 | 57 |
| `cudd-bdd` | 0 | 57 |
| `cudd-zdd` | 0 | 57 |
| `qcec` | 19 | 38 |

Rejected before benchmarking (outside the X/CX/CCX/MCX model):
- `c2_182`: unsupported statement: 'ctrl @ U(pi/2,-pi/2,pi/2) q[0], q[2]'

## Workload `simulate` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `zdd-native` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 154 | 156 | 2.72 | 0.25 | 4.34 | 0.327 | 4.51 | 12.1 | not_applicable |
| `mod5adder_306` | dev | 32 | 110 | 0.244 | 0.205 | 0.722 | 0.0541 | 0.242 | 0.284 | 5.29 | 6.59 | not_applicable |
| `rd73_312` | dev | 25 | 76 | 0.219 | 0.185 | 0.514 | 0.0445 | 0.214 | 0.256 | 3.1 | 4.29 | not_applicable |
| `rd84_313` | dev | 34 | 113 | 0.476 | 0.375 | 0.871 | 0.0675 | 0.402 | 0.506 | 3.67 | 20.1 | not_applicable |
| `sym9_317` | dev | 27 | 64 | 0.519 | 0.41 | 0.843 | 0.0607 | 0.429 | 0.554 | 3.17 | 15.5 | not_applicable |
| `5xp1_194` | holdout | 17 | 85 | 0.216 | 0.182 | 0.459 | 0.0473 | 0.214 | 0.192 | 2.42 | 6.25 | not_applicable |
| `alu1_198` | holdout | 20 | 32 | 0.0556 | 0.0489 | 0.127 | 0.0177 | 0.0662 | 0.0645 | 2.28 | 5.96 | not_applicable |
| `cm150a_210` | holdout | 22 | 53 | 0.194 | 0.14 | 0.565 | 0.0424 | 0.167 | 0.164 | 2.66 | 2.54 | not_applicable |
| `dk27_225` | holdout | 18 | 24 | 0.0681 | 0.0722 | 0.128 | 0.0154 | 0.0831 | 0.0518 | 1.98 | 5.19 | not_applicable |
| `mlp4_245` | holdout | 16 | 131 | 0.414 | 0.344 | 0.962 | 0.0796 | 0.388 | 0.436 | 3.04 | 8.17 | not_applicable |
| `pcler8_248` | holdout | 21 | 22 | 0.0468 | 0.0439 | 0.103 | 0.0153 | 0.0571 | 0.0591 | 2.03 | 5.32 | not_applicable |
| `C7552_205` | extension | 21 | 80 | 0.21 | 0.2 | 0.32 | 0.0321 | 0.231 | 0.183 | 4.55 | 7.12 | not_applicable |
| `add6_196` | extension | 19 | 229 | 1.25 | 0.705 | 2.61 | 0.234 | 0.761 | 1.55 | 8.69 | 15.2 | not_applicable |
| `apla_203` | extension | 22 | 80 | 1.53 | 1.28 | 1.09 | 0.0565 | 1.34 | 0.296 | 2.55 | 4.53 | not_applicable |
| `cm151a_211` | extension | 28 | 33 | 0.0943 | 0.144 | 0.195 | 0.0208 | 0.116 | 0.0911 | 2.69 | 2.92 | not_applicable |
| `cm163a_213` | extension | 29 | 39 | 0.0827 | 0.076 | 0.204 | 0.0217 | 0.103 | 0.0921 | 2.19 | 2.73 | not_applicable |
| `cu_219` | extension | 25 | 40 | 0.215 | 0.211 | 0.337 | 0.0283 | 0.223 | 0.106 | 2.23 | 2.6 | not_applicable |
| `dk17_224` | extension | 21 | 49 | 0.631 | 0.626 | 0.409 | 0.0359 | 0.755 | 0.169 | 2.54 | 6.7 | not_applicable |
| `example2_231` | extension | 16 | 157 | 0.883 | 0.542 | 2.11 | 0.203 | 0.593 | 0.774 | 3.66 | 9.03 | not_applicable |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.23×, geomean 1.23×, range 1.18–1.27× | 1.0× |
| `sparse` | holdout | n=6, median 1.16×, geomean 1.15×, range 0.94–1.39× | — |
| `sparse` | extension | n=8, median 1.07×, geomean 1.13×, range 0.65–1.77× | — |
| `zdd` | dev | n=4, median 0.49×, geomean 0.47×, range 0.34–0.61× | 56.8× |
| `zdd` | holdout | n=6, median 0.45×, geomean 0.44×, range 0.34–0.53× | — |
| `zdd` | extension | n=8, median 0.56×, geomean 0.66×, range 0.41–1.54× | — |
| `zdd-native` | dev | n=4, median 5.99×, geomean 6.05×, range 4.51–8.54× | 617.5× |
| `zdd-native` | holdout | n=6, median 4.50×, geomean 4.08×, range 3.06–5.20× | — |
| `zdd-native` | extension | n=8, median 5.93×, geomean 7.45×, range 3.82–27.09× | — |
| `auto-zdd` | dev | n=4, median 1.10×, geomean 1.10×, range 1.01–1.21× | 35.5× |
| `auto-zdd` | holdout | n=6, median 0.93×, geomean 0.94×, range 0.82–1.16× | — |
| `auto-zdd` | extension | n=8, median 0.94×, geomean 1.04×, range 0.80–1.64× | — |
| `polybori` | dev | n=4, median 0.90×, geomean 0.90×, range 0.86–0.94× | 471.1× |
| `polybori` | holdout | n=6, median 1.04×, geomean 1.02×, range 0.79–1.31× | — |
| `polybori` | extension | n=8, median 1.14×, geomean 1.58×, range 0.80–5.17× | — |
| `cudd-bdd` | dev | n=4, median 0.10×, geomean 0.09×, range 0.05–0.16× | 34.2× |
| `cudd-bdd` | holdout | n=6, median 0.05×, geomean 0.05×, range 0.02–0.14× | — |
| `cudd-bdd` | extension | n=8, median 0.12×, geomean 0.11×, range 0.04–0.60× | — |
| `cudd-zdd` | dev | n=4, median 0.04×, geomean 0.03×, range 0.02–0.05× | 12.8× |
| `cudd-zdd` | holdout | n=6, median 0.02×, geomean 0.02×, range 0.01–0.08× | — |
| `cudd-zdd` | extension | n=8, median 0.08×, geomean 0.07×, range 0.03–0.34× | — |

## Workload `equiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `zdd-native` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 4668 | 4409 | 5.43 | 0.523 | 8.73 | 0.942 | 14 | 28 | 6.76 |
| `mod5adder_306` | dev | 32 | 110 | 2.79 | 2.76 | 6.94 | 0.812 | 2.85 | 1.13 | 9.52 | 21.9 | 12.2 |
| `rd73_312` | dev | 25 | 76 | 0.569 | 0.46 | 0.855 | 0.085 | 0.513 | 0.602 | 8.13 | 12.4 | 43.8 |
| `rd84_313` | dev | 34 | 113 | 1.74 | 1.47 | 2.93 | 0.314 | 1.56 | 1.38 | 11.2 | 37.1 | 36 |
| `sym9_317` | dev | 27 | 64 | 2.91 | 2.64 | 4.67 | 0.481 | 2.69 | 1.27 | 8.43 | 24.9 | 5.33 |
| `5xp1_194` | holdout | 17 | 85 | 0.907 | 0.813 | 1.18 | 0.136 | 0.897 | 0.544 | 8.15 | 10.8 | 2.97 |
| `alu1_198` | holdout | 20 | 32 | 0.154 | 0.143 | 0.257 | 0.0344 | 0.171 | 0.154 | 5.64 | 6.95 | 3.93 |
| `cm150a_210` | holdout | 22 | 53 | 0.548 | 0.423 | 0.806 | 0.0722 | 0.466 | 0.343 | 5.73 | 6.89 | 2.93 |
| `dk27_225` | holdout | 18 | 24 | 0.164 | 0.161 | 0.158 | 0.026 | 0.19 | 0.106 | 5.25 | 5.83 | 3.09 |
| `mlp4_245` | holdout | 16 | 131 | 1.54 | 1.36 | 3.36 | 0.351 | 1.51 | 1.2 | 8.85 | 16.7 | 4.07 |
| `pcler8_248` | holdout | 21 | 22 | 0.0996 | 0.0954 | 0.157 | 0.0259 | 0.118 | 0.112 | 5.23 | 6.04 | 1.33 |
| `C7552_205` | extension | 21 | 80 | 0.555 | 0.525 | 0.648 | 0.0716 | 0.604 | 0.437 | 7.09 | 12.3 | 3.83 |
| `add6_196` | extension | 19 | 229 | 4.44 | 4.06 | 8.44 | 0.978 | 4.37 | 4.17 | 40.4 | 45.4 | 14.5 |
| `apla_203` | extension | 22 | 80 | 36.5 | 35.9 | 1.91 | 0.147 | 6.92 | 0.722 | 8.56 | 12.6 | 5.17 |
| `cm151a_211` | extension | 28 | 33 | 0.211 | 0.195 | 0.269 | 0.0368 | 0.234 | 0.198 | 5.53 | 7.92 | 2.83 |
| `cm163a_213` | extension | 29 | 39 | 0.223 | 0.203 | 0.327 | 0.0443 | 0.238 | 0.204 | 5.8 | 8.53 | 2.93 |
| `cu_219` | extension | 25 | 40 | 0.596 | 0.561 | 0.486 | 0.0495 | 0.628 | 0.242 | 5.68 | 8.03 | 2.9 |
| `dk17_224` | extension | 21 | 49 | 3.4 | 3.43 | 0.576 | 0.0548 | 3.5 | 0.311 | 5.96 | 7.99 | 3.41 |
| `example2_231` | extension | 16 | 157 | 2.95 | 2.26 | 4.09 | 0.423 | 2.42 | 1.85 | 9.94 | 19.4 | 6.95 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.14×, geomean 1.13×, range 1.01–1.24× | 1.1× |
| `sparse` | holdout | n=6, median 1.10×, geomean 1.11×, range 1.02–1.30× | — |
| `sparse` | extension | n=8, median 1.07×, geomean 1.09×, range 0.99–1.31× | — |
| `zdd` | dev | n=4, median 0.61×, geomean 0.56×, range 0.40–0.67× | 859.0× |
| `zdd` | holdout | n=6, median 0.66×, geomean 0.67×, range 0.46–1.03× | — |
| `zdd` | extension | n=8, median 0.82×, geomean 1.49×, range 0.53–19.10× | — |
| `zdd-native` | dev | n=4, median 5.79×, geomean 5.27×, range 3.44–6.70× | 8922.2× |
| `zdd-native` | holdout | n=6, median 5.39×, geomean 5.37×, range 3.85–7.59× | — |
| `zdd-native` | extension | n=8, median 7.36×, geomean 13.80×, range 4.54–247.85× | — |
| `auto-zdd` | dev | n=4, median 1.10×, geomean 1.07×, range 0.98–1.12× | 534.7× |
| `auto-zdd` | holdout | n=6, median 0.96×, geomean 0.96×, range 0.85–1.18× | — |
| `auto-zdd` | extension | n=8, median 0.96×, geomean 1.21×, range 0.90–5.27× | — |
| `polybori` | dev | n=4, median 1.78×, geomean 1.61×, range 0.95–2.47× | 4957.5× |
| `polybori` | holdout | n=6, median 1.41×, geomean 1.29×, range 0.89–1.67× | — |
| `polybori` | extension | n=8, median 1.43×, geomean 2.77×, range 1.07–50.55× | — |
| `cudd-bdd` | dev | n=4, median 0.22×, geomean 0.18×, range 0.07–0.35× | 333.9× |
| `cudd-bdd` | holdout | n=6, median 0.06×, geomean 0.06×, range 0.02–0.17× | — |
| `cudd-bdd` | extension | n=8, median 0.11×, geomean 0.18×, range 0.04–4.26× | — |
| `cudd-zdd` | dev | n=4, median 0.08×, geomean 0.08×, range 0.05–0.13× | 166.7× |
| `cudd-zdd` | holdout | n=6, median 0.05×, geomean 0.04×, range 0.02–0.09× | — |
| `cudd-zdd` | extension | n=8, median 0.09×, geomean 0.12×, range 0.03–2.90× | — |
| `qcec` | dev | n=4, median 0.14×, geomean 0.09×, range 0.01–0.55× | 690.3× |
| `qcec` | holdout | n=6, median 0.13×, geomean 0.12×, range 0.04–0.38× | — |
| `qcec` | extension | n=8, median 0.26×, geomean 0.33×, range 0.07–7.05× | — |

## Workload `nonequiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `zdd-native` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 326 | 312 | 2.89 | 0.325 | 6.21 | 0.701 | 14.6 | 30.3 | 2.99 |
| `mod5adder_306` | dev | 32 | 110 | 0.531 | 0.489 | 1.05 | 0.155 | 0.549 | 0.633 | 8.69 | 17 | 4.01 |
| `rd73_312` | dev | 25 | 76 | 0.482 | 0.411 | 0.731 | 0.112 | 0.467 | 0.556 | 8.87 | 12.7 | 8.04 |
| `rd84_313` | dev | 34 | 113 | 1.06 | 0.84 | 1.28 | 0.175 | 0.897 | 1.11 | 10 | 33.2 | 5.61 |
| `sym9_317` | dev | 27 | 64 | 1.09 | 0.859 | 1.1 | 0.131 | 0.894 | 1.14 | 8.59 | 25.7 | 2.95 |
| `5xp1_194` | holdout | 17 | 85 | 0.485 | 0.435 | 0.729 | 0.131 | 0.486 | 0.422 | 12.2 | 19.8 | 3.03 |
| `alu1_198` | holdout | 20 | 32 | 0.128 | 0.128 | 0.226 | 0.051 | 0.151 | 0.145 | 6.61 | 9.1 | 3.03 |
| `cm150a_210` | holdout | 22 | 53 | 0.43 | 0.313 | 0.76 | 0.0923 | 0.367 | 0.346 | 6.61 | 8.45 | 3.25 |
| `dk27_225` | holdout | 18 | 24 | 0.163 | 0.159 | 0.166 | 0.0408 | 0.182 | 0.126 | 6.23 | 7.44 | 2.48 |
| `mlp4_245` | holdout | 16 | 131 | 1.07 | 0.902 | 1.85 | 0.25 | 1 | 1.03 | 8.45 | 14.8 | 2.17 |
| `pcler8_248` | holdout | 21 | 22 | 0.12 | 0.109 | 0.234 | 0.0434 | 0.13 | 0.137 | 6.54 | 8.12 | 1.48 |
| `C7552_205` | extension | 21 | 80 | 0.459 | 0.46 | 0.537 | 0.0999 | 0.504 | 0.396 | 9.11 | 13.8 | 2 |
| `add6_196` | extension | 19 | 229 | 2.67 | 1.58 | 3.15 | 0.448 | 1.69 | 3.27 | 20.4 | 42.9 | 4.52 |
| `apla_203` | extension | 22 | 80 | 4.82 | 4.22 | 1.29 | 0.224 | 4.27 | 1.31 | 9.58 | 14.8 | 3.33 |
| `cm151a_211` | extension | 28 | 33 | 0.221 | 0.216 | 0.306 | 0.0575 | 0.247 | 0.202 | 6.61 | 9.74 | 2.81 |
| `cm163a_213` | extension | 29 | 39 | 0.193 | 0.182 | 0.293 | 0.0626 | 0.218 | 0.195 | 6.69 | 9.3 | 2.61 |
| `cu_219` | extension | 25 | 40 | 0.587 | 0.564 | 0.528 | 0.0739 | 0.486 | 0.228 | 6.57 | 9.08 | 2.91 |
| `dk17_224` | extension | 21 | 49 | 1.55 | 1.28 | 0.55 | 0.083 | 1.59 | 0.386 | 6.65 | 10.4 | 3.46 |
| `example2_231` | extension | 16 | 157 | 2.84 | 1.33 | 3.93 | 0.505 | 1.49 | 2.01 | 10.4 | 17.2 | 3.8 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.22×, geomean 1.19×, range 1.09–1.26× | 1.0× |
| `sparse` | holdout | n=6, median 1.11×, geomean 1.13×, range 1.00–1.38× | — |
| `sparse` | extension | n=8, median 1.10×, geomean 1.24×, range 1.00–2.14× | — |
| `zdd` | dev | n=4, median 0.75×, geomean 0.72×, range 0.50–0.99× | 112.9× |
| `zdd` | holdout | n=6, median 0.57×, geomean 0.63×, range 0.51–0.98× | — |
| `zdd` | extension | n=8, median 0.85×, geomean 1.14×, range 0.66–3.74× | — |
| `zdd-native` | dev | n=4, median 5.17×, geomean 5.21×, range 3.43–8.27× | 1001.9× |
| `zdd-native` | holdout | n=6, median 3.84×, geomean 3.56×, range 2.51–4.66× | — |
| `zdd-native` | extension | n=8, median 5.80×, geomean 7.01×, range 3.08–21.57× | — |
| `auto-zdd` | dev | n=4, median 1.11×, geomean 1.09×, range 0.97–1.21× | 52.6× |
| `auto-zdd` | holdout | n=6, median 0.96×, geomean 0.98×, range 0.85–1.17× | — |
| `auto-zdd` | extension | n=8, median 1.05×, geomean 1.14×, range 0.88–1.90× | — |
| `polybori` | dev | n=4, median 0.91×, geomean 0.90×, range 0.84–0.95× | 464.9× |
| `polybori` | holdout | n=6, median 1.09×, geomean 1.07×, range 0.88–1.30× | — |
| `polybori` | extension | n=8, median 1.29×, geomean 1.65×, range 0.82–4.03× | — |
| `cudd-bdd` | dev | n=4, median 0.08×, geomean 0.08×, range 0.05–0.13× | 22.4× |
| `cudd-bdd` | holdout | n=6, median 0.03×, geomean 0.04×, range 0.02–0.13× | — |
| `cudd-bdd` | extension | n=8, median 0.11×, geomean 0.11×, range 0.03–0.50× | — |
| `cudd-zdd` | dev | n=4, median 0.03×, geomean 0.04×, range 0.03–0.04× | 10.8× |
| `cudd-zdd` | holdout | n=6, median 0.02×, geomean 0.03×, range 0.01–0.07× | — |
| `cudd-zdd` | extension | n=8, median 0.06×, geomean 0.07×, range 0.02–0.33× | — |
| `qcec` | dev | n=4, median 0.16×, geomean 0.15×, range 0.06–0.37× | 109.0× |
| `qcec` | holdout | n=6, median 0.11×, geomean 0.12×, range 0.04–0.49× | — |
| `qcec` | extension | n=8, median 0.34×, geomean 0.31×, range 0.07–1.45× | — |

## Memory and representation changes (`simulate`)

tracemalloc peak in KiB (separate untimed run); worker peak RSS in MiB, which includes the interpreter.

| circuit | `sparse-copy` KiB | `sparse` KiB | `zdd` KiB | `zdd-native` KiB | `auto-zdd` KiB | `polybori` KiB | `cudd-bdd` KiB | `cudd-zdd` KiB | `qcec` KiB | max RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | 4910 | 5060 | 400 | 6 | 392 | 6 | 11 | 11 | — | 139 |
| `mod5adder_306` | 52 | 58 | 130 | 6 | 59 | 6 | 10 | 11 | — | 154 |
| `rd73_312` | 55 | 50 | 82 | 4 | 51 | 5 | 9 | 10 | — | 139 |
| `rd84_313` | 122 | 96 | 172 | 6 | 97 | 6 | 11 | 11 | — | 139 |
| `sym9_317` | 179 | 154 | 177 | 4 | 155 | 5 | 10 | 10 | — | 139 |
| `5xp1_194` | 18 | 19 | 62 | 5 | 19 | 4 | 6 | 6 | — | 139 |
| `alu1_198` | 12 | 11 | 19 | 3 | 13 | 4 | 8 | 8 | — | 139 |
| `cm150a_210` | 41 | 24 | 88 | 4 | 25 | 5 | 9 | 9 | — | 146 |
| `dk27_225` | 24 | 21 | 15 | 2 | 22 | 4 | 6 | 6 | — | 139 |
| `mlp4_245` | 22 | 20 | 130 | 9 | 21 | 4 | 5 | 6 | — | 139 |
| `pcler8_248` | 10 | 10 | 15 | 2 | 10 | 5 | 8 | 8 | — | 139 |
| `C7552_205` | 18 | 18 | 41 | 6 | 19 | 5 | 8 | 8 | — | 139 |
| `add6_196` | 37 | 28 | 404 | 17 | 29 | 4 | 8 | 8 | — | 139 |
| `apla_203` | 325 | 274 | 131 | 8 | 275 | 5 | 9 | 9 | — | 139 |
| `cm151a_211` | 17 | 16 | 31 | 3 | 18 | 5 | 10 | 10 | — | 147 |
| `cm163a_213` | 14 | 14 | 29 | 3 | 15 | 5 | 10 | 10 | — | 138 |
| `cu_219` | 52 | 40 | 39 | 4 | 41 | 5 | 10 | 10 | — | 138 |
| `dk17_224` | 174 | 163 | 64 | 4 | 164 | 5 | 8 | 8 | — | 139 |
| `example2_231` | 56 | 38 | 298 | 11 | 39 | 4 | 5 | 6 | — | 139 |

| circuit | `zdd` nodes | `zdd-native` nodes | `auto-zdd` switch gate | `auto-zdd` conversions | `adaptive-wire` conversions | `packed-fallback` conversions |
|---|---:|---:|---:|---:|---:|---:|
| `c2_181` | 2232 | 2232 | 32 | 35 | — | — |
| `mod5adder_306` | 735 | 735 | none | 0 | — | — |
| `rd73_312` | 531 | 531 | none | 0 | — | — |
| `rd84_313` | 910 | 910 | none | 0 | — | — |
| `sym9_317` | 922 | 922 | none | 0 | — | — |
| `5xp1_194` | 414 | 414 | none | 0 | — | — |
| `alu1_198` | 127 | 127 | none | 0 | — | — |
| `cm150a_210` | 619 | 619 | none | 0 | — | — |
| `dk27_225` | 97 | 97 | none | 0 | — | — |
| `mlp4_245` | 842 | 842 | none | 0 | — | — |
| `pcler8_248` | 114 | 114 | none | 0 | — | — |
| `C7552_205` | 275 | 275 | none | 0 | — | — |
| `add6_196` | 2322 | 2322 | none | 0 | — | — |
| `apla_203` | 714 | 714 | none | 0 | — | — |
| `cm151a_211` | 190 | 190 | none | 0 | — | — |
| `cm163a_213` | 200 | 200 | none | 0 | — | — |
| `cu_219` | 308 | 308 | none | 0 | — | — |
| `dk17_224` | 375 | 375 | none | 0 | — | — |
| `example2_231` | 2043 | 2043 | none | 0 | — | — |

## Native tools

- Versions: dd 0.6.0, mqt.core 3.11.0, mqt.qcec 3.11.0, passagemath-brial 10.8.13.
- CUDD variable reordering: enabled (CUDD default); disabled during ANF conversion; PolyBoRi monomial order: `lp`.
- Native algebras run the same simulate/equivalence code as the symq backends. Their times exclude the conversion of the final outputs to ANF (needed only for the fingerprint), reported here separately.
- tracemalloc only sees Python allocations: memory held by the C/C++ libraries (BDD/ZDD nodes, PolyBoRi diagrams, QCEC decision diagrams) is not counted in the KiB columns; worker peak RSS includes it.

Native representation size of the `simulate` outputs (sum of node counts, shared nodes counted per output) and ANF conversion time (ms):

| circuit | `polybori` nodes | `polybori` conversion | `cudd-bdd` nodes | `cudd-bdd` conversion | `cudd-zdd` nodes | `cudd-zdd` conversion |
|---|---:|---:|---:|---:|---:|---:|
| `c2_181` | 289 | 12.8 | 479 | 16.6 | 1649 | 15.8 |
| `mod5adder_306` | 544 | 0.731 | 511 | 5.02 | 3518 | 10.4 |
| `rd73_312` | 462 | 0.645 | 629 | 6.1 | 2354 | 7.2 |
| `rd84_313` | 904 | 1.29 | 1406 | 13.4 | 3393 | 12.4 |
| `sym9_317` | 965 | 1.85 | 1464 | 15.9 | 2477 | 11.5 |
| `5xp1_194` | 132 | 0.229 | 121 | 1.02 | 499 | 2.17 |
| `alu1_198` | 58 | 0.155 | 85 | 0.646 | 666 | 2.77 |
| `cm150a_210` | 84 | 0.342 | 76 | 0.651 | 749 | 2.88 |
| `dk27_225` | 65 | 0.275 | 72 | 0.654 | 451 | 2.2 |
| `mlp4_245` | 200 | 0.318 | 243 | 2.98 | 751 | 2.91 |
| `pcler8_248` | 82 | 0.207 | 113 | 0.91 | 695 | 2.57 |
| `C7552_205` | 101 | 0.244 | 122 | 1.02 | 662 | 2.54 |
| `add6_196` | 271 | 0.313 | 446 | 5.72 | 1142 | 4.94 |
| `apla_203` | 311 | 2.3 | 234 | 5.32 | 942 | 7.21 |
| `cm151a_211` | 117 | 0.237 | 171 | 1.58 | 1173 | 3.97 |
| `cm163a_213` | 101 | 0.208 | 128 | 1 | 1192 | 4.25 |
| `cu_219` | 143 | 0.602 | 213 | 2.5 | 1067 | 4.52 |
| `dk17_224` | 200 | 2.5 | 176 | 3.81 | 744 | 6.99 |
| `example2_231` | 220 | 0.582 | 223 | 3.49 | 669 | 3.25 |

`qcec` configuration: `{"run_alternating_checker": true, "run_simulation_checker": false, "run_zx_checker": false, "run_construction_checker": false, "parallel": false}`. Median wall time of `qcec.verify` versus QCEC's own reported check and preprocessing times (ms); the circuit conversion to `QuantumComputation` is excluded from the timed runs.

| circuit | workload | verdict | wall | check | preprocessing |
|---|---|---|---:|---:|---:|
| `c2_181` | equiv | equivalent | 6.76 | 5.12 | 0.683 |
| `c2_181` | nonequiv | not_equivalent | 2.99 | 1.57 | 0.588 |
| `mod5adder_306` | equiv | equivalent | 12.2 | 10.4 | 0.685 |
| `mod5adder_306` | nonequiv | not_equivalent | 4.01 | 2.54 | 0.633 |
| `rd73_312` | equiv | equivalent | 43.8 | 41.7 | 0.57 |
| `rd73_312` | nonequiv | not_equivalent | 8.04 | 6.62 | 0.535 |
| `rd84_313` | equiv | equivalent | 36 | 33.9 | 0.699 |
| `rd84_313` | nonequiv | not_equivalent | 5.61 | 4.17 | 0.627 |
| `sym9_317` | equiv | equivalent | 5.33 | 4.11 | 0.546 |
| `sym9_317` | nonequiv | not_equivalent | 2.95 | 1.72 | 0.51 |
| `5xp1_194` | equiv | equivalent | 2.97 | 1.62 | 0.59 |
| `5xp1_194` | nonequiv | not_equivalent | 3.03 | 1.64 | 0.54 |
| `alu1_198` | equiv | equivalent | 3.93 | 2.41 | 0.463 |
| `alu1_198` | nonequiv | not_equivalent | 3.03 | 1.92 | 0.441 |
| `cm150a_210` | equiv | equivalent | 2.93 | 1.67 | 0.517 |
| `cm150a_210` | nonequiv | not_equivalent | 3.25 | 1.98 | 0.5 |
| `dk27_225` | equiv | equivalent | 3.09 | 1.98 | 0.434 |
| `dk27_225` | nonequiv | not_equivalent | 2.48 | 1.42 | 0.426 |
| `mlp4_245` | equiv | equivalent | 4.07 | 2.1 | 0.737 |
| `mlp4_245` | nonequiv | not_equivalent | 2.17 | 0.622 | 0.67 |
| `pcler8_248` | equiv | equivalent | 1.33 | 0.355 | 0.439 |
| `pcler8_248` | nonequiv | not_equivalent | 1.48 | 0.491 | 0.431 |
| `C7552_205` | equiv | equivalent | 3.83 | 2.38 | 0.559 |
| `C7552_205` | nonequiv | not_equivalent | 2 | 0.777 | 0.543 |
| `add6_196` | equiv | equivalent | 14.5 | 11.5 | 1.06 |
| `add6_196` | nonequiv | not_equivalent | 4.52 | 2.21 | 1.09 |
| `apla_203` | equiv | equivalent | 5.17 | 3.3 | 0.717 |
| `apla_203` | nonequiv | not_equivalent | 3.33 | 1.79 | 0.622 |
| `cm151a_211` | equiv | equivalent | 2.83 | 1.62 | 0.499 |
| `cm151a_211` | nonequiv | not_equivalent | 2.81 | 1.59 | 0.491 |
| `cm163a_213` | equiv | equivalent | 2.93 | 1.67 | 0.517 |
| `cm163a_213` | nonequiv | not_equivalent | 2.61 | 1.43 | 0.487 |
| `cu_219` | equiv | equivalent | 2.9 | 1.65 | 0.51 |
| `cu_219` | nonequiv | not_equivalent | 2.91 | 1.68 | 0.494 |
| `dk17_224` | equiv | equivalent | 3.41 | 2.03 | 0.553 |
| `dk17_224` | nonequiv | not_equivalent | 3.46 | 2.05 | 0.536 |
| `example2_231` | equiv | equivalent | 6.95 | 4.83 | 0.839 |
| `example2_231` | nonequiv | not_equivalent | 3.8 | 1.94 | 0.757 |

## Comparison with the historical handoff (`simulate`)

Source: COMPARAISON_EXISTANT.md, frozen comparison of 27 Oct 2026 (user-supplied handoff), table 'Résultat principal sur les circuits COMPLETS'. historical, externally produced; not reproduced by these files. Different machine and different (reconstructed) code: compare speedup ratios, not absolute times.

| circuit | copy_set hist / `sparse-copy` here (ms) | fast_set hist / `sparse` here (ms) | zdd hist / `zdd` here (ms) | auto_zdd hist / `auto-zdd` here (ms) | auto_zdd speedup hist | here |
|---|---|---|---|---|---|---|
| `c2_181` | 226 / 154 | 209 / 156 | 0.835 / 2.72 | 2.28 / 4.34 | 99.31× | 35.54× |
| `mod5adder_306` | 0.173 / 0.244 | 0.146 / 0.205 | 1.12 / 0.722 | 0.179 / 0.242 | 0.97× | 1.01× |
| `rd73_312` | 0.205 / 0.219 | 0.137 / 0.185 | 1.3 / 0.514 | 0.15 / 0.214 | 1.37× | 1.02× |
| `rd84_313` | 0.382 / 0.476 | 0.299 / 0.375 | 2.32 / 0.871 | 0.321 / 0.402 | 1.19× | 1.18× |
| `sym9_317` | 0.532 / 0.519 | 0.309 / 0.41 | 2.39 / 0.843 | 0.31 / 0.429 | 1.72× | 1.21× |
| `5xp1_194` | 0.212 / 0.216 | 0.173 / 0.182 | 0.764 / 0.459 | 0.202 / 0.214 | 1.05× | 1.01× |
| `alu1_198` | 0.046 / 0.0556 | 0.039 / 0.0489 | 0.195 / 0.127 | 0.048 / 0.0662 | 0.96× | 0.84× |
| `dk27_225` | 0.066 / 0.0681 | 0.063 / 0.0722 | 0.185 / 0.128 | 0.073 / 0.0831 | 0.90× | 0.82× |
| `cm150a_210` | 0.198 / 0.194 | 0.117 / 0.14 | 0.605 / 0.565 | 0.134 / 0.167 | 1.48× | 1.16× |
| `pcler8_248` | 0.042 / 0.0468 | 0.036 / 0.0439 | 0.169 / 0.103 | 0.044 / 0.0571 | 0.95× | 0.82× |
| `mlp4_245` | 0.434 / 0.414 | 0.302 / 0.344 | 1.51 / 0.962 | 0.342 / 0.388 | 1.27× | 1.07× |
