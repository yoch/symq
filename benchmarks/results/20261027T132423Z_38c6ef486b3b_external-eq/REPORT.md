# Benchmark report

- symq commit `38c6ef486b3b19116a70a15d1166e7a4b60e368b` (dirty: False), started 2026-10-27T13:24:23Z
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
| `c2_181` | dev | 35 | 116 | 160 | 155 | 2.74 | 4.35 | 0.326 | 4.44 | 8.79 | not_applicable |
| `mod5adder_306` | dev | 32 | 110 | 0.225 | 0.206 | 0.73 | 0.248 | 0.284 | 3.27 | 6.52 | not_applicable |
| `rd73_312` | dev | 25 | 76 | 0.221 | 0.177 | 0.505 | 0.201 | 0.258 | 3.1 | 4.53 | not_applicable |
| `rd84_313` | dev | 34 | 113 | 0.476 | 0.368 | 0.889 | 0.41 | 0.514 | 3.64 | 20.3 | not_applicable |
| `sym9_317` | dev | 27 | 64 | 0.529 | 0.419 | 0.842 | 0.463 | 0.551 | 3.5 | 16.4 | not_applicable |
| `5xp1_194` | holdout | 17 | 85 | 0.216 | 0.183 | 0.48 | 0.217 | 0.188 | 2.47 | 6.33 | not_applicable |
| `alu1_198` | holdout | 20 | 32 | 0.052 | 0.0508 | 0.126 | 0.0633 | 0.064 | 1.99 | 5.53 | not_applicable |
| `cm150a_210` | holdout | 22 | 53 | 0.2 | 0.141 | 0.571 | 0.157 | 0.161 | 2.72 | 2.66 | not_applicable |
| `dk27_225` | holdout | 18 | 24 | 0.0682 | 0.0708 | 0.0999 | 0.0805 | 0.0508 | 1.94 | 5.24 | not_applicable |
| `mlp4_245` | holdout | 16 | 131 | 0.408 | 0.341 | 0.958 | 0.395 | 0.446 | 3.42 | 9.98 | not_applicable |
| `pcler8_248` | holdout | 21 | 22 | 0.048 | 0.0448 | 0.106 | 0.0558 | 0.0589 | 2.46 | 5.35 | not_applicable |
| `C7552_205` | extension | 21 | 80 | 0.216 | 0.199 | 0.32 | 0.237 | 0.196 | 2.49 | 6.96 | not_applicable |
| `add6_196` | extension | 19 | 229 | 1.25 | 0.691 | 2.6 | 0.774 | 1.54 | 7.53 | 14.4 | not_applicable |
| `apla_203` | extension | 22 | 80 | 1.53 | 1.29 | 0.797 | 1.33 | 0.285 | 2.54 | 3.9 | not_applicable |
| `cm151a_211` | extension | 28 | 33 | 0.0962 | 0.132 | 0.246 | 0.119 | 0.0994 | 2.38 | 3.65 | not_applicable |
| `cm163a_213` | extension | 29 | 39 | 0.0853 | 0.0952 | 0.21 | 0.0964 | 0.0908 | 2.85 | 2.76 | not_applicable |
| `cu_219` | extension | 25 | 40 | 0.212 | 0.202 | 0.331 | 0.232 | 0.105 | 2.22 | 2.95 | not_applicable |
| `dk17_224` | extension | 21 | 49 | 0.626 | 0.62 | 0.405 | 0.642 | 0.139 | 2.38 | 7.39 | not_applicable |
| `example2_231` | extension | 16 | 157 | 0.891 | 0.516 | 2.09 | 0.598 | 0.772 | 3.52 | 9.03 | not_applicable |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.26×, geomean 1.22×, range 1.09–1.29× | 1.0× |
| `sparse` | holdout | n=6, median 1.13×, geomean 1.13×, range 0.96–1.42× | — |
| `sparse` | extension | n=8, median 1.07×, geomean 1.14×, range 0.73–1.81× | — |
| `zdd` | dev | n=4, median 0.49×, geomean 0.46×, range 0.31–0.63× | 58.4× |
| `zdd` | holdout | n=6, median 0.44×, geomean 0.45×, range 0.35–0.68× | — |
| `zdd` | extension | n=8, median 0.56×, geomean 0.67×, range 0.39–1.92× | — |
| `auto-zdd` | dev | n=4, median 1.12×, geomean 1.07×, range 0.91–1.16× | 36.8× |
| `auto-zdd` | holdout | n=6, median 0.93×, geomean 0.96×, range 0.82–1.28× | — |
| `auto-zdd` | extension | n=8, median 0.94×, geomean 1.06×, range 0.81–1.62× | — |
| `polybori` | dev | n=4, median 0.89×, geomean 0.88×, range 0.79–0.96× | 490.4× |
| `polybori` | holdout | n=6, median 1.03×, geomean 1.03×, range 0.81–1.34× | — |
| `polybori` | extension | n=8, median 1.13×, geomean 1.61×, range 0.81–5.37× | — |
| `cudd-bdd` | dev | n=4, median 0.10×, geomean 0.10×, range 0.07–0.15× | 36.0× |
| `cudd-bdd` | holdout | n=6, median 0.05×, geomean 0.05×, range 0.02–0.12× | — |
| `cudd-bdd` | extension | n=8, median 0.13×, geomean 0.13×, range 0.03–0.60× | — |
| `cudd-zdd` | dev | n=4, median 0.03×, geomean 0.03×, range 0.02–0.05× | 18.2× |
| `cudd-zdd` | holdout | n=6, median 0.02×, geomean 0.02×, range 0.01–0.08× | — |
| `cudd-zdd` | extension | n=8, median 0.08×, geomean 0.07×, range 0.03–0.39× | — |

