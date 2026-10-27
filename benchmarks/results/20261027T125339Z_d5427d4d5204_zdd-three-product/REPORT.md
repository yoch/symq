# Benchmark report

- symq commit `d5427d4d5204d61245991c86379ebd268066bf09` (dirty: False), started 2026-10-27T12:53:39Z
- CPython 3.12.3 on Linux-6.12.94+-x86_64-with-glibc2.39
- CPU: Intel(R) Xeon(R) Processor (4 usable of 4), RAM 15.6 GiB
- Corpus: https://github.com/munich-quantum-toolkit/qcec @ `98d6784176bfeb6ef923d4d0220e8d486dc1982f`, manifest sha256 `d3771d0cba987d7f…`
- Protocol: 1 warmup + median of 7 timed runs per cell; time.perf_counter around one run, no instrumentation; tracemalloc peak from a separate untimed run; ru_maxrss of the worker; one fresh worker process per cell, cells run sequentially; per-run budget 60.0 s.
- Times are milliseconds. Sub-millisecond medians are sensitive to scheduling, GC and CPU frequency; no confidence interval is claimed.

## Correctness checks

- All backends that completed a cell produced identical output polynomials (simulate) or verdicts and differing output (equiv/nonequiv). No wrong verdict, no worker error.

| backend | ok |
|---|---:|
| `sparse-copy` | 57 |
| `sparse` | 57 |
| `zdd` | 57 |
| `auto-zdd` | 57 |

Rejected before benchmarking (outside the X/CX/CCX/MCX model):
- `c2_182`: unsupported statement: 'ctrl @ U(pi/2,-pi/2,pi/2) q[0], q[2]'

## Workload `simulate` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` |
|---|---|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 162 | 155 | 2.65 | 4.31 |
| `mod5adder_306` | dev | 32 | 110 | 0.24 | 0.209 | 0.711 | 0.227 |
| `rd73_312` | dev | 25 | 76 | 0.23 | 0.18 | 0.505 | 0.206 |
| `rd84_313` | dev | 34 | 113 | 0.466 | 0.368 | 0.897 | 0.402 |
| `sym9_317` | dev | 27 | 64 | 0.517 | 0.407 | 0.839 | 0.421 |
| `5xp1_194` | holdout | 17 | 85 | 0.214 | 0.186 | 0.469 | 0.216 |
| `alu1_198` | holdout | 20 | 32 | 0.0536 | 0.0495 | 0.127 | 0.0629 |
| `cm150a_210` | holdout | 22 | 53 | 0.195 | 0.143 | 0.554 | 0.158 |
| `dk27_225` | holdout | 18 | 24 | 0.0688 | 0.0729 | 0.0995 | 0.0787 |
| `mlp4_245` | holdout | 16 | 131 | 0.399 | 0.325 | 0.94 | 0.372 |
| `pcler8_248` | holdout | 21 | 22 | 0.0465 | 0.0455 | 0.103 | 0.052 |
| `C7552_205` | extension | 21 | 80 | 0.209 | 0.208 | 0.323 | 0.234 |
| `add6_196` | extension | 19 | 229 | 1.21 | 0.673 | 2.56 | 0.729 |
| `apla_203` | extension | 22 | 80 | 1.52 | 1.26 | 0.789 | 1.31 |
| `cm151a_211` | extension | 28 | 33 | 0.099 | 0.0908 | 0.191 | 0.112 |
| `cm163a_213` | extension | 29 | 39 | 0.0805 | 0.0767 | 0.201 | 0.0934 |
| `cu_219` | extension | 25 | 40 | 0.221 | 0.213 | 0.328 | 0.227 |
| `dk17_224` | extension | 21 | 49 | 0.619 | 0.599 | 0.396 | 0.629 |
| `example2_231` | extension | 16 | 157 | 0.852 | 0.509 | 2.07 | 0.549 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.27×, geomean 1.24×, range 1.15–1.28× | 1.0× |
| `sparse` | holdout | n=6, median 1.12×, geomean 1.12×, range 0.94–1.36× | — |
| `sparse` | extension | n=8, median 1.07×, geomean 1.21×, range 1.00–1.79× | — |
| `zdd` | dev | n=4, median 0.49×, geomean 0.47×, range 0.34–0.62× | 61.0× |
| `zdd` | holdout | n=6, median 0.44×, geomean 0.46×, range 0.35–0.69× | — |
| `zdd` | extension | n=8, median 0.58×, geomean 0.69×, range 0.40–1.92× | — |
| `auto-zdd` | dev | n=4, median 1.14×, geomean 1.14×, range 1.06–1.23× | 37.5× |
| `auto-zdd` | holdout | n=6, median 0.94×, geomean 0.98×, range 0.85–1.24× | — |
| `auto-zdd` | extension | n=8, median 0.98×, geomean 1.09×, range 0.86–1.65× | — |

