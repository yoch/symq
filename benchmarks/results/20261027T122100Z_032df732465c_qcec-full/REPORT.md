# Benchmark report

- symq commit `032df732465c66253709e9bd9ccef236f8052dc1` (dirty: False), started 2026-10-27T12:21:00Z
- CPython 3.12.3 on Linux-6.12.94+-x86_64-with-glibc2.39
- CPU: Intel(R) Xeon(R) Processor (4 usable of 4), RAM 15.6 GiB
- Corpus: https://github.com/munich-quantum-toolkit/qcec @ `98d6784176bfeb6ef923d4d0220e8d486dc1982f`, manifest sha256 `d3771d0cba987d7f…`
- Protocol: 1 warmup + median of 7 timed runs per cell; time.perf_counter around one run, no instrumentation; tracemalloc peak from a separate untimed run; ru_maxrss of the worker; one fresh worker process per cell, cells run sequentially; per-run budget 60.0 s.
- Times are milliseconds. Sub-millisecond medians are sensitive to scheduling, GC and CPU frequency; no confidence interval is claimed.

## Correctness checks

- All backends that completed a cell produced identical output polynomials (simulate) or verdicts and differing output (equiv/nonequiv). No wrong verdict, no worker error.

| backend | ok | refused:degree | refused:width |
|---|---:|---:|---:|
| `reference` | 57 | 0 | 0 |
| `sparse-copy` | 57 | 0 | 0 |
| `sparse` | 57 | 0 | 0 |
| `zdd` | 57 | 0 | 0 |
| `adaptive-wire` | 57 | 0 | 0 |
| `auto-zdd` | 57 | 0 | 0 |
| `packed` | 0 | 57 | 0 |
| `packed-fallback` | 57 | 0 | 0 |
| `truthtable` | 12 | 0 | 45 |

Rejected before benchmarking (outside the X/CX/CCX/MCX model):
- `c2_182`: unsupported statement: 'ctrl @ U(pi/2,-pi/2,pi/2) q[0], q[2]'

## Workload `simulate` — median ms