## Workload `equiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 4554 | 4468 | 5.44 | 8.98 | 0.915 | 15.2 | 30.1 | 6.95 |
| `mod5adder_306` | dev | 32 | 110 | 2.75 | 2.75 | 6.87 | 2.82 | 1.11 | 9.76 | 21.8 | 12.1 |
| `rd73_312` | dev | 25 | 76 | 0.565 | 0.457 | 0.886 | 0.516 | 0.625 | 7.77 | 12.6 | 43 |
| `rd84_313` | dev | 34 | 113 | 1.71 | 1.46 | 2.92 | 1.59 | 1.37 | 11.1 | 35.7 | 35.8 |
| `sym9_317` | dev | 27 | 64 | 2.99 | 2.65 | 4.68 | 2.7 | 1.34 | 8.47 | 25.2 | 5.24 |
| `5xp1_194` | holdout | 17 | 85 | 0.899 | 0.83 | 1.21 | 0.892 | 0.514 | 6.86 | 10.6 | 3.16 |
| `alu1_198` | holdout | 20 | 32 | 0.15 | 0.142 | 0.249 | 0.172 | 0.149 | 5.62 | 6.77 | 3.32 |
| `cm150a_210` | holdout | 22 | 53 | 0.54 | 0.444 | 0.819 | 0.468 | 0.362 | 5.86 | 7.25 | 3.4 |
| `dk27_225` | holdout | 18 | 24 | 0.164 | 0.164 | 0.153 | 0.235 | 0.11 | 5.34 | 6.13 | 3.21 |
| `mlp4_245` | holdout | 16 | 131 | 1.52 | 1.38 | 3.35 | 1.51 | 1.24 | 9.62 | 18.1 | 3.62 |
| `pcler8_248` | holdout | 21 | 22 | 0.101 | 0.093 | 0.161 | 0.118 | 0.115 | 5.34 | 6.05 | 1.36 |
| `C7552_205` | extension | 21 | 80 | 0.553 | 0.543 | 0.636 | 0.588 | 0.425 | 6.9 | 11.8 | 3.74 |
| `add6_196` | extension | 19 | 229 | 4.47 | 4.09 | 8.46 | 4.32 | 4.15 | 39.8 | 46.7 | 13.5 |
| `apla_203` | extension | 22 | 80 | 36.4 | 35.8 | 1.46 | 5.48 | 0.731 | 7.23 | 12.6 | 5.06 |
| `cm151a_211` | extension | 28 | 33 | 0.206 | 0.204 | 0.273 | 0.241 | 0.194 | 5.87 | 7.96 | 2.89 |
| `cm163a_213` | extension | 29 | 39 | 0.212 | 0.205 | 0.324 | 0.248 | 0.209 | 6.24 | 8.7 | 3.01 |
| `cu_219` | extension | 25 | 40 | 0.586 | 0.551 | 0.484 | 0.62 | 0.241 | 5.82 | 8.08 | 2.88 |
| `dk17_224` | extension | 21 | 49 | 2.75 | 3.96 | 0.596 | 2.83 | 0.311 | 6.27 | 8.16 | 3.34 |
| `example2_231` | extension | 16 | 157 | 2.98 | 2.29 | 4.24 | 2.51 | 1.87 | 9.86 | 20 | 7.06 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.15×, geomean 1.13×, range 1.00–1.23× | 1.0× |
| `sparse` | holdout | n=6, median 1.09×, geomean 1.09×, range 1.00–1.21× | — |
| `sparse` | extension | n=8, median 1.03×, geomean 1.02×, range 0.69–1.30× | — |
| `zdd` | dev | n=4, median 0.61×, geomean 0.56×, range 0.40–0.64× | 836.3× |
| `zdd` | holdout | n=6, median 0.64×, geomean 0.67×, range 0.45–1.08× | — |
| `zdd` | extension | n=8, median 0.81×, geomean 1.47×, range 0.53–24.84× | — |
| `auto-zdd` | dev | n=4, median 1.09×, geomean 1.06×, range 0.97–1.11× | 507.2× |
| `auto-zdd` | holdout | n=6, median 0.94×, geomean 0.92×, range 0.70–1.15× | — |
| `auto-zdd` | extension | n=8, median 0.96×, geomean 1.23×, range 0.86–6.64× | — |
| `polybori` | dev | n=4, median 1.74×, geomean 1.58×, range 0.90–2.48× | 4977.9× |
| `polybori` | holdout | n=6, median 1.36×, geomean 1.27×, range 0.88–1.75× | — |
| `polybori` | extension | n=8, median 1.45×, geomean 2.67×, range 1.02–49.73× | — |
| `cudd-bdd` | dev | n=4, median 0.22×, geomean 0.18×, range 0.07–0.35× | 299.4× |
| `cudd-bdd` | holdout | n=6, median 0.06×, geomean 0.06×, range 0.02–0.16× | — |
| `cudd-bdd` | extension | n=8, median 0.11×, geomean 0.17×, range 0.03–5.03× | — |
| `cudd-zdd` | dev | n=4, median 0.08×, geomean 0.08×, range 0.04–0.13× | 151.2× |
| `cudd-zdd` | holdout | n=6, median 0.05×, geomean 0.04×, range 0.02–0.08× | — |
| `cudd-zdd` | extension | n=8, median 0.08×, geomean 0.11×, range 0.02–2.89× | — |
| `qcec` | dev | n=4, median 0.14×, geomean 0.09×, range 0.01–0.57× | 655.5× |
| `qcec` | holdout | n=6, median 0.12×, geomean 0.12×, range 0.05–0.42× | — |
| `qcec` | extension | n=8, median 0.27×, geomean 0.33×, range 0.07–7.19× | — |