## Workload `equiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` |
|---|---|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 4489 | 4431 | 5.53 | 8.96 |
| `mod5adder_306` | dev | 32 | 110 | 2.75 | 2.74 | 6.83 | 2.83 |
| `rd73_312` | dev | 25 | 76 | 0.569 | 0.465 | 0.863 | 0.505 |
| `rd84_313` | dev | 34 | 113 | 1.74 | 1.46 | 3.06 | 1.56 |
| `sym9_317` | dev | 27 | 64 | 2.97 | 2.71 | 4.79 | 2.75 |
| `5xp1_194` | holdout | 17 | 85 | 0.839 | 0.807 | 1.2 | 0.867 |
| `alu1_198` | holdout | 20 | 32 | 0.152 | 0.139 | 0.248 | 0.177 |
| `cm150a_210` | holdout | 22 | 53 | 0.542 | 0.425 | 0.792 | 0.471 |
| `dk27_225` | holdout | 18 | 24 | 0.159 | 0.16 | 0.154 | 0.181 |
| `mlp4_245` | holdout | 16 | 131 | 1.47 | 1.34 | 3.41 | 1.43 |
| `pcler8_248` | holdout | 21 | 22 | 0.0987 | 0.0925 | 0.161 | 0.111 |
| `C7552_205` | extension | 21 | 80 | 0.538 | 0.533 | 0.637 | 0.576 |
| `add6_196` | extension | 19 | 229 | 4.37 | 4.07 | 8.4 | 4.28 |
| `apla_203` | extension | 22 | 80 | 36.5 | 36.1 | 1.48 | 5.5 |
| `cm151a_211` | extension | 28 | 33 | 0.204 | 0.196 | 0.269 | 0.227 |
| `cm163a_213` | extension | 29 | 39 | 0.202 | 0.195 | 0.329 | 0.231 |
| `cu_219` | extension | 25 | 40 | 0.604 | 0.557 | 0.482 | 0.621 |
| `dk17_224` | extension | 21 | 49 | 2.75 | 2.82 | 0.576 | 2.85 |
| `example2_231` | extension | 16 | 157 | 2.85 | 2.19 | 4.18 | 2.34 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.14×, geomean 1.13×, range 1.01–1.22× | 1.0× |
| `sparse` | holdout | n=6, median 1.08×, geomean 1.09×, range 0.99–1.28× | — |
| `sparse` | extension | n=8, median 1.04×, geomean 1.06×, range 0.98–1.30× | — |
| `zdd` | dev | n=4, median 0.59×, geomean 0.55×, range 0.40–0.66× | 811.9× |
| `zdd` | holdout | n=6, median 0.65×, geomean 0.66×, range 0.43–1.03× | — |
| `zdd` | extension | n=8, median 0.80×, geomean 1.46×, range 0.52–24.57× | — |
| `auto-zdd` | dev | n=4, median 1.10×, geomean 1.07×, range 0.97–1.13× | 501.1× |
| `auto-zdd` | holdout | n=6, median 0.93×, geomean 0.96×, range 0.85–1.15× | — |
| `auto-zdd` | extension | n=8, median 0.97×, geomean 1.24×, range 0.87–6.63× | — |

