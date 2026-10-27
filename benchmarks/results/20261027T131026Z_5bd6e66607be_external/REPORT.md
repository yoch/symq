# Benchmark report

- symq commit `5bd6e66607be2fad7dae617d5ec4f64fdfdf5395` (dirty: False), started 2026-10-27T13:10:26Z
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
| `auto-zdd` | 0 | 57 |
| `polybori` | 0 | 57 |
| `cudd-bdd` | 0 | 57 |
| `cudd-zdd` | 0 | 57 |
| `qcec` | 19 | 38 |

Rejected before benchmarking (outside the X/CX/CCX/MCX model):
- `c2_182`: unsupported statement: 'ctrl @ U(pi/2,-pi/2,pi/2) q[0], q[2]'

## Workload `simulate` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 165 | 162 | 2.78 | 4.4 | 0.325 | 4.38 | 9.04 | not_applicable |
| `mod5adder_306` | dev | 32 | 110 | 0.236 | 0.201 | 0.709 | 0.234 | 0.274 | 3.72 | 6.48 | not_applicable |
| `rd73_312` | dev | 25 | 76 | 0.221 | 0.189 | 0.518 | 0.199 | 0.258 | 2.79 | 4.81 | not_applicable |
| `rd84_313` | dev | 34 | 113 | 0.472 | 0.368 | 0.91 | 0.407 | 0.509 | 4.1 | 19.9 | not_applicable |
| `sym9_317` | dev | 27 | 64 | 0.51 | 0.465 | 0.829 | 0.492 | 0.617 | 3.56 | 15.4 | not_applicable |
| `5xp1_194` | holdout | 17 | 85 | 0.216 | 0.186 | 0.464 | 0.218 | 0.198 | 2.58 | 8.23 | not_applicable |
| `alu1_198` | holdout | 20 | 32 | 0.0504 | 0.0501 | 0.127 | 0.065 | 0.064 | 2.07 | 5.74 | not_applicable |
| `cm150a_210` | holdout | 22 | 53 | 0.194 | 0.139 | 0.569 | 0.161 | 0.158 | 2.6 | 2.12 | not_applicable |
| `dk27_225` | holdout | 18 | 24 | 0.0662 | 0.0721 | 0.128 | 0.103 | 0.0526 | 1.92 | 5.64 | not_applicable |
| `mlp4_245` | holdout | 16 | 131 | 0.42 | 0.343 | 0.955 | 0.391 | 0.422 | 3.12 | 8.2 | not_applicable |
| `pcler8_248` | holdout | 21 | 22 | 0.0457 | 0.0452 | 0.111 | 0.0562 | 0.0596 | 1.91 | 5.31 | not_applicable |
| `C7552_205` | extension | 21 | 80 | 0.211 | 0.199 | 0.409 | 0.226 | 0.186 | 2.8 | 8.01 | not_applicable |
| `add6_196` | extension | 19 | 229 | 1.27 | 0.68 | 2.6 | 0.787 | 1.56 | 8.73 | 16.3 | not_applicable |
| `apla_203` | extension | 22 | 80 | 1.53 | 1.3 | 0.804 | 1.34 | 0.29 | 2.83 | 4.65 | not_applicable |
| `cm151a_211` | extension | 28 | 33 | 0.0973 | 0.0953 | 0.189 | 0.113 | 0.092 | 2.02 | 2.66 | not_applicable |
| `cm163a_213` | extension | 29 | 39 | 0.0823 | 0.0814 | 0.206 | 0.104 | 0.163 | 2.18 | 2.77 | not_applicable |
| `cu_219` | extension | 25 | 40 | 0.218 | 0.208 | 0.335 | 0.231 | 0.107 | 2.16 | 2.83 | not_applicable |
| `dk17_224` | extension | 21 | 49 | 0.618 | 0.605 | 0.412 | 0.643 | 0.133 | 2.27 | 6.05 | not_applicable |
| `example2_231` | extension | 16 | 157 | 0.888 | 0.557 | 2.06 | 0.593 | 0.776 | 3.76 | 8.95 | not_applicable |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.17×, geomean 1.18×, range 1.10–1.28× | 1.0× |
| `sparse` | holdout | n=6, median 1.08×, geomean 1.11×, range 0.92–1.40× | — |
| `sparse` | extension | n=8, median 1.05×, geomean 1.19×, range 1.01–1.86× | — |
| `zdd` | dev | n=4, median 0.47×, geomean 0.46×, range 0.33–0.62× | 59.5× |
| `zdd` | holdout | n=6, median 0.43×, geomean 0.43×, range 0.34–0.52× | — |
| `zdd` | extension | n=8, median 0.51×, geomean 0.67×, range 0.40–1.91× | — |
| `auto-zdd` | dev | n=4, median 1.07×, geomean 1.08×, range 1.01–1.16× | 37.5× |
| `auto-zdd` | holdout | n=6, median 0.90×, geomean 0.90×, range 0.65–1.21× | — |
| `auto-zdd` | extension | n=8, median 0.95×, geomean 1.06×, range 0.79–1.61× | — |
| `polybori` | dev | n=4, median 0.86×, geomean 0.87×, range 0.83–0.93× | 508.4× |
| `polybori` | holdout | n=6, median 1.04×, geomean 1.00×, range 0.77–1.26× | — |
| `polybori` | extension | n=8, median 1.14×, geomean 1.52×, range 0.51–5.28× | — |
| `cudd-bdd` | dev | n=4, median 0.10×, geomean 0.10×, range 0.06–0.14× | 37.8× |
| `cudd-bdd` | holdout | n=6, median 0.05×, geomean 0.05×, range 0.02–0.13× | — |
| `cudd-bdd` | extension | n=8, median 0.12×, geomean 0.13×, range 0.04–0.54× | — |
| `cudd-zdd` | dev | n=4, median 0.03×, geomean 0.03×, range 0.02–0.05× | 18.3× |
| `cudd-zdd` | holdout | n=6, median 0.02×, geomean 0.02×, range 0.01–0.09× | — |
| `cudd-zdd` | extension | n=8, median 0.08×, geomean 0.07×, range 0.03–0.33× | — |