## Workload `nonequiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 321 | 321 | 2.87 | 6.22 | 0.713 | 12.5 | 24 | 3.42 |
| `mod5adder_306` | dev | 32 | 110 | 0.538 | 0.492 | 1.1 | 0.542 | 0.64 | 9.29 | 17.6 | 3.55 |
| `rd73_312` | dev | 25 | 76 | 0.494 | 0.501 | 0.738 | 0.459 | 0.548 | 8.74 | 12.9 | 7.59 |
| `rd84_313` | dev | 34 | 113 | 1.06 | 0.867 | 1.3 | 0.906 | 1.1 | 10.1 | 33.6 | 5.67 |
| `sym9_317` | dev | 27 | 64 | 1.09 | 0.833 | 1.09 | 0.894 | 1.14 | 9.01 | 25.7 | 3.38 |
| `5xp1_194` | holdout | 17 | 85 | 0.498 | 0.432 | 0.716 | 0.516 | 0.436 | 7.91 | 15.2 | 3 |
| `alu1_198` | holdout | 20 | 32 | 0.126 | 0.125 | 0.222 | 0.149 | 0.144 | 6.47 | 17 | 2.79 |
| `cm150a_210` | holdout | 22 | 53 | 0.426 | 0.363 | 0.782 | 0.349 | 0.341 | 6.64 | 8.79 | 3.29 |
| `dk27_225` | holdout | 18 | 24 | 0.164 | 0.158 | 0.166 | 0.189 | 0.124 | 6.74 | 7.68 | 2.56 |
| `mlp4_245` | holdout | 16 | 131 | 1.08 | 0.9 | 1.83 | 0.994 | 1.04 | 8.75 | 17 | 2.19 |
| `pcler8_248` | holdout | 21 | 22 | 0.119 | 0.113 | 0.245 | 0.127 | 0.136 | 7.43 | 9.11 | 3.38 |
| `C7552_205` | extension | 21 | 80 | 0.474 | 0.441 | 0.539 | 0.516 | 0.392 | 7.41 | 11.7 | 3.33 |
| `add6_196` | extension | 19 | 229 | 2.7 | 1.6 | 3.13 | 1.74 | 3.23 | 20.8 | 42.5 | 4.45 |
| `apla_203` | extension | 22 | 80 | 4.81 | 5.19 | 1.31 | 4.31 | 1.31 | 9.17 | 12.9 | 3.37 |
| `cm151a_211` | extension | 28 | 33 | 0.229 | 0.217 | 0.302 | 0.242 | 0.2 | 6.8 | 9.72 | 2.82 |
| `cm163a_213` | extension | 29 | 39 | 0.189 | 0.186 | 0.293 | 0.213 | 0.193 | 6.52 | 9.4 | 2.66 |
| `cu_219` | extension | 25 | 40 | 0.457 | 0.454 | 0.499 | 0.494 | 0.232 | 7.35 | 9.21 | 2.78 |
| `dk17_224` | extension | 21 | 49 | 1.32 | 1.34 | 0.564 | 1.47 | 0.3 | 6.61 | 9.29 | 3.22 |
| `example2_231` | extension | 16 | 157 | 2.17 | 1.39 | 3.82 | 1.51 | 2 | 11.4 | 17.7 | 5.36 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.16×, geomean 1.15×, range 0.99–1.31× | 1.0× |
| `sparse` | holdout | n=6, median 1.10×, geomean 1.10×, range 1.01–1.20× | — |
| `sparse` | extension | n=8, median 1.04×, geomean 1.14×, range 0.93–1.69× | — |
| `zdd` | dev | n=4, median 0.74×, geomean 0.72×, range 0.49–1.00× | 111.8× |
| `zdd` | holdout | n=6, median 0.58×, geomean 0.63×, range 0.49–0.99× | — |
| `zdd` | extension | n=8, median 0.87×, geomean 1.06×, range 0.57–3.68× | — |
| `auto-zdd` | dev | n=4, median 1.12×, geomean 1.11×, range 0.99–1.22× | 51.6× |
| `auto-zdd` | holdout | n=6, median 0.95×, geomean 0.98×, range 0.85–1.22× | — |
| `auto-zdd` | extension | n=8, median 0.94×, geomean 1.06×, range 0.88–1.55× | — |
| `polybori` | dev | n=4, median 0.93×, geomean 0.91×, range 0.84–0.96× | 450.7× |
| `polybori` | holdout | n=6, median 1.09×, geomean 1.07×, range 0.88–1.32× | — |
| `polybori` | extension | n=8, median 1.18×, geomean 1.58×, range 0.84–4.39× | — |
| `cudd-bdd` | dev | n=4, median 0.08×, geomean 0.08×, range 0.06–0.12× | 25.7× |
| `cudd-bdd` | holdout | n=6, median 0.04×, geomean 0.04×, range 0.02–0.12× | — |
| `cudd-bdd` | extension | n=8, median 0.10×, geomean 0.10×, range 0.03–0.53× | — |
| `cudd-zdd` | dev | n=4, median 0.03×, geomean 0.04×, range 0.03–0.04× | 13.4× |
| `cudd-zdd` | holdout | n=6, median 0.03×, geomean 0.02×, range 0.01–0.06× | — |
| `cudd-zdd` | extension | n=8, median 0.06×, geomean 0.07×, range 0.02–0.37× | — |
| `qcec` | dev | n=4, median 0.17×, geomean 0.16×, range 0.07–0.32× | 94.1× |
| `qcec` | holdout | n=6, median 0.10×, geomean 0.10×, range 0.04–0.49× | — |
| `qcec` | extension | n=8, median 0.28×, geomean 0.26×, range 0.07–1.43× | — |