| circuit | split | width | gates | `reference` | `sparse-copy` | `sparse` | `zdd` | `adaptive-wire` | `auto-zdd` | `packed` | `packed-fallback` | `truthtable` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 160 | 160 | 164 | 3.77 | 15.6 | 5.42 | refused (degree) | 163 | refused (width) |
| `mod5adder_306` | dev | 32 | 110 | 0.551 | 0.231 | 0.2 | 1.51 | 0.231 | 0.228 | refused (degree) | 0.537 | refused (width) |
| `rd73_312` | dev | 25 | 76 | 0.516 | 0.222 | 0.175 | 0.919 | 0.212 | 0.206 | refused (degree) | 0.529 | refused (width) |
| `rd84_313` | dev | 34 | 113 | 0.968 | 0.467 | 0.377 | 2.16 | 0.406 | 0.403 | refused (degree) | 0.919 | refused (width) |
| `sym9_317` | dev | 27 | 64 | 1.08 | 0.52 | 0.403 | 2.62 | 0.437 | 0.426 | refused (degree) | 0.601 | refused (width) |
| `5xp1_194` | holdout | 17 | 85 | 0.504 | 0.217 | 0.181 | 0.461 | 0.217 | 0.215 | refused (degree) | 0.562 | 4.87 |
| `alu1_198` | holdout | 20 | 32 | 0.137 | 0.0508 | 0.0485 | 0.129 | 0.0625 | 0.0633 | refused (degree) | 0.171 | refused (width) |
| `cm150a_210` | holdout | 22 | 53 | 0.461 | 0.192 | 0.137 | 0.56 | 0.16 | 0.153 | refused (degree) | 0.398 | refused (width) |
| `dk27_225` | holdout | 18 | 24 | 0.162 | 0.0696 | 0.0673 | 0.0965 | 0.0814 | 0.0801 | refused (degree) | 0.195 | 9.97 |
| `mlp4_245` | holdout | 16 | 131 | 0.91 | 0.391 | 0.321 | 0.925 | 0.369 | 0.37 | refused (degree) | 0.927 | 2.37 |
| `pcler8_248` | holdout | 21 | 22 | 0.126 | 0.0456 | 0.0434 | 0.109 | 0.0542 | 0.0547 | refused (degree) | 0.163 | refused (width) |
| `C7552_205` | extension | 21 | 80 | 0.514 | 0.209 | 0.199 | 0.321 | 0.222 | 0.232 | refused (degree) | 0.608 | refused (width) |
| `add6_196` | extension | 19 | 229 | 2.57 | 1.21 | 0.669 | 2.59 | 0.713 | 0.714 | refused (degree) | 1.95 | refused (width) |
| `apla_203` | extension | 22 | 80 | 2.87 | 1.53 | 1.26 | 0.763 | 1.31 | 1.32 | refused (degree) | 2.87 | refused (width) |
| `cm151a_211` | extension | 28 | 33 | 0.229 | 0.0974 | 0.0932 | 0.188 | 0.106 | 0.11 | refused (degree) | 0.305 | refused (width) |
| `cm163a_213` | extension | 29 | 39 | 0.21 | 0.0798 | 0.0787 | 0.196 | 0.0925 | 0.0889 | refused (degree) | 0.279 | refused (width) |
| `cu_219` | extension | 25 | 40 | 0.514 | 0.219 | 0.206 | 0.319 | 0.221 | 0.224 | refused (degree) | 0.592 | refused (width) |
| `dk17_224` | extension | 21 | 49 | 1.24 | 0.608 | 0.614 | 0.38 | 0.632 | 0.621 | refused (degree) | 1.38 | refused (width) |
| `example2_231` | extension | 16 | 157 | 1.85 | 0.87 | 0.502 | 2.02 | 0.567 | 0.555 | refused (degree) | 1.47 | 2.46 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `reference` | dev | n=4, median 0.46×, geomean 0.45×, range 0.42–0.48× | 1.0× |
| `reference` | holdout | n=6, median 0.42×, geomean 0.41×, range 0.36–0.43× | — |
| `reference` | extension | n=8, median 0.45×, geomean 0.45×, range 0.38–0.53× | — |
| `sparse` | dev | n=4, median 1.25×, geomean 1.24×, range 1.15–1.29× | 1.0× |
| `sparse` | holdout | n=6, median 1.12×, geomean 1.15×, range 1.04–1.40× | — |
| `sparse` | extension | n=8, median 1.06×, geomean 1.21×, range 0.99–1.80× | — |
| `zdd` | dev | n=4, median 0.21×, geomean 0.20×, range 0.15–0.24× | 42.4× |
| `zdd` | holdout | n=6, median 0.42×, geomean 0.45×, range 0.34–0.72× | — |
| `zdd` | extension | n=8, median 0.59×, geomean 0.70×, range 0.41–2.01× | — |
| `adaptive-wire` | dev | n=4, median 1.10×, geomean 1.09×, range 1.00–1.19× | 10.3× |
| `adaptive-wire` | holdout | n=6, median 0.93×, geomean 0.95×, range 0.81–1.20× | — |
| `adaptive-wire` | extension | n=8, median 0.98×, geomean 1.10×, range 0.86–1.69× | — |
| `auto-zdd` | dev | n=4, median 1.12×, geomean 1.11×, range 1.01–1.22× | 29.4× |
| `auto-zdd` | holdout | n=6, median 0.94×, geomean 0.96×, range 0.80–1.25× | — |
| `auto-zdd` | extension | n=8, median 0.98×, geomean 1.10×, range 0.89–1.69× | — |
| `packed-fallback` | dev | n=4, median 0.47×, geomean 0.53×, range 0.42–0.87× | 1.0× |
| `packed-fallback` | holdout | n=6, median 0.37×, geomean 0.36×, range 0.28–0.48× | — |
| `packed-fallback` | extension | n=8, median 0.41×, geomean 0.42×, range 0.29–0.62× | — |
| `truthtable` | holdout | n=3, median 0.04×, geomean 0.04×, range 0.01–0.17× | — |
| `truthtable` | extension | n=1, median 0.35×, geomean 0.35×, range 0.35–0.35× | — |