## Workload `equiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 4674 | 4498 | 5.4 | 8.71 | 11.8 | 14.1 | 28.9 | 6.91 |
| `mod5adder_306` | dev | 32 | 110 | 2.78 | 2.77 | 6.85 | 2.84 | 1.54 | 9.58 | 22.2 | 12.3 |
| `rd73_312` | dev | 25 | 76 | 0.566 | 0.444 | 0.866 | 0.518 | 0.906 | 7.49 | 12.2 | 40.9 |
| `rd84_313` | dev | 34 | 113 | 1.73 | 1.48 | 2.91 | 1.56 | 2.1 | 11 | 36.2 | 35.9 |
| `sym9_317` | dev | 27 | 64 | 3.38 | 3.07 | 6.03 | 2.69 | 2.27 | 8.27 | 24.8 | 5.26 |
| `5xp1_194` | holdout | 17 | 85 | 0.894 | 0.832 | 1.19 | 0.901 | 0.623 | 7.44 | 11.6 | 4.38 |
| `alu1_198` | holdout | 20 | 32 | 0.15 | 0.145 | 0.26 | 0.173 | 0.196 | 5.59 | 6.85 | 3.37 |
| `cm150a_210` | holdout | 22 | 53 | 0.546 | 0.444 | 0.803 | 0.597 | 0.481 | 6.55 | 8.06 | 2.96 |
| `dk27_225` | holdout | 18 | 24 | 0.205 | 0.207 | 0.158 | 0.189 | 0.216 | 5.23 | 5.73 | 3.16 |
| `mlp4_245` | holdout | 16 | 131 | 1.51 | 1.36 | 3.35 | 1.54 | 1.36 | 8.72 | 16 | 3.69 |
| `pcler8_248` | holdout | 21 | 22 | 0.102 | 0.0946 | 0.155 | 0.119 | 0.161 | 5.09 | 6.05 | 1.32 |
| `C7552_205` | extension | 21 | 80 | 0.571 | 0.556 | 0.643 | 0.624 | 0.516 | 7.87 | 13 | 3.82 |
| `add6_196` | extension | 19 | 229 | 4.4 | 4.07 | 8.36 | 4.31 | 6.12 | 43.1 | 46 | 13.7 |
| `apla_203` | extension | 22 | 80 | 36.5 | 36.1 | 1.47 | 5.56 | 2.08 | 7.33 | 12.7 | 4.66 |
| `cm151a_211` | extension | 28 | 33 | 0.21 | 0.207 | 0.275 | 0.238 | 0.27 | 5.72 | 8.12 | 2.85 |
| `cm163a_213` | extension | 29 | 39 | 0.208 | 0.201 | 0.337 | 0.235 | 0.311 | 5.88 | 8.17 | 2.95 |
| `cu_219` | extension | 25 | 40 | 0.601 | 0.561 | 0.495 | 0.606 | 0.533 | 5.95 | 7.76 | 2.95 |
| `dk17_224` | extension | 21 | 49 | 2.76 | 2.75 | 0.582 | 2.82 | 1.42 | 6 | 7.94 | 3.38 |
| `example2_231` | extension | 16 | 157 | 2.93 | 2.27 | 4.11 | 2.42 | 2.15 | 9.76 | 20.1 | 7.45 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.13×, geomean 1.13×, range 1.00–1.27× | 1.0× |
| `sparse` | holdout | n=6, median 1.08×, geomean 1.08×, range 0.99–1.23× | — |
| `sparse` | extension | n=8, median 1.03×, geomean 1.06×, range 1.00–1.29× | — |
| `zdd` | dev | n=4, median 0.58×, geomean 0.54×, range 0.41–0.65× | 865.3× |
| `zdd` | holdout | n=6, median 0.67×, geomean 0.70×, range 0.45–1.30× | — |
| `zdd` | extension | n=8, median 0.83×, geomean 1.47×, range 0.53–24.80× | — |
| `auto-zdd` | dev | n=4, median 1.10×, geomean 1.10×, range 0.98–1.26× | 536.8× |
| `auto-zdd` | holdout | n=6, median 0.95×, geomean 0.95×, range 0.86–1.09× | — |
| `auto-zdd` | extension | n=8, median 0.98×, geomean 1.24×, range 0.88–6.57× | — |
| `polybori` | dev | n=4, median 1.15×, geomean 1.08×, range 0.62–1.80× | 395.2× |
| `polybori` | holdout | n=6, median 1.03×, geomean 0.97×, range 0.64–1.44× | — |
| `polybori` | extension | n=8, median 1.12×, geomean 1.47×, range 0.67–17.58× | — |
| `cudd-bdd` | dev | n=4, median 0.22×, geomean 0.19×, range 0.08–0.41× | 332.3× |
| `cudd-bdd` | holdout | n=6, median 0.06×, geomean 0.06×, range 0.02–0.17× | — |
| `cudd-bdd` | extension | n=8, median 0.10×, geomean 0.17×, range 0.04–4.99× | — |
| `cudd-zdd` | dev | n=4, median 0.09×, geomean 0.08×, range 0.05–0.14× | 161.6× |
| `cudd-zdd` | holdout | n=6, median 0.05×, geomean 0.04×, range 0.02–0.09× | — |
| `cudd-zdd` | extension | n=8, median 0.09×, geomean 0.12×, range 0.03–2.88× | — |
| `qcec` | dev | n=4, median 0.14×, geomean 0.10×, range 0.01–0.64× | 676.9× |
| `qcec` | holdout | n=6, median 0.13×, geomean 0.12×, range 0.04–0.41× | — |
| `qcec` | extension | n=8, median 0.26×, geomean 0.33×, range 0.07–7.84× | — |