## Memory and representation changes (`simulate`)

tracemalloc peak in KiB (separate untimed run); worker peak RSS in MiB, which includes the interpreter.

| circuit | `sparse-copy` KiB | `sparse` KiB | `zdd` KiB | `auto-zdd` KiB | `polybori` KiB | `cudd-bdd` KiB | `cudd-zdd` KiB | `qcec` KiB | max RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | 4910 | 5060 | 400 | 392 | 6 | 11 | 11 | — | 139 |
| `mod5adder_306` | 52 | 58 | 130 | 59 | 6 | 10 | 11 | — | 139 |
| `rd73_312` | 55 | 50 | 82 | 51 | 5 | 9 | 10 | — | 139 |
| `rd84_313` | 122 | 96 | 172 | 97 | 6 | 11 | 11 | — | 139 |
| `sym9_317` | 179 | 154 | 177 | 155 | 5 | 10 | 10 | — | 139 |
| `5xp1_194` | 18 | 19 | 62 | 19 | 4 | 6 | 6 | — | 139 |
| `alu1_198` | 12 | 11 | 19 | 13 | 4 | 8 | 8 | — | 139 |
| `cm150a_210` | 41 | 24 | 88 | 25 | 5 | 9 | 9 | — | 146 |
| `dk27_225` | 24 | 21 | 15 | 22 | 4 | 6 | 6 | — | 139 |
| `mlp4_245` | 22 | 20 | 130 | 21 | 4 | 5 | 6 | — | 139 |
| `pcler8_248` | 10 | 10 | 15 | 10 | 5 | 8 | 8 | — | 146 |
| `C7552_205` | 18 | 18 | 41 | 19 | 5 | 8 | 8 | — | 138 |
| `add6_196` | 37 | 28 | 404 | 29 | 4 | 8 | 8 | — | 139 |
| `apla_203` | 325 | 274 | 131 | 275 | 5 | 9 | 9 | — | 138 |
| `cm151a_211` | 17 | 16 | 31 | 18 | 5 | 10 | 10 | — | 138 |
| `cm163a_213` | 14 | 14 | 29 | 15 | 5 | 10 | 10 | — | 138 |
| `cu_219` | 52 | 40 | 39 | 41 | 5 | 10 | 10 | — | 138 |
| `dk17_224` | 174 | 163 | 64 | 164 | 5 | 8 | 8 | — | 139 |
| `example2_231` | 56 | 38 | 298 | 39 | 4 | 5 | 6 | — | 138 |

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
| `c2_181` | 289 | 12.6 | 479 | 16.6 | 1649 | 15 |
| `mod5adder_306` | 544 | 0.771 | 511 | 5.08 | 3518 | 10.4 |
| `rd73_312` | 462 | 0.636 | 629 | 5.76 | 2354 | 7.27 |
| `rd84_313` | 904 | 1.34 | 1406 | 13.5 | 3393 | 12.5 |
| `sym9_317` | 965 | 1.84 | 1464 | 17.4 | 2477 | 12.2 |
| `5xp1_194` | 132 | 0.233 | 121 | 1.09 | 499 | 2.16 |
| `alu1_198` | 58 | 0.164 | 85 | 0.635 | 666 | 2.59 |
| `cm150a_210` | 84 | 0.342 | 76 | 0.705 | 749 | 2.89 |
| `dk27_225` | 65 | 0.276 | 72 | 0.664 | 451 | 2.64 |
| `mlp4_245` | 200 | 0.339 | 243 | 3.16 | 751 | 3.57 |
| `pcler8_248` | 82 | 0.155 | 113 | 0.928 | 695 | 2.61 |
| `C7552_205` | 101 | 0.195 | 122 | 0.967 | 662 | 2.67 |
| `add6_196` | 271 | 0.3 | 446 | 5.44 | 1142 | 4.76 |
| `apla_203` | 311 | 2.15 | 234 | 5.34 | 942 | 6.88 |
| `cm151a_211` | 117 | 0.227 | 171 | 1.57 | 1173 | 4.1 |
| `cm163a_213` | 101 | 0.205 | 128 | 1.15 | 1192 | 3.97 |
| `cu_219` | 143 | 0.631 | 213 | 2.49 | 1067 | 4.79 |
| `dk17_224` | 200 | 1.98 | 176 | 3.25 | 744 | 6.3 |
| `example2_231` | 220 | 0.594 | 223 | 3.29 | 669 | 3.51 |