## Workload `equiv` — median ms

| circuit | split | width | gates | `reference` | `sparse-copy` | `sparse` | `zdd` | `adaptive-wire` | `auto-zdd` | `packed` | `packed-fallback` | `truthtable` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 2540 | 4595 | 4473 | 6.97 | 32.4 | 10.2 | refused (degree) | 4532 | refused (width) |
| `mod5adder_306` | dev | 32 | 110 | 4.03 | 2.75 | 2.75 | 6.06 | 7.82 | 2.8 | refused (degree) | 3.5 | refused (width) |
| `rd73_312` | dev | 25 | 76 | 1.3 | 0.56 | 0.45 | 1.36 | 0.513 | 0.495 | refused (degree) | 1.26 | refused (width) |
| `rd84_313` | dev | 34 | 113 | 3.15 | 1.71 | 1.47 | 5.41 | 1.54 | 1.54 | refused (degree) | 2.8 | refused (width) |
| `sym9_317` | dev | 27 | 64 | 4.08 | 2.94 | 2.69 | 4.89 | 6.18 | 2.73 | refused (degree) | 3.08 | refused (width) |
| `5xp1_194` | holdout | 17 | 85 | 1.68 | 0.862 | 0.792 | 1.61 | 0.886 | 0.88 | refused (degree) | 1.6 | 5.4 |
| `alu1_198` | holdout | 20 | 32 | 0.391 | 0.143 | 0.137 | 0.297 | 0.166 | 0.168 | refused (degree) | 0.412 | refused (width) |
| `cm150a_210` | holdout | 22 | 53 | 1.16 | 0.56 | 0.429 | 0.914 | 0.465 | 0.483 | refused (degree) | 0.973 | refused (width) |
| `dk27_225` | holdout | 18 | 24 | 0.382 | 0.158 | 0.15 | 0.155 | 0.187 | 0.177 | refused (degree) | 0.394 | 10.5 |
| `mlp4_245` | holdout | 16 | 131 | 2.76 | 1.49 | 1.34 | 5.57 | 1.47 | 1.46 | refused (degree) | 2.71 | 2.86 |
| `pcler8_248` | holdout | 21 | 22 | 0.287 | 0.099 | 0.09 | 0.151 | 0.112 | 0.111 | refused (degree) | 0.296 | refused (width) |
| `C7552_205` | extension | 21 | 80 | 1.3 | 0.545 | 0.538 | 0.777 | 0.594 | 0.578 | refused (degree) | 1.39 | refused (width) |
| `add6_196` | extension | 19 | 229 | 8.18 | 4.36 | 4.05 | 26.7 | 4.27 | 4.21 | refused (degree) | 6.17 | refused (width) |
| `apla_203` | extension | 22 | 80 | 28.3 | 36.6 | 36.1 | 1.88 | 9.69 | 5.87 | refused (degree) | 39.6 | refused (width) |
| `cm151a_211` | extension | 28 | 33 | 0.5 | 0.215 | 0.202 | 0.27 | 0.226 | 0.23 | refused (degree) | 0.589 | refused (width) |
| `cm163a_213` | extension | 29 | 39 | 0.508 | 0.204 | 0.19 | 0.335 | 0.231 | 0.229 | refused (degree) | 0.581 | refused (width) |
| `cu_219` | extension | 25 | 40 | 1.26 | 0.588 | 0.57 | 0.523 | 0.598 | 0.877 | refused (degree) | 1.32 | refused (width) |
| `dk17_224` | extension | 21 | 49 | 4.59 | 2.75 | 2.78 | 0.648 | 3.09 | 2.84 | refused (degree) | 4.34 | refused (width) |
| `example2_231` | extension | 16 | 157 | 5.45 | 2.84 | 2.18 | 5.93 | 2.35 | 2.33 | refused (degree) | 4.28 | 3.03 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `reference` | dev | n=4, median 0.61×, geomean 0.58×, range 0.43–0.72× | 1.8× |
| `reference` | holdout | n=6, median 0.45×, geomean 0.44×, range 0.35–0.54× | — |
| `reference` | extension | n=8, median 0.49×, geomean 0.54×, range 0.40–1.29× | — |
| `sparse` | dev | n=4, median 1.13×, geomean 1.12×, range 1.00–1.25× | 1.0× |
| `sparse` | holdout | n=6, median 1.09×, geomean 1.11×, range 1.04–1.31× | — |
| `sparse` | extension | n=8, median 1.05×, geomean 1.07×, range 0.99–1.30× | — |
| `zdd` | dev | n=4, median 0.43×, geomean 0.43×, range 0.32–0.60× | 659.5× |
| `zdd` | holdout | n=6, median 0.57×, geomean 0.55×, range 0.27–1.02× | — |
| `zdd` | extension | n=8, median 0.75×, geomean 1.12×, range 0.16–19.48× | — |
| `adaptive-wire` | dev | n=4, median 0.78×, geomean 0.67×, range 0.35–1.11× | 141.7× |
| `adaptive-wire` | holdout | n=6, median 0.93×, geomean 0.96×, range 0.84–1.20× | — |
| `adaptive-wire` | extension | n=8, median 0.97×, geomean 1.15×, range 0.88–3.78× | — |
| `auto-zdd` | dev | n=4, median 1.10×, geomean 1.08×, range 0.98–1.13× | 448.8× |
| `auto-zdd` | holdout | n=6, median 0.94×, geomean 0.96×, range 0.85–1.16× | — |
| `auto-zdd` | extension | n=8, median 0.96×, geomean 1.19×, range 0.67–6.24× | — |
| `packed-fallback` | dev | n=4, median 0.70×, geomean 0.67×, range 0.44–0.96× | 1.0× |
| `packed-fallback` | holdout | n=6, median 0.47×, geomean 0.45×, range 0.33–0.58× | — |
| `packed-fallback` | extension | n=8, median 0.54×, geomean 0.53×, range 0.35–0.92× | — |
| `truthtable` | holdout | n=3, median 0.16×, geomean 0.11×, range 0.02–0.52× | — |
| `truthtable` | extension | n=1, median 0.94×, geomean 0.94×, range 0.94–0.94× | — |