## Workload `nonequiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 322 | 326 | 2.86 | 6.18 | 0.842 | 15.7 | 33.1 | 2.91 |
| `mod5adder_306` | dev | 32 | 110 | 0.532 | 0.468 | 1.04 | 0.52 | 0.876 | 8.67 | 17.3 | 3.65 |
| `rd73_312` | dev | 25 | 76 | 0.485 | 0.409 | 0.772 | 0.45 | 0.652 | 8.39 | 12.9 | 7.74 |
| `rd84_313` | dev | 34 | 113 | 1.05 | 0.84 | 1.32 | 0.938 | 1.43 | 11.1 | 32.8 | 6.42 |
| `sym9_317` | dev | 27 | 64 | 1.08 | 0.833 | 1.08 | 0.882 | 1.19 | 8.49 | 25.6 | 3.37 |
| `5xp1_194` | holdout | 17 | 85 | 0.489 | 0.427 | 0.743 | 0.495 | 0.499 | 7.85 | 11 | 3.68 |
| `alu1_198` | holdout | 20 | 32 | 0.132 | 0.124 | 0.227 | 0.151 | 0.168 | 6.46 | 8.27 | 2.87 |
| `cm150a_210` | holdout | 22 | 53 | 0.423 | 0.306 | 0.726 | 0.35 | 0.472 | 6.37 | 8.09 | 3.28 |
| `dk27_225` | holdout | 18 | 24 | 0.152 | 0.161 | 0.172 | 0.186 | 0.164 | 6.13 | 7.47 | 2.61 |
| `mlp4_245` | holdout | 16 | 131 | 1.08 | 0.936 | 1.79 | 1.06 | 1.05 | 8.76 | 14.6 | 2.32 |
| `pcler8_248` | holdout | 21 | 22 | 0.115 | 0.112 | 0.242 | 0.128 | 0.141 | 6.31 | 7.96 | 1.35 |
| `C7552_205` | extension | 21 | 80 | 0.473 | 0.467 | 0.565 | 0.507 | 0.448 | 8.05 | 12.3 | 3.51 |
| `add6_196` | extension | 19 | 229 | 2.65 | 1.58 | 3.13 | 1.71 | 3.35 | 21 | 41.7 | 4.95 |
| `apla_203` | extension | 22 | 80 | 4.82 | 4.21 | 1.29 | 4.3 | 1.97 | 9.53 | 13.8 | 4.03 |
| `cm151a_211` | extension | 28 | 33 | 0.231 | 0.217 | 0.309 | 0.259 | 0.242 | 6.62 | 9.5 | 2.8 |
| `cm163a_213` | extension | 29 | 39 | 0.196 | 0.181 | 0.301 | 0.211 | 0.205 | 6.47 | 9.28 | 2.65 |
| `cu_219` | extension | 25 | 40 | 0.453 | 0.469 | 0.51 | 0.496 | 0.407 | 6.49 | 8.91 | 2.75 |
| `dk17_224` | extension | 21 | 49 | 1.31 | 1.29 | 0.549 | 1.33 | 0.763 | 6.66 | 9.08 | 3.06 |
| `example2_231` | extension | 16 | 157 | 2.1 | 1.33 | 3.92 | 1.49 | 2 | 10.3 | 17.2 | 5.31 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.22×, geomean 1.22×, range 1.14–1.29× | 1.0× |
| `sparse` | holdout | n=6, median 1.11×, geomean 1.11×, range 0.94–1.38× | — |
| `sparse` | extension | n=8, median 1.07×, geomean 1.17×, range 0.97–1.68× | — |
| `zdd` | dev | n=4, median 0.71×, geomean 0.71×, range 0.51–1.00× | 112.3× |
| `zdd` | holdout | n=6, median 0.59×, geomean 0.62×, range 0.48–0.88× | — |
| `zdd` | extension | n=8, median 0.84×, geomean 1.05×, range 0.54–3.74× | — |
| `auto-zdd` | dev | n=4, median 1.10×, geomean 1.11×, range 1.02–1.22× | 52.0× |
| `auto-zdd` | holdout | n=6, median 0.95×, geomean 0.96×, range 0.82–1.21× | — |
| `auto-zdd` | extension | n=8, median 0.96×, geomean 1.07×, range 0.89–1.55× | — |
| `polybori` | dev | n=4, median 0.74×, geomean 0.74×, range 0.61–0.90× | 382.1× |
| `polybori` | holdout | n=6, median 0.91×, geomean 0.90×, range 0.79–1.03× | — |
| `polybori` | extension | n=8, median 1.05×, geomean 1.18×, range 0.79–2.45× | — |
| `cudd-bdd` | dev | n=4, median 0.08×, geomean 0.08×, range 0.06–0.13× | 20.5× |
| `cudd-bdd` | holdout | n=6, median 0.04×, geomean 0.04×, range 0.02–0.12× | — |
| `cudd-bdd` | extension | n=8, median 0.10×, geomean 0.10×, range 0.03–0.51× | — |
| `cudd-zdd` | dev | n=4, median 0.03×, geomean 0.04×, range 0.03–0.04× | 9.7× |
| `cudd-zdd` | holdout | n=6, median 0.03×, geomean 0.03×, range 0.01–0.07× | — |
| `cudd-zdd` | extension | n=8, median 0.06×, geomean 0.07×, range 0.02–0.35× | — |
| `qcec` | dev | n=4, median 0.15×, geomean 0.15×, range 0.06–0.32× | 110.6× |
| `qcec` | holdout | n=6, median 0.11×, geomean 0.11×, range 0.05–0.46× | — |
| `qcec` | extension | n=8, median 0.28×, geomean 0.25×, range 0.07–1.20× | — |