## Workload `nonequiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `auto-zdd` |
|---|---|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 322 | 313 | 2.85 | 6.2 |
| `mod5adder_306` | dev | 32 | 110 | 0.523 | 0.465 | 1.03 | 0.522 |
| `rd73_312` | dev | 25 | 76 | 0.466 | 0.412 | 0.83 | 0.445 |
| `rd84_313` | dev | 34 | 113 | 1.03 | 0.843 | 1.31 | 0.902 |
| `sym9_317` | dev | 27 | 64 | 1.14 | 0.854 | 1.11 | 0.873 |
| `5xp1_194` | holdout | 17 | 85 | 0.477 | 0.44 | 0.699 | 0.483 |
| `alu1_198` | holdout | 20 | 32 | 0.132 | 0.124 | 0.23 | 0.147 |
| `cm150a_210` | holdout | 22 | 53 | 0.423 | 0.308 | 0.778 | 0.342 |
| `dk27_225` | holdout | 18 | 24 | 0.151 | 0.156 | 0.173 | 0.178 |
| `mlp4_245` | holdout | 16 | 131 | 1.04 | 0.86 | 1.81 | 0.969 |
| `pcler8_248` | holdout | 21 | 22 | 0.119 | 0.109 | 0.254 | 0.128 |
| `C7552_205` | extension | 21 | 80 | 0.474 | 0.466 | 0.533 | 0.488 |
| `add6_196` | extension | 19 | 229 | 2.57 | 1.5 | 3.18 | 1.62 |
| `apla_203` | extension | 22 | 80 | 4.89 | 4.25 | 1.22 | 4.34 |
| `cm151a_211` | extension | 28 | 33 | 0.228 | 0.21 | 0.292 | 0.226 |
| `cm163a_213` | extension | 29 | 39 | 0.185 | 0.175 | 0.301 | 0.203 |
| `cu_219` | extension | 25 | 40 | 0.456 | 0.46 | 0.456 | 0.497 |
| `dk17_224` | extension | 21 | 49 | 1.28 | 1.27 | 0.588 | 1.32 |
| `example2_231` | extension | 16 | 157 | 2.07 | 1.3 | 3.92 | 1.4 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.18×, geomean 1.20×, range 1.13–1.33× | 1.0× |
| `sparse` | holdout | n=6, median 1.09×, geomean 1.12×, range 0.96–1.37× | — |
| `sparse` | extension | n=8, median 1.07×, geomean 1.18×, range 0.99–1.71× | — |
| `zdd` | dev | n=4, median 0.67×, geomean 0.69×, range 0.51–1.02× | 112.9× |
| `zdd` | holdout | n=6, median 0.57×, geomean 0.61×, range 0.47–0.87× | — |
| `zdd` | extension | n=8, median 0.85×, geomean 1.06×, range 0.53–3.99× | — |
| `auto-zdd` | dev | n=4, median 1.10×, geomean 1.12×, range 1.00–1.30× | 51.9× |
| `auto-zdd` | holdout | n=6, median 0.96×, geomean 0.99×, range 0.85–1.24× | — |
| `auto-zdd` | extension | n=8, median 0.99×, geomean 1.10×, range 0.91–1.59× | — |

## Memory and representation changes (`simulate`)

tracemalloc peak in KiB (separate untimed run); worker peak RSS in MiB, which includes the interpreter.