## Workload `nonequiv` — median ms

| circuit | split | width | gates | `reference` | `sparse-copy` | `sparse` | `zdd` | `adaptive-wire` | `auto-zdd` | `packed` | `packed-fallback` | `truthtable` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 328 | 327 | 314 | 4.01 | 29 | 7.3 | refused (degree) | 329 | refused (width) |
| `mod5adder_306` | dev | 32 | 110 | 1.2 | 0.513 | 0.468 | 1.97 | 0.53 | 0.521 | refused (degree) | 1.08 | refused (width) |
| `rd73_312` | dev | 25 | 76 | 1.08 | 0.482 | 0.401 | 1.23 | 0.449 | 0.439 | refused (degree) | 1.09 | refused (width) |
| `rd84_313` | dev | 34 | 113 | 2.07 | 1.05 | 0.823 | 2.47 | 0.9 | 0.902 | refused (degree) | 1.83 | refused (width) |
| `sym9_317` | dev | 27 | 64 | 2.26 | 1.11 | 0.871 | 2.71 | 0.91 | 0.873 | refused (degree) | 1.19 | refused (width) |
| `5xp1_194` | holdout | 17 | 85 | 1.11 | 0.488 | 0.472 | 0.73 | 0.482 | 0.472 | refused (degree) | 1.1 | 5.42 |
| `alu1_198` | holdout | 20 | 32 | 0.303 | 0.128 | 0.122 | 0.236 | 0.148 | 0.142 | refused (degree) | 0.344 | refused (width) |
| `cm150a_210` | holdout | 22 | 53 | 0.937 | 0.421 | 0.305 | 0.706 | 0.342 | 0.336 | refused (degree) | 0.793 | refused (width) |
| `dk27_225` | holdout | 18 | 24 | 0.355 | 0.155 | 0.155 | 0.166 | 0.182 | 0.178 | refused (degree) | 0.376 | 10.5 |
| `mlp4_245` | holdout | 16 | 131 | 2.1 | 1.04 | 0.87 | 1.79 | 0.969 | 0.962 | refused (degree) | 2.08 | 2.86 |
| `pcler8_248` | holdout | 21 | 22 | 0.291 | 0.114 | 0.113 | 0.243 | 0.13 | 0.129 | refused (degree) | 0.329 | refused (width) |
| `C7552_205` | extension | 21 | 80 | 1.05 | 0.47 | 0.443 | 0.534 | 0.501 | 0.513 | refused (degree) | 1.23 | refused (width) |
| `add6_196` | extension | 19 | 229 | 5.33 | 2.6 | 1.49 | 3.19 | 1.65 | 1.62 | refused (degree) | 4.12 | refused (width) |
| `apla_203` | extension | 22 | 80 | 7.71 | 4.9 | 4.25 | 1.43 | 3.62 | 4.31 | refused (degree) | 7.45 | refused (width) |
| `cm151a_211` | extension | 28 | 33 | 0.514 | 0.212 | 0.202 | 0.332 | 0.235 | 0.24 | refused (degree) | 0.589 | refused (width) |
| `cm163a_213` | extension | 29 | 39 | 0.449 | 0.183 | 0.178 | 0.312 | 0.208 | 0.209 | refused (degree) | 0.504 | refused (width) |
| `cu_219` | extension | 25 | 40 | 1.1 | 0.46 | 0.453 | 0.446 | 0.499 | 0.499 | refused (degree) | 1.15 | refused (width) |
| `dk17_224` | extension | 21 | 49 | 2.53 | 1.29 | 1.28 | 0.568 | 1.31 | 1.32 | refused (degree) | 2.77 | refused (width) |
| `example2_231` | extension | 16 | 157 | 4.2 | 2.08 | 1.3 | 4.16 | 1.41 | 1.41 | refused (degree) | 3.53 | 3.29 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `reference` | dev | n=4, median 0.47×, geomean 0.47×, range 0.43–0.51× | 1.0× |
| `reference` | holdout | n=6, median 0.44×, geomean 0.44×, range 0.39–0.49× | — |
| `reference` | extension | n=8, median 0.47×, geomean 0.47×, range 0.41–0.64× | — |
| `sparse` | dev | n=4, median 1.24×, geomean 1.21×, range 1.10–1.28× | 1.0× |
| `sparse` | holdout | n=6, median 1.04×, geomean 1.10×, range 1.00–1.38× | — |
| `sparse` | extension | n=8, median 1.05×, geomean 1.18×, range 1.01–1.75× | — |
| `zdd` | dev | n=4, median 0.40×, geomean 0.37×, range 0.26–0.43× | 81.6× |
| `zdd` | holdout | n=6, median 0.59×, geomean 0.62×, range 0.47–0.94× | — |
| `zdd` | extension | n=8, median 0.85×, geomean 1.01×, range 0.50–3.42× | — |
| `adaptive-wire` | dev | n=4, median 1.12×, geomean 1.10×, range 0.97–1.22× | 11.3× |
| `adaptive-wire` | holdout | n=6, median 0.94×, geomean 0.98×, range 0.86–1.23× | — |
| `adaptive-wire` | extension | n=8, median 0.96×, geomean 1.10×, range 0.88–1.58× | — |
| `auto-zdd` | dev | n=4, median 1.13×, geomean 1.13×, range 0.99–1.28× | 44.8× |
| `auto-zdd` | holdout | n=6, median 0.97×, geomean 1.00×, range 0.87–1.26× | — |
| `auto-zdd` | extension | n=8, median 0.95×, geomean 1.07×, range 0.88–1.60× | — |
| `packed-fallback` | dev | n=4, median 0.53×, geomean 0.58×, range 0.44–0.94× | 1.0× |
| `packed-fallback` | holdout | n=6, median 0.43×, geomean 0.43×, range 0.35–0.53× | — |
| `packed-fallback` | extension | n=8, median 0.43×, geomean 0.47×, range 0.36–0.66× | — |
| `truthtable` | holdout | n=3, median 0.09×, geomean 0.08×, range 0.01–0.36× | — |
| `truthtable` | extension | n=1, median 0.63×, geomean 0.63×, range 0.63–0.63× | — |