## Memory and representation changes (`simulate`)

tracemalloc peak in KiB (separate untimed run); worker peak RSS in MiB, which includes the interpreter.

| circuit | `sparse-copy` KiB | `sparse` KiB | `zdd` KiB | `auto-zdd` KiB | `polybori` KiB | `cudd-bdd` KiB | `cudd-zdd` KiB | `qcec` KiB | max RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | 4910 | 5060 | 400 | 392 | 6 | 11 | 11 | — | 139 |
| `mod5adder_306` | 52 | 58 | 130 | 59 | 6 | 10 | 11 | — | 146 |
| `rd73_312` | 55 | 50 | 82 | 51 | 5 | 9 | 10 | — | 138 |
| `rd84_313` | 122 | 96 | 172 | 97 | 6 | 11 | 11 | — | 139 |
| `sym9_317` | 179 | 154 | 177 | 155 | 5 | 10 | 10 | — | 139 |
| `5xp1_194` | 18 | 19 | 62 | 19 | 4 | 6 | 6 | — | 139 |
| `alu1_198` | 12 | 11 | 19 | 13 | 4 | 8 | 8 | — | 139 |
| `cm150a_210` | 41 | 24 | 88 | 25 | 5 | 9 | 9 | — | 147 |
| `dk27_225` | 24 | 21 | 15 | 22 | 4 | 6 | 6 | — | 139 |
| `mlp4_245` | 22 | 20 | 130 | 21 | 4 | 5 | 6 | — | 139 |
| `pcler8_248` | 10 | 10 | 15 | 10 | 5 | 8 | 8 | — | 139 |
| `C7552_205` | 18 | 18 | 41 | 19 | 5 | 8 | 8 | — | 139 |
| `add6_196` | 37 | 28 | 404 | 29 | 4 | 8 | 8 | — | 139 |
| `apla_203` | 325 | 274 | 131 | 275 | 5 | 9 | 9 | — | 138 |
| `cm151a_211` | 17 | 16 | 31 | 18 | 5 | 10 | 10 | — | 139 |
| `cm163a_213` | 14 | 14 | 29 | 15 | 5 | 10 | 10 | — | 139 |
| `cu_219` | 52 | 40 | 39 | 41 | 5 | 10 | 10 | — | 139 |
| `dk17_224` | 174 | 163 | 64 | 164 | 5 | 8 | 8 | — | 139 |
| `example2_231` | 56 | 38 | 298 | 39 | 4 | 5 | 6 | — | 139 |