| circuit | `sparse-copy` KiB | `sparse` KiB | `zdd` KiB | `auto-zdd` KiB | max RSS MiB |
|---|---:|---:|---:|---:|---:|
| `c2_181` | 4910 | 5060 | 400 | 392 | 31 |
| `mod5adder_306` | 52 | 58 | 130 | 59 | 21 |
| `rd73_312` | 55 | 50 | 82 | 51 | 21 |
| `rd84_313` | 122 | 96 | 172 | 97 | 22 |
| `sym9_317` | 179 | 154 | 177 | 155 | 22 |
| `5xp1_194` | 18 | 19 | 62 | 19 | 21 |
| `alu1_198` | 12 | 11 | 19 | 13 | 21 |
| `cm150a_210` | 41 | 24 | 88 | 25 | 21 |
| `dk27_225` | 24 | 21 | 15 | 22 | 21 |
| `mlp4_245` | 22 | 20 | 130 | 21 | 22 |
| `pcler8_248` | 10 | 9 | 15 | 10 | 21 |
| `C7552_205` | 18 | 18 | 41 | 19 | 21 |
| `add6_196` | 37 | 28 | 404 | 29 | 23 |
| `apla_203` | 325 | 274 | 131 | 275 | 22 |
| `cm151a_211` | 17 | 16 | 31 | 18 | 21 |
| `cm163a_213` | 14 | 13 | 29 | 15 | 21 |
| `cu_219` | 52 | 40 | 39 | 41 | 21 |
| `dk17_224` | 174 | 163 | 64 | 164 | 21 |
| `example2_231` | 56 | 38 | 298 | 38 | 23 |

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

## Comparison with the historical handoff (`simulate`)

Source: COMPARAISON_EXISTANT.md, frozen comparison of 27 Oct 2026 (user-supplied handoff), table 'Résultat principal sur les circuits COMPLETS'. historical, externally produced; not reproduced by these files. Different machine and different (reconstructed) code: compare speedup ratios, not absolute times.

| circuit | copy_set hist / `sparse-copy` here (ms) | fast_set hist / `sparse` here (ms) | zdd hist / `zdd` here (ms) | auto_zdd hist / `auto-zdd` here (ms) | auto_zdd speedup hist | here |
|---|---|---|---|---|---|---|
| `c2_181` | 226 / 162 | 209 / 155 | 0.835 / 2.65 | 2.28 / 4.31 | 99.31× | 37.51× |
| `mod5adder_306` | 0.173 / 0.24 | 0.146 / 0.209 | 1.12 / 0.711 | 0.179 / 0.227 | 0.97× | 1.06× |
| `rd73_312` | 0.205 / 0.23 | 0.137 / 0.18 | 1.3 / 0.505 | 0.15 / 0.206 | 1.37× | 1.12× |
| `rd84_313` | 0.382 / 0.466 | 0.299 / 0.368 | 2.32 / 0.897 | 0.321 / 0.402 | 1.19× | 1.16× |
| `sym9_317` | 0.532 / 0.517 | 0.309 / 0.407 | 2.39 / 0.839 | 0.31 / 0.421 | 1.72× | 1.23× |
| `5xp1_194` | 0.212 / 0.214 | 0.173 / 0.186 | 0.764 / 0.469 | 0.202 / 0.216 | 1.05× | 0.99× |
| `alu1_198` | 0.046 / 0.0536 | 0.039 / 0.0495 | 0.195 / 0.127 | 0.048 / 0.0629 | 0.96× | 0.85× |
| `dk27_225` | 0.066 / 0.0688 | 0.063 / 0.0729 | 0.185 / 0.0995 | 0.073 / 0.0787 | 0.90× | 0.87× |
| `cm150a_210` | 0.198 / 0.195 | 0.117 / 0.143 | 0.605 / 0.554 | 0.134 / 0.158 | 1.48× | 1.24× |
| `pcler8_248` | 0.042 / 0.0465 | 0.036 / 0.0455 | 0.169 / 0.103 | 0.044 / 0.052 | 0.95× | 0.89× |
| `mlp4_245` | 0.434 / 0.399 | 0.302 / 0.325 | 1.51 / 0.94 | 0.342 / 0.372 | 1.27× | 1.07× |