## Memory and representation changes (`simulate`)

tracemalloc peak in KiB (separate untimed run); worker peak RSS in MiB, which includes the interpreter.

| circuit | `reference` KiB | `sparse-copy` KiB | `sparse` KiB | `zdd` KiB | `adaptive-wire` KiB | `auto-zdd` KiB | `packed` KiB | `packed-fallback` KiB | `truthtable` KiB | max RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | 5122 | 4910 | 5060 | 745 | 564 | 744 | — | 5116 | — | 31 |
| `mod5adder_306` | 58 | 52 | 58 | 215 | 59 | 59 | — | 97 | — | 22 |
| `rd73_312` | 59 | 55 | 50 | 144 | 51 | 51 | — | 63 | — | 22 |
| `rd84_313` | 121 | 122 | 96 | 440 | 97 | 97 | — | 129 | — | 22 |
| `sym9_317` | 195 | 179 | 154 | 468 | 155 | 155 | — | 186 | — | 23 |
| `5xp1_194` | 24 | 18 | 19 | 62 | 19 | 19 | — | 28 | 714 | 23 |
| `alu1_198` | 14 | 12 | 11 | 19 | 13 | 13 | — | 26 | — | 22 |
| `cm150a_210` | 45 | 41 | 24 | 88 | 25 | 25 | — | 39 | — | 22 |
| `dk27_225` | 28 | 24 | 21 | 15 | 22 | 22 | — | 33 | 1474 | 25 |
| `mlp4_245` | 23 | 22 | 20 | 130 | 21 | 21 | — | 28 | 328 | 22 |
| `pcler8_248` | 13 | 10 | 9 | 15 | 10 | 10 | — | 25 | — | 22 |
| `C7552_205` | 21 | 18 | 18 | 41 | 19 | 19 | — | 35 | — | 22 |
| `add6_196` | 38 | 37 | 28 | 404 | 29 | 29 | — | 43 | — | 23 |
| `apla_203` | 338 | 325 | 274 | 131 | 275 | 275 | — | 292 | — | 22 |
| `cm151a_211` | 20 | 17 | 16 | 31 | 18 | 18 | — | 52 | — | 22 |
| `cm163a_213` | 17 | 14 | 13 | 29 | 15 | 15 | — | 49 | — | 22 |
| `cu_219` | 54 | 52 | 40 | 39 | 41 | 41 | — | 61 | — | 22 |
| `dk17_224` | 189 | 174 | 163 | 64 | 164 | 164 | — | 179 | — | 22 |
| `example2_231` | 58 | 56 | 38 | 298 | 38 | 38 | — | 45 | 328 | 22 |