| circuit | `zdd` nodes | `auto-zdd` switch gate | `auto-zdd` conversions | `adaptive-wire` conversions | `packed-fallback` conversions |
|---|---:|---:|---:|---:|---:|
| `c2_181` | 2232 | 32 | 35 | — | — |
| `mod5adder_306` | 735 | none | 0 | — | — |
| `rd73_312` | 531 | none | 0 | — | — |
| `rd84_313` | 910 | none | 0 | — | — |
| `sym9_317` | 922 | none | 0 | — | — |
| `5xp1_194` | 414 | none | 0 | — | — |
| `alu1_198` | 127 | none | 0 | — | — |
| `cm150a_210` | 619 | none | 0 | — | — |
| `dk27_225` | 97 | none | 0 | — | — |
| `mlp4_245` | 842 | none | 0 | — | — |
| `pcler8_248` | 114 | none | 0 | — | — |
| `C7552_205` | 275 | none | 0 | — | — |
| `add6_196` | 2322 | none | 0 | — | — |
| `apla_203` | 714 | none | 0 | — | — |
| `cm151a_211` | 190 | none | 0 | — | — |
| `cm163a_213` | 200 | none | 0 | — | — |
| `cu_219` | 308 | none | 0 | — | — |
| `dk17_224` | 375 | none | 0 | — | — |
| `example2_231` | 2043 | none | 0 | — | — |