`qcec` configuration: `{"run_alternating_checker": true, "run_simulation_checker": false, "run_zx_checker": false, "run_construction_checker": false, "parallel": false}`. Median wall time of `qcec.verify` versus QCEC's own reported check and preprocessing times (ms); the circuit conversion to `QuantumComputation` is excluded from the timed runs.

| circuit | workload | verdict | wall | check | preprocessing |
|---|---|---|---:|---:|---:|
| `c2_181` | equiv | equivalent | 6.95 | 5.26 | 0.682 |
| `c2_181` | nonequiv | not_equivalent | 3.42 | 1.93 | 0.594 |
| `mod5adder_306` | equiv | equivalent | 12.1 | 10.4 | 0.687 |
| `mod5adder_306` | nonequiv | not_equivalent | 3.55 | 2.1 | 0.633 |
| `rd73_312` | equiv | equivalent | 43 | 40.6 | 0.57 |
| `rd73_312` | nonequiv | not_equivalent | 7.59 | 6.28 | 0.531 |
| `rd84_313` | equiv | equivalent | 35.8 | 33.5 | 0.7 |
| `rd84_313` | nonequiv | not_equivalent | 5.67 | 4.22 | 0.626 |
| `sym9_317` | equiv | equivalent | 5.24 | 3.91 | 0.545 |
| `sym9_317` | nonequiv | not_equivalent | 3.38 | 2.12 | 0.513 |
| `5xp1_194` | equiv | equivalent | 3.16 | 1.65 | 0.588 |
| `5xp1_194` | nonequiv | not_equivalent | 3 | 1.66 | 0.54 |
| `alu1_198` | equiv | equivalent | 3.32 | 2.13 | 0.458 |
| `alu1_198` | nonequiv | not_equivalent | 2.79 | 1.8 | 0.441 |
| `cm150a_210` | equiv | equivalent | 3.4 | 2.06 | 0.516 |
| `cm150a_210` | nonequiv | not_equivalent | 3.29 | 1.99 | 0.5 |
| `dk27_225` | equiv | equivalent | 3.21 | 2.08 | 0.443 |
| `dk27_225` | nonequiv | not_equivalent | 2.56 | 1.47 | 0.429 |
| `mlp4_245` | equiv | equivalent | 3.62 | 1.95 | 0.735 |
| `mlp4_245` | nonequiv | not_equivalent | 2.19 | 0.632 | 0.673 |
| `pcler8_248` | equiv | equivalent | 1.36 | 0.382 | 0.44 |
| `pcler8_248` | nonequiv | not_equivalent | 3.38 | 2.14 | 0.437 |
| `C7552_205` | equiv | equivalent | 3.74 | 2.26 | 0.579 |
| `C7552_205` | nonequiv | not_equivalent | 3.33 | 1.94 | 0.54 |
| `add6_196` | equiv | equivalent | 13.5 | 10.7 | 1.07 |
| `add6_196` | nonequiv | not_equivalent | 4.45 | 2.13 | 1.11 |
| `apla_203` | equiv | equivalent | 5.06 | 3.21 | 0.718 |
| `apla_203` | nonequiv | not_equivalent | 3.37 | 1.82 | 0.632 |
| `cm151a_211` | equiv | equivalent | 2.89 | 1.65 | 0.506 |
| `cm151a_211` | nonequiv | not_equivalent | 2.82 | 1.61 | 0.491 |
| `cm163a_213` | equiv | equivalent | 3.01 | 1.72 | 0.523 |
| `cm163a_213` | nonequiv | not_equivalent | 2.66 | 1.47 | 0.485 |
| `cu_219` | equiv | equivalent | 2.88 | 1.62 | 0.512 |
| `cu_219` | nonequiv | not_equivalent | 2.78 | 1.57 | 0.494 |
| `dk17_224` | equiv | equivalent | 3.34 | 1.97 | 0.554 |
| `dk17_224` | nonequiv | not_equivalent | 3.22 | 1.9 | 0.529 |
| `example2_231` | equiv | equivalent | 7.06 | 4.94 | 0.838 |
| `example2_231` | nonequiv | not_equivalent | 5.36 | 3.43 | 0.76 |