| circuit | `zdd` nodes | `auto-zdd` switch gate | `auto-zdd` conversions | `adaptive-wire` conversions | `packed-fallback` conversions |
|---|---:|---:|---:|---:|---:|
| `c2_181` | 2919 | 32 | 35 | 35 | 96 |
| `mod5adder_306` | 1355 | none | 0 | 0 | 88 |
| `rd73_312` | 818 | none | 0 | 0 | 79 |
| `rd84_313` | 1658 | none | 0 | 0 | 100 |
| `sym9_317` | 1903 | none | 0 | 0 | 60 |
| `5xp1_194` | 414 | none | 0 | 0 | 197 |
| `alu1_198` | 127 | none | 0 | 0 | 58 |
| `cm150a_210` | 619 | none | 0 | 0 | 132 |
| `dk27_225` | 97 | none | 0 | 0 | 34 |
| `mlp4_245` | 842 | none | 0 | 0 | 457 |
| `pcler8_248` | 114 | none | 0 | 0 | 57 |
| `C7552_205` | 275 | none | 0 | 0 | 284 |
| `add6_196` | 2322 | none | 0 | 0 | 822 |
| `apla_203` | 714 | none | 0 | 0 | 415 |
| `cm151a_211` | 190 | none | 0 | 0 | 114 |
| `cm163a_213` | 200 | none | 0 | 0 | 103 |
| `cu_219` | 308 | none | 0 | 0 | 141 |
| `dk17_224` | 375 | none | 0 | 0 | 192 |
| `example2_231` | 2043 | none | 0 | 0 | 547 |