## Native tools

- Versions: dd 0.6.0, mqt.core 3.11.0, mqt.qcec 3.11.0, passagemath-brial 10.8.13.
- CUDD variable reordering: enabled (CUDD default); disabled during ANF conversion; PolyBoRi monomial order: `lp`.
- Native algebras run the same simulate/equivalence code as the symq backends. Their times exclude the conversion of the final outputs to ANF (needed only for the fingerprint), reported here separately.
- tracemalloc only sees Python allocations: memory held by the C/C++ libraries (BDD/ZDD nodes, PolyBoRi diagrams, QCEC decision diagrams) is not counted in the KiB columns; worker peak RSS includes it.

Native representation size of the `simulate` outputs (sum of node counts, shared nodes counted per output) and ANF conversion time (ms):

| circuit | `polybori` nodes | `polybori` conversion | `cudd-bdd` nodes | `cudd-bdd` conversion | `cudd-zdd` nodes | `cudd-zdd` conversion |
|---|---:|---:|---:|---:|---:|---:|
| `c2_181` | 289 | 12.8 | 479 | 16.7 | 1649 | 15 |
| `mod5adder_306` | 544 | 0.754 | 511 | 4.91 | 3518 | 9.99 |
| `rd73_312` | 462 | 0.624 | 629 | 5.78 | 2354 | 7.49 |
| `rd84_313` | 904 | 1.29 | 1406 | 14.1 | 3393 | 12.2 |
| `sym9_317` | 965 | 2.18 | 1464 | 18.2 | 2477 | 11.5 |
| `5xp1_194` | 132 | 0.266 | 121 | 1.05 | 499 | 2.88 |
| `alu1_198` | 58 | 0.167 | 85 | 0.647 | 666 | 2.64 |
| `cm150a_210` | 84 | 0.322 | 76 | 0.669 | 749 | 2.65 |
| `dk27_225` | 65 | 0.284 | 72 | 0.717 | 451 | 2.24 |
| `mlp4_245` | 200 | 0.312 | 243 | 2.89 | 751 | 2.98 |
| `pcler8_248` | 82 | 0.157 | 113 | 0.947 | 695 | 2.58 |
| `C7552_205` | 101 | 0.196 | 122 | 0.983 | 662 | 3 |
| `add6_196` | 271 | 0.321 | 446 | 5.83 | 1142 | 5.12 |
| `apla_203` | 311 | 2.16 | 234 | 5.44 | 942 | 6.95 |
| `cm151a_211` | 117 | 0.22 | 171 | 1.52 | 1173 | 3.85 |
| `cm163a_213` | 101 | 0.295 | 128 | 1.03 | 1192 | 3.9 |
| `cu_219` | 143 | 0.586 | 213 | 2.52 | 1067 | 4.52 |
| `dk17_224` | 200 | 1.95 | 176 | 3.26 | 744 | 6.02 |
| `example2_231` | 220 | 0.585 | 223 | 3.43 | 669 | 3.23 |