## Comparison with the historical handoff (`simulate`)

Source: COMPARAISON_EXISTANT.md, frozen comparison of 27 Oct 2026 (user-supplied handoff), table 'Résultat principal sur les circuits COMPLETS'. historical, externally produced; not reproduced by these files. Different machine and different (reconstructed) code: compare speedup ratios, not absolute times.

| circuit | copy_set hist / `sparse-copy` here (ms) | fast_set hist / `sparse` here (ms) | zdd hist / `zdd` here (ms) | auto_zdd hist / `auto-zdd` here (ms) | auto_zdd speedup hist | here |
|---|---|---|---|---|---|---|
| `c2_181` | 226 / 160 | 209 / 155 | 0.835 / 2.74 | 2.28 / 4.35 | 99.31× | 36.78× |
| `mod5adder_306` | 0.173 / 0.225 | 0.146 / 0.206 | 1.12 / 0.73 | 0.179 / 0.248 | 0.97× | 0.91× |
| `rd73_312` | 0.205 / 0.221 | 0.137 / 0.177 | 1.3 / 0.505 | 0.15 / 0.201 | 1.37× | 1.10× |
| `rd84_313` | 0.382 / 0.476 | 0.299 / 0.368 | 2.32 / 0.889 | 0.321 / 0.41 | 1.19× | 1.16× |
| `sym9_317` | 0.532 / 0.529 | 0.309 / 0.419 | 2.39 / 0.842 | 0.31 / 0.463 | 1.72× | 1.14× |
| `5xp1_194` | 0.212 / 0.216 | 0.173 / 0.183 | 0.764 / 0.48 | 0.202 / 0.217 | 1.05× | 1.00× |
| `alu1_198` | 0.046 / 0.052 | 0.039 / 0.0508 | 0.195 / 0.126 | 0.048 / 0.0633 | 0.96× | 0.82× |
| `dk27_225` | 0.066 / 0.0682 | 0.063 / 0.0708 | 0.185 / 0.0999 | 0.073 / 0.0805 | 0.90× | 0.85× |
| `cm150a_210` | 0.198 / 0.2 | 0.117 / 0.141 | 0.605 / 0.571 | 0.134 / 0.157 | 1.48× | 1.28× |
| `pcler8_248` | 0.042 / 0.048 | 0.036 / 0.0448 | 0.169 / 0.106 | 0.044 / 0.0558 | 0.95× | 0.86× |
| `mlp4_245` | 0.434 / 0.408 | 0.302 / 0.341 | 1.51 / 0.958 | 0.342 / 0.395 | 1.27× | 1.03× |