## Comparison with the historical handoff (`simulate`)

Source: COMPARAISON_EXISTANT.md, frozen comparison of 27 Oct 2026 (user-supplied handoff), table 'Résultat principal sur les circuits COMPLETS'. historical, externally produced; not reproduced by these files. Different machine and different (reconstructed) code: compare speedup ratios, not absolute times.

| circuit | qant_set hist / `sparse-copy` here (ms) | fast_set hist / `sparse` here (ms) | zdd hist / `zdd` here (ms) | auto_zdd hist / `auto-zdd` here (ms) | auto_zdd speedup hist | here |
|---|---|---|---|---|---|---|
| `c2_181` | 226 / 160 | 209 / 164 | 0.835 / 3.77 | 2.28 / 5.42 | 99.31× | 29.43× |
| `mod5adder_306` | 0.173 / 0.231 | 0.146 / 0.2 | 1.12 / 1.51 | 0.179 / 0.228 | 0.97× | 1.01× |
| `rd73_312` | 0.205 / 0.222 | 0.137 / 0.175 | 1.3 / 0.919 | 0.15 / 0.206 | 1.37× | 1.08× |
| `rd84_313` | 0.382 / 0.467 | 0.299 / 0.377 | 2.32 / 2.16 | 0.321 / 0.403 | 1.19× | 1.16× |
| `sym9_317` | 0.532 / 0.52 | 0.309 / 0.403 | 2.39 / 2.62 | 0.31 / 0.426 | 1.72× | 1.22× |
| `5xp1_194` | 0.212 / 0.217 | 0.173 / 0.181 | 0.764 / 0.461 | 0.202 / 0.215 | 1.05× | 1.01× |
| `alu1_198` | 0.046 / 0.0508 | 0.039 / 0.0485 | 0.195 / 0.129 | 0.048 / 0.0633 | 0.96× | 0.80× |
| `dk27_225` | 0.066 / 0.0696 | 0.063 / 0.0673 | 0.185 / 0.0965 | 0.073 / 0.0801 | 0.90× | 0.87× |
| `cm150a_210` | 0.198 / 0.192 | 0.117 / 0.137 | 0.605 / 0.56 | 0.134 / 0.153 | 1.48× | 1.25× |
| `pcler8_248` | 0.042 / 0.0456 | 0.036 / 0.0434 | 0.169 / 0.109 | 0.044 / 0.0547 | 0.95× | 0.83× |
| `mlp4_245` | 0.434 / 0.391 | 0.302 / 0.321 | 1.51 / 0.925 | 0.342 / 0.37 | 1.27× | 1.06× |