`qcec` configuration: `{"run_alternating_checker": true, "run_simulation_checker": false, "run_zx_checker": false, "run_construction_checker": false, "parallel": false}`. Median wall time of `qcec.verify` versus QCEC's own reported check and preprocessing times (ms); the circuit conversion to `QuantumComputation` is excluded from the timed runs.

| circuit | workload | verdict | wall | check | preprocessing |
|---|---|---|---:|---:|---:|
| `c2_181` | equiv | equivalent | 6.91 | 5.26 | 0.682 |
| `c2_181` | nonequiv | not_equivalent | 2.91 | 1.51 | 0.587 |
| `mod5adder_306` | equiv | equivalent | 12.3 | 10.4 | 0.684 |
| `mod5adder_306` | nonequiv | not_equivalent | 3.65 | 2.17 | 0.634 |
| `rd73_312` | equiv | equivalent | 40.9 | 38.9 | 0.567 |
| `rd73_312` | nonequiv | not_equivalent | 7.74 | 6.36 | 0.531 |
| `rd84_313` | equiv | equivalent | 35.9 | 33.7 | 0.698 |
| `rd84_313` | nonequiv | not_equivalent | 6.42 | 4.8 | 0.657 |
| `sym9_317` | equiv | equivalent | 5.26 | 3.9 | 0.546 |
| `sym9_317` | nonequiv | not_equivalent | 3.37 | 2.11 | 0.506 |
| `5xp1_194` | equiv | equivalent | 4.38 | 3.03 | 0.59 |
| `5xp1_194` | nonequiv | not_equivalent | 3.68 | 2.26 | 0.723 |
| `alu1_198` | equiv | equivalent | 3.37 | 2.18 | 0.458 |
| `alu1_198` | nonequiv | not_equivalent | 2.87 | 1.87 | 0.443 |
| `cm150a_210` | equiv | equivalent | 2.96 | 1.67 | 0.517 |
| `cm150a_210` | nonequiv | not_equivalent | 3.28 | 2.01 | 0.498 |
| `dk27_225` | equiv | equivalent | 3.16 | 2 | 0.431 |
| `dk27_225` | nonequiv | not_equivalent | 2.61 | 1.49 | 0.427 |
| `mlp4_245` | equiv | equivalent | 3.69 | 2 | 0.729 |
| `mlp4_245` | nonequiv | not_equivalent | 2.32 | 0.603 | 0.671 |
| `pcler8_248` | equiv | equivalent | 1.32 | 0.37 | 0.437 |
| `pcler8_248` | nonequiv | not_equivalent | 1.35 | 0.378 | 0.429 |
| `C7552_205` | equiv | equivalent | 3.82 | 2.32 | 0.585 |
| `C7552_205` | nonequiv | not_equivalent | 3.51 | 2.06 | 0.544 |
| `add6_196` | equiv | equivalent | 13.7 | 10.9 | 1.05 |
| `add6_196` | nonequiv | not_equivalent | 4.95 | 2.48 | 1.15 |
| `apla_203` | equiv | equivalent | 4.66 | 2.94 | 0.681 |
| `apla_203` | nonequiv | not_equivalent | 4.03 | 2.3 | 0.641 |
| `cm151a_211` | equiv | equivalent | 2.85 | 1.63 | 0.498 |
| `cm151a_211` | nonequiv | not_equivalent | 2.8 | 1.6 | 0.495 |
| `cm163a_213` | equiv | equivalent | 2.95 | 1.68 | 0.517 |
| `cm163a_213` | nonequiv | not_equivalent | 2.65 | 1.44 | 0.484 |
| `cu_219` | equiv | equivalent | 2.95 | 1.67 | 0.515 |
| `cu_219` | nonequiv | not_equivalent | 2.75 | 1.52 | 0.493 |
| `dk17_224` | equiv | equivalent | 3.38 | 2 | 0.554 |
| `dk17_224` | nonequiv | not_equivalent | 3.06 | 1.75 | 0.526 |
| `example2_231` | equiv | equivalent | 7.45 | 5.25 | 0.844 |
| `example2_231` | nonequiv | not_equivalent | 5.31 | 3.42 | 0.758 |

## Comparison with the historical handoff (`simulate`)

Source: COMPARAISON_EXISTANT.md, frozen comparison of 27 Oct 2026 (user-supplied handoff), table 'Résultat principal sur les circuits COMPLETS'. historical, externally produced; not reproduced by these files. Different machine and different (reconstructed) code: compare speedup ratios, not absolute times.

| circuit | copy_set hist / `sparse-copy` here (ms) | fast_set hist / `sparse` here (ms) | zdd hist / `zdd` here (ms) | auto_zdd hist / `auto-zdd` here (ms) | auto_zdd speedup hist | here |
|---|---|---|---|---|---|---|
| `c2_181` | 226 / 165 | 209 / 162 | 0.835 / 2.78 | 2.28 / 4.4 | 99.31× | 37.54× |
| `mod5adder_306` | 0.173 / 0.236 | 0.146 / 0.201 | 1.12 / 0.709 | 0.179 / 0.234 | 0.97× | 1.01× |
| `rd73_312` | 0.205 / 0.221 | 0.137 / 0.189 | 1.3 / 0.518 | 0.15 / 0.199 | 1.37× | 1.11× |
| `rd84_313` | 0.382 / 0.472 | 0.299 / 0.368 | 2.32 / 0.91 | 0.321 / 0.407 | 1.19× | 1.16× |
| `sym9_317` | 0.532 / 0.51 | 0.309 / 0.465 | 2.39 / 0.829 | 0.31 / 0.492 | 1.72× | 1.04× |
| `5xp1_194` | 0.212 / 0.216 | 0.173 / 0.186 | 0.764 / 0.464 | 0.202 / 0.218 | 1.05× | 0.99× |
| `alu1_198` | 0.046 / 0.0504 | 0.039 / 0.0501 | 0.195 / 0.127 | 0.048 / 0.065 | 0.96× | 0.78× |
| `dk27_225` | 0.066 / 0.0662 | 0.063 / 0.0721 | 0.185 / 0.128 | 0.073 / 0.103 | 0.90× | 0.65× |
| `cm150a_210` | 0.198 / 0.194 | 0.117 / 0.139 | 0.605 / 0.569 | 0.134 / 0.161 | 1.48× | 1.21× |
| `pcler8_248` | 0.042 / 0.0457 | 0.036 / 0.0452 | 0.169 / 0.111 | 0.044 / 0.0562 | 0.95× | 0.81× |
| `mlp4_245` | 0.434 / 0.42 | 0.302 / 0.343 | 1.51 / 0.955 | 0.342 / 0.391 | 1.27× | 1.07× |
