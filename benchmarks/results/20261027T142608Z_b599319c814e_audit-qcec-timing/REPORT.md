# Benchmark report

- symq commit `b599319c814e371792f70c443861d67ed79696e2` (dirty: False), started 2026-10-27T14:26:08Z
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
| `c2_181` | dev | 35 | 116 | 161 | 161 | 2.73 | 0.245 | 4.35 | 0.329 | 4.72 | 12.5 | not_applicable |
| `mod5adder_306` | dev | 32 | 110 | 0.24 | 0.202 | 0.726 | 0.0582 | 0.239 | 0.286 | 5.53 | 7.69 | not_applicable |
| `rd73_312` | dev | 25 | 76 | 0.235 | 0.181 | 0.522 | 0.0436 | 0.208 | 0.254 | 3.11 | 4.38 | not_applicable |
| `rd84_313` | dev | 34 | 113 | 0.486 | 0.374 | 0.897 | 0.0701 | 0.415 | 0.503 | 3.86 | 23.6 | not_applicable |
| `sym9_317` | dev | 27 | 64 | 0.528 | 0.409 | 0.844 | 0.0635 | 0.437 | 0.555 | 3.25 | 16.4 | not_applicable |
| `5xp1_194` | holdout | 17 | 85 | 0.214 | 0.184 | 0.471 | 0.0488 | 0.23 | 0.2 | 2.34 | 6.34 | not_applicable |
| `alu1_198` | holdout | 20 | 32 | 0.0547 | 0.051 | 0.125 | 0.0203 | 0.0664 | 0.0632 | 2.3 | 5.39 | not_applicable |
| `cm150a_210` | holdout | 22 | 53 | 0.195 | 0.138 | 0.572 | 0.0396 | 0.167 | 0.162 | 2.06 | 2.18 | not_applicable |
| `dk27_225` | holdout | 18 | 24 | 0.0704 | 0.0725 | 0.103 | 0.0224 | 0.0857 | 0.0692 | 2.41 | 6.31 | not_applicable |
| `mlp4_245` | holdout | 16 | 131 | 0.418 | 0.345 | 0.998 | 0.0909 | 0.395 | 0.429 | 3.35 | 8.28 | not_applicable |
| `pcler8_248` | holdout | 21 | 22 | 0.0477 | 0.046 | 0.118 | 0.0198 | 0.0579 | 0.0586 | 2.35 | 2.11 | not_applicable |
| `C7552_205` | extension | 21 | 80 | 0.222 | 0.205 | 0.34 | 0.036 | 0.232 | 0.174 | 2.52 | 4.07 | not_applicable |
| `add6_196` | extension | 19 | 229 | 1.25 | 0.907 | 2.63 | 0.289 | 1 | 1.78 | 9.77 | 15.2 | not_applicable |
| `apla_203` | extension | 22 | 80 | 1.54 | 1.28 | 0.8 | 0.0642 | 1.38 | 0.294 | 2.86 | 4.21 | not_applicable |
| `cm151a_211` | extension | 28 | 33 | 0.129 | 0.128 | 0.251 | 0.0305 | 0.153 | 0.119 | 2.31 | 2.95 | not_applicable |
| `cm163a_213` | extension | 29 | 39 | 0.0871 | 0.0797 | 0.207 | 0.0278 | 0.116 | 0.0925 | 2.08 | 2.94 | not_applicable |
| `cu_219` | extension | 25 | 40 | 0.231 | 0.209 | 0.344 | 0.0308 | 0.239 | 0.109 | 2.33 | 3.21 | not_applicable |
| `dk17_224` | extension | 21 | 49 | 0.623 | 0.61 | 0.417 | 0.0346 | 0.647 | 0.168 | 2.31 | 7.5 | not_applicable |
| `example2_231` | extension | 16 | 157 | 0.92 | 0.525 | 2.08 | 0.218 | 0.596 | 0.943 | 4.11 | 9.09 | not_applicable |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.29×, geomean 1.27×, range 1.19–1.30× | 1.0× |
| `sparse` | holdout | n=6, median 1.12×, geomean 1.14×, range 0.97–1.41× | — |
| `sparse` | extension | n=8, median 1.10×, geomean 1.19×, range 1.00–1.75× | — |
| `zdd` | dev | n=4, median 0.50×, geomean 0.47×, range 0.33–0.63× | 58.9× |
| `zdd` | holdout | n=6, median 0.43×, geomean 0.45×, range 0.34–0.68× | — |
| `zdd` | extension | n=8, median 0.58×, geomean 0.70×, range 0.42–1.92× | — |
| `zdd-native` | dev | n=4, median 6.17×, geomean 5.99×, range 4.13–8.31× | 655.5× |
| `zdd-native` | holdout | n=6, median 3.76×, geomean 3.56×, range 2.41–4.93× | — |
| `zdd-native` | extension | n=8, median 5.25×, geomean 6.84×, range 3.13–23.94× | — |
| `auto-zdd` | dev | n=4, median 1.15×, geomean 1.13×, range 1.00–1.21× | 37.0× |
| `auto-zdd` | holdout | n=6, median 0.88×, geomean 0.93×, range 0.82–1.17× | — |
| `auto-zdd` | extension | n=8, median 0.97×, geomean 1.02×, range 0.75–1.54× | — |
| `polybori` | dev | n=4, median 0.94×, geomean 0.92×, range 0.84–0.97× | 488.9× |
| `polybori` | holdout | n=6, median 1.00×, geomean 0.98×, range 0.81–1.21× | — |
| `polybori` | extension | n=8, median 1.18×, geomean 1.57×, range 0.71–5.24× | — |
| `cudd-bdd` | dev | n=4, median 0.10×, geomean 0.09×, range 0.04–0.16× | 34.1× |
| `cudd-bdd` | holdout | n=6, median 0.06×, geomean 0.05×, range 0.02–0.12× | — |
| `cudd-bdd` | extension | n=8, median 0.11×, geomean 0.13×, range 0.04–0.54× | — |
| `cudd-zdd` | dev | n=4, median 0.03×, geomean 0.03×, range 0.02–0.05× | 12.8× |
| `cudd-zdd` | holdout | n=6, median 0.03×, geomean 0.03×, range 0.01–0.09× | — |
| `cudd-zdd` | extension | n=8, median 0.08×, geomean 0.08×, range 0.03–0.37× | — |

## Workload `equiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `zdd-native` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 4793 | 4831 | 5.5 | 0.541 | 8.84 | 0.95 | 13.9 | 28 | 6.71 |
| `mod5adder_306` | dev | 32 | 110 | 2.98 | 2.79 | 6.9 | 0.846 | 2.83 | 1.12 | 9.98 | 23.3 | 12.3 |
| `rd73_312` | dev | 25 | 76 | 0.576 | 0.456 | 0.88 | 0.0999 | 0.538 | 0.62 | 7.31 | 12.8 | 41.1 |
| `rd84_313` | dev | 34 | 113 | 1.75 | 1.49 | 2.92 | 0.331 | 1.58 | 1.41 | 11.8 | 37.3 | 34.8 |
| `sym9_317` | dev | 27 | 64 | 2.92 | 2.62 | 4.65 | 0.48 | 2.67 | 1.28 | 8.56 | 24.8 | 5.12 |
| `5xp1_194` | holdout | 17 | 85 | 0.9 | 0.851 | 1.19 | 0.142 | 0.906 | 0.557 | 6.82 | 10.3 | 4.51 |
| `alu1_198` | holdout | 20 | 32 | 0.157 | 0.151 | 0.255 | 0.0409 | 0.18 | 0.159 | 6.08 | 6.82 | 3.33 |
| `cm150a_210` | holdout | 22 | 53 | 0.576 | 0.456 | 0.809 | 0.0784 | 0.483 | 0.353 | 5.87 | 6.99 | 2.81 |
| `dk27_225` | holdout | 18 | 24 | 0.207 | 0.208 | 0.211 | 0.0304 | 0.196 | 0.117 | 5.69 | 5.97 | 2.7 |
| `mlp4_245` | holdout | 16 | 131 | 1.53 | 1.39 | 3.38 | 0.379 | 1.5 | 1.24 | 9.33 | 17.4 | 3.46 |
| `pcler8_248` | holdout | 21 | 22 | 0.104 | 0.0989 | 0.163 | 0.0307 | 0.12 | 0.123 | 5.33 | 5.86 | 3.06 |
| `C7552_205` | extension | 21 | 80 | 0.572 | 0.535 | 0.647 | 0.0773 | 0.84 | 0.551 | 8.67 | 13 | 3.59 |
| `add6_196` | extension | 19 | 229 | 5.15 | 4.81 | 12.1 | 1.11 | 4.36 | 4.22 | 42.5 | 45.1 | 11.8 |
| `apla_203` | extension | 22 | 80 | 36.5 | 35.9 | 1.48 | 0.156 | 5.53 | 0.724 | 7.32 | 13 | 4.31 |
| `cm151a_211` | extension | 28 | 33 | 0.219 | 0.212 | 0.274 | 0.0455 | 0.244 | 0.191 | 5.9 | 8.13 | 3.42 |
| `cm163a_213` | extension | 29 | 39 | 0.223 | 0.205 | 0.331 | 0.052 | 0.25 | 0.214 | 6.25 | 9.09 | 2.97 |
| `cu_219` | extension | 25 | 40 | 0.609 | 0.562 | 0.481 | 0.059 | 0.616 | 0.238 | 6.03 | 8.33 | 3.07 |
| `dk17_224` | extension | 21 | 49 | 2.75 | 2.79 | 0.573 | 0.0667 | 2.86 | 0.323 | 5.92 | 9.05 | 3.15 |
| `example2_231` | extension | 16 | 157 | 3.51 | 2.79 | 4.2 | 0.433 | 2.43 | 1.86 | 10.2 | 19.5 | 6.66 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.15×, geomean 1.15×, range 1.07–1.26× | 1.0× |
| `sparse` | holdout | n=6, median 1.05×, geomean 1.08×, range 0.99–1.26× | — |
| `sparse` | extension | n=8, median 1.07×, geomean 1.07×, range 0.99–1.26× | — |
| `zdd` | dev | n=4, median 0.61×, geomean 0.57×, range 0.43–0.65× | 870.9× |
| `zdd` | holdout | n=6, median 0.67×, geomean 0.67×, range 0.45–0.98× | — |
| `zdd` | extension | n=8, median 0.86×, geomean 1.50×, range 0.43–24.64× | — |
| `zdd-native` | dev | n=4, median 5.53×, geomean 5.06×, range 3.52–6.10× | 8856.7× |
| `zdd-native` | holdout | n=6, median 5.18×, geomean 5.05×, range 3.39–7.34× | — |
| `zdd-native` | extension | n=8, median 7.75×, geomean 12.44×, range 4.29–233.97× | — |
| `auto-zdd` | dev | n=4, median 1.08×, geomean 1.08×, range 1.05–1.11× | 542.4× |
| `auto-zdd` | holdout | n=6, median 1.01×, geomean 0.99×, range 0.86–1.19× | — |
| `auto-zdd` | extension | n=8, median 0.98×, geomean 1.25×, range 0.68–6.59× | — |
| `polybori` | dev | n=4, median 1.77×, geomean 1.63×, range 0.93–2.67× | 5043.5× |
| `polybori` | holdout | n=6, median 1.42×, geomean 1.30×, range 0.85–1.76× | — |
| `polybori` | extension | n=8, median 1.55×, geomean 2.73×, range 1.04–50.32× | — |
| `cudd-bdd` | dev | n=4, median 0.22×, geomean 0.19×, range 0.08–0.34× | 343.9× |
| `cudd-bdd` | holdout | n=6, median 0.07×, geomean 0.06×, range 0.02–0.16× | — |
| `cudd-bdd` | extension | n=8, median 0.11×, geomean 0.17×, range 0.04–4.98× | — |
| `cudd-zdd` | dev | n=4, median 0.08×, geomean 0.08×, range 0.05–0.13× | 171.3× |
| `cudd-zdd` | holdout | n=6, median 0.06×, geomean 0.05×, range 0.02–0.09× | — |
| `cudd-zdd` | extension | n=8, median 0.09×, geomean 0.12×, range 0.02–2.80× | — |
| `qcec` | dev | n=4, median 0.15×, geomean 0.10×, range 0.01–0.57× | 714.6× |
| `qcec` | holdout | n=6, median 0.14×, geomean 0.11×, range 0.03–0.44× | — |
| `qcec` | extension | n=8, median 0.32×, geomean 0.36×, range 0.06–8.46× | — |

## Workload `nonequiv` — median ms

| circuit | split | width | gates | `sparse-copy` | `sparse` | `zdd` | `zdd-native` | `auto-zdd` | `polybori` | `cudd-bdd` | `cudd-zdd` | `qcec` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | dev | 35 | 116 | 316 | 324 | 2.9 | 0.345 | 6.29 | 0.699 | 20.5 | 32.8 | 2.8 |
| `mod5adder_306` | dev | 32 | 110 | 0.549 | 0.501 | 1.14 | 0.166 | 0.552 | 0.631 | 10.2 | 21 | 3.85 |
| `rd73_312` | dev | 25 | 76 | 0.502 | 0.42 | 0.747 | 0.122 | 0.463 | 0.546 | 8.45 | 15.1 | 7.55 |
| `rd84_313` | dev | 34 | 113 | 1.26 | 0.85 | 1.28 | 0.194 | 0.927 | 1.11 | 11.3 | 41.3 | 5.59 |
| `sym9_317` | dev | 27 | 64 | 1.08 | 0.866 | 1.11 | 0.138 | 0.905 | 1.14 | 8.54 | 25.8 | 2.96 |
| `5xp1_194` | holdout | 17 | 85 | 0.492 | 0.438 | 0.725 | 0.127 | 0.517 | 0.437 | 7.15 | 10.1 | 3.3 |
| `alu1_198` | holdout | 20 | 32 | 0.141 | 0.131 | 0.227 | 0.0573 | 0.153 | 0.145 | 7 | 8.09 | 1.71 |
| `cm150a_210` | holdout | 22 | 53 | 0.44 | 0.307 | 0.735 | 0.0957 | 0.361 | 0.352 | 8.78 | 18.4 | 3.03 |
| `dk27_225` | holdout | 18 | 24 | 0.158 | 0.171 | 0.17 | 0.0466 | 0.195 | 0.126 | 9.03 | 17.7 | 2.6 |
| `mlp4_245` | holdout | 16 | 131 | 1.07 | 0.899 | 1.79 | 0.278 | 1.02 | 1.06 | 8.9 | 18.5 | 2.12 |
| `pcler8_248` | holdout | 21 | 22 | 0.122 | 0.116 | 0.245 | 0.0479 | 0.139 | 0.144 | 9.33 | 8.21 | 1.29 |
| `C7552_205` | extension | 21 | 80 | 0.51 | 0.444 | 0.546 | 0.11 | 0.525 | 0.396 | 8.77 | 12.7 | 1.97 |
| `add6_196` | extension | 19 | 229 | 2.72 | 1.6 | 3.17 | 0.484 | 1.79 | 3.36 | 20.9 | 42.5 | 3.76 |
| `apla_203` | extension | 22 | 80 | 4.81 | 4.22 | 1.28 | 0.184 | 4.33 | 1.35 | 9.21 | 14.4 | 3.09 |
| `cm151a_211` | extension | 28 | 33 | 0.234 | 0.225 | 0.315 | 0.0646 | 0.299 | 0.201 | 6.99 | 10 | 2.75 |
| `cm163a_213` | extension | 29 | 39 | 0.209 | 0.189 | 0.342 | 0.0727 | 0.236 | 0.205 | 11.2 | 10.1 | 2.77 |
| `cu_219` | extension | 25 | 40 | 0.484 | 0.448 | 0.484 | 0.0772 | 0.493 | 0.241 | 8.19 | 12.4 | 2.96 |
| `dk17_224` | extension | 21 | 49 | 1.32 | 1.28 | 0.568 | 0.0908 | 1.34 | 0.298 | 9.68 | 10.4 | 3.53 |
| `example2_231` | extension | 16 | 157 | 2.14 | 1.33 | 3.91 | 0.517 | 1.52 | 2.08 | 10.6 | 15.9 | 3.25 |

Paired speedup of each backend over `sparse-copy` (per-circuit ratio of medians, >1 is faster), `c2_181` reported separately:

| backend | split | without c2_181 | c2_181 |
|---|---|---|---:|
| `sparse` | dev | n=4, median 1.22×, geomean 1.25×, range 1.10–1.49× | 1.0× |
| `sparse` | holdout | n=6, median 1.10×, geomean 1.12×, range 0.92–1.43× | — |
| `sparse` | extension | n=8, median 1.12×, geomean 1.21×, range 1.03–1.70× | — |
| `zdd` | dev | n=4, median 0.83×, geomean 0.75×, range 0.48–0.99× | 108.8× |
| `zdd` | holdout | n=6, median 0.61×, geomean 0.64×, range 0.50–0.93× | — |
| `zdd` | extension | n=8, median 0.90×, geomean 1.07×, range 0.55–3.75× | — |
| `zdd-native` | dev | n=4, median 5.30×, geomean 5.14×, range 3.31–7.87× | 916.1× |
| `zdd-native` | holdout | n=6, median 3.61×, geomean 3.36×, range 2.45–4.59× | — |
| `zdd-native` | extension | n=8, median 5.13×, geomean 6.36×, range 2.87–26.08× | — |
| `auto-zdd` | dev | n=4, median 1.14×, geomean 1.15×, range 0.99–1.36× | 50.2× |
| `auto-zdd` | holdout | n=6, median 0.94×, geomean 0.96×, range 0.81–1.22× | — |
| `auto-zdd` | extension | n=8, median 0.98×, geomean 1.06×, range 0.78–1.52× | — |
| `polybori` | dev | n=4, median 0.93×, geomean 0.96×, range 0.87–1.14× | 451.5× |
| `polybori` | holdout | n=6, median 1.07×, geomean 1.07×, range 0.85–1.26× | — |
| `polybori` | extension | n=8, median 1.23×, geomean 1.59×, range 0.81–4.43× | — |
| `cudd-bdd` | dev | n=4, median 0.09×, geomean 0.08×, range 0.05–0.13× | 15.4× |
| `cudd-bdd` | holdout | n=6, median 0.04×, geomean 0.04×, range 0.01–0.12× | — |
| `cudd-bdd` | extension | n=8, median 0.09×, geomean 0.09×, range 0.02–0.52× | — |
| `cudd-zdd` | dev | n=4, median 0.03×, geomean 0.03×, range 0.03–0.04× | 9.6× |
| `cudd-zdd` | holdout | n=6, median 0.02×, geomean 0.02×, range 0.01–0.06× | — |
| `cudd-zdd` | extension | n=8, median 0.05×, geomean 0.06×, range 0.02–0.33× | — |
| `qcec` | dev | n=4, median 0.18×, geomean 0.17×, range 0.07–0.37× | 112.8× |
| `qcec` | holdout | n=6, median 0.12×, geomean 0.13×, range 0.06–0.50× | — |
| `qcec` | extension | n=8, median 0.32×, geomean 0.31×, range 0.08–1.55× | — |

## Memory and representation changes (`simulate`)

tracemalloc peak in KiB (separate untimed run); worker peak RSS in MiB, which includes the interpreter.

| circuit | `sparse-copy` KiB | `sparse` KiB | `zdd` KiB | `zdd-native` KiB | `auto-zdd` KiB | `polybori` KiB | `cudd-bdd` KiB | `cudd-zdd` KiB | `qcec` KiB | max RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `c2_181` | 4910 | 5060 | 400 | 6 | 392 | 6 | 11 | 11 | — | 139 |
| `mod5adder_306` | 52 | 58 | 130 | 6 | 59 | 6 | 10 | 11 | — | 147 |
| `rd73_312` | 55 | 50 | 82 | 4 | 51 | 5 | 9 | 10 | — | 139 |
| `rd84_313` | 122 | 96 | 172 | 6 | 97 | 6 | 11 | 11 | — | 139 |
| `sym9_317` | 179 | 154 | 177 | 4 | 155 | 5 | 10 | 10 | — | 139 |
| `5xp1_194` | 18 | 19 | 62 | 5 | 19 | 4 | 6 | 6 | — | 139 |
| `alu1_198` | 12 | 11 | 19 | 3 | 13 | 4 | 8 | 8 | — | 139 |
| `cm150a_210` | 41 | 24 | 88 | 4 | 25 | 5 | 9 | 9 | — | 139 |
| `dk27_225` | 24 | 21 | 15 | 2 | 22 | 4 | 6 | 6 | — | 139 |
| `mlp4_245` | 22 | 20 | 130 | 10 | 21 | 4 | 5 | 6 | — | 139 |
| `pcler8_248` | 10 | 10 | 15 | 3 | 10 | 5 | 8 | 8 | — | 139 |
| `C7552_205` | 18 | 18 | 41 | 6 | 19 | 5 | 8 | 8 | — | 139 |
| `add6_196` | 37 | 28 | 404 | 17 | 29 | 4 | 8 | 8 | — | 140 |
| `apla_203` | 325 | 274 | 131 | 8 | 275 | 5 | 9 | 9 | — | 139 |
| `cm151a_211` | 17 | 16 | 31 | 4 | 18 | 5 | 10 | 10 | — | 139 |
| `cm163a_213` | 14 | 14 | 29 | 3 | 15 | 5 | 10 | 10 | — | 139 |
| `cu_219` | 52 | 40 | 39 | 4 | 41 | 5 | 10 | 10 | — | 139 |
| `dk17_224` | 174 | 163 | 64 | 4 | 164 | 5 | 8 | 8 | — | 139 |
| `example2_231` | 56 | 38 | 298 | 11 | 39 | 4 | 5 | 6 | — | 147 |

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
| `c2_181` | 289 | 12.9 | 479 | 17.1 | 1649 | 16.2 |
| `mod5adder_306` | 544 | 0.767 | 511 | 5.12 | 3518 | 10.6 |
| `rd73_312` | 462 | 0.634 | 629 | 6.21 | 2354 | 7.27 |
| `rd84_313` | 904 | 1.39 | 1406 | 14.5 | 3393 | 12.8 |
| `sym9_317` | 965 | 1.88 | 1464 | 15.8 | 2477 | 12.1 |
| `5xp1_194` | 132 | 0.249 | 121 | 1.04 | 499 | 2.2 |
| `alu1_198` | 58 | 0.156 | 85 | 0.676 | 666 | 2.67 |
| `cm150a_210` | 84 | 0.349 | 76 | 0.677 | 749 | 2.67 |
| `dk27_225` | 65 | 0.387 | 72 | 0.696 | 451 | 2.39 |
| `mlp4_245` | 200 | 0.332 | 243 | 3.01 | 751 | 3.07 |
| `pcler8_248` | 82 | 0.195 | 113 | 1.01 | 695 | 3.93 |
| `C7552_205` | 101 | 0.197 | 122 | 0.966 | 662 | 2.66 |
| `add6_196` | 271 | 0.401 | 446 | 5.66 | 1142 | 4.92 |
| `apla_203` | 311 | 2.27 | 234 | 5.52 | 942 | 6.94 |
| `cm151a_211` | 117 | 0.27 | 171 | 1.58 | 1173 | 3.98 |
| `cm163a_213` | 101 | 0.205 | 128 | 1.04 | 1192 | 3.89 |
| `cu_219` | 143 | 0.682 | 213 | 2.49 | 1067 | 4.73 |
| `dk17_224` | 200 | 2.6 | 176 | 3.47 | 744 | 6.33 |
| `example2_231` | 220 | 0.61 | 223 | 3.34 | 669 | 3.32 |

`qcec` configuration: `{"run_alternating_checker": true, "run_simulation_checker": false, "run_zx_checker": false, "run_construction_checker": false, "parallel": false}`. Three separate medians (ms): `conversion` builds the two `QuantumComputation` objects, `native` calls `qcec.verify` on those pre-built objects (so no conversion is timed), and `end to end` is the public helper that converts on each call. `check` and `preprocessing` are QCEC's own reported times.

| circuit | workload | verdict | conversion | native | end to end | check | preprocessing |
|---|---|---:|---:|---:|---:|---:|
| `c2_181` | equiv | equivalent | 0.197 | 6.71 | 5.45 | 5.25 | 0.682 |
| `c2_181` | nonequiv | not_equivalent | 0.134 | 2.8 | 2.9 | 1.56 | 0.588 |
| `mod5adder_306` | equiv | equivalent | 0.168 | 12.3 | 10.5 | 10.7 | 0.684 |
| `mod5adder_306` | nonequiv | not_equivalent | 0.119 | 3.85 | 4 | 2.53 | 0.631 |
| `rd73_312` | equiv | equivalent | 0.116 | 41.1 | 40.9 | 39.2 | 0.569 |
| `rd73_312` | nonequiv | not_equivalent | 0.0894 | 7.55 | 8.05 | 6.35 | 0.531 |
| `rd84_313` | equiv | equivalent | 0.187 | 34.8 | 34.6 | 32.8 | 0.702 |
| `rd84_313` | nonequiv | not_equivalent | 0.121 | 5.59 | 5.8 | 4.25 | 0.626 |
| `sym9_317` | equiv | equivalent | 0.109 | 5.12 | 5.27 | 3.89 | 0.547 |
| `sym9_317` | nonequiv | not_equivalent | 0.0765 | 2.96 | 3.2 | 1.8 | 0.507 |
| `5xp1_194` | equiv | equivalent | 0.191 | 4.51 | 2.93 | 3.25 | 0.592 |
| `5xp1_194` | nonequiv | not_equivalent | 0.14 | 3.3 | 3.42 | 2.09 | 0.688 |
| `alu1_198` | equiv | equivalent | 0.0622 | 3.33 | 1.57 | 2.2 | 0.64 |
| `alu1_198` | nonequiv | not_equivalent | 0.0445 | 1.71 | 1.75 | 0.807 | 0.442 |
| `cm150a_210` | equiv | equivalent | 0.0994 | 2.81 | 2.94 | 1.65 | 0.517 |
| `cm150a_210` | nonequiv | not_equivalent | 0.109 | 3.03 | 3.4 | 1.77 | 0.511 |
| `dk27_225` | equiv | equivalent | 0.0396 | 2.7 | 3.05 | 1.63 | 0.434 |
| `dk27_225` | nonequiv | not_equivalent | 0.034 | 2.6 | 3.09 | 1.57 | 0.426 |
| `mlp4_245` | equiv | equivalent | 0.347 | 3.46 | 3.66 | 2 | 0.733 |
| `mlp4_245` | nonequiv | not_equivalent | 0.283 | 2.12 | 2.2 | 0.66 | 0.672 |
| `pcler8_248` | equiv | equivalent | 0.042 | 3.06 | 3.19 | 1.94 | 0.44 |
| `pcler8_248` | nonequiv | not_equivalent | 0.0375 | 1.29 | 1.34 | 0.405 | 0.43 |
| `C7552_205` | equiv | equivalent | 0.182 | 3.59 | 3.77 | 2.37 | 0.58 |
| `C7552_205` | nonequiv | not_equivalent | 0.215 | 1.97 | 2.13 | 0.839 | 0.565 |
| `add6_196` | equiv | equivalent | 0.683 | 11.8 | 12.3 | 9.53 | 1.06 |
| `add6_196` | nonequiv | not_equivalent | 0.546 | 3.76 | 4.26 | 2.1 | 1.06 |
| `apla_203` | equiv | equivalent | 0.233 | 4.31 | 2.95 | 2.89 | 0.688 |
| `apla_203` | nonequiv | not_equivalent | 0.204 | 3.09 | 3.34 | 1.79 | 0.622 |
| `cm151a_211` | equiv | equivalent | 0.0749 | 3.42 | 3.55 | 2.13 | 0.543 |
| `cm151a_211` | nonequiv | not_equivalent | 0.0693 | 2.75 | 2.84 | 1.61 | 0.491 |
| `cm163a_213` | equiv | equivalent | 0.0879 | 2.97 | 3.17 | 1.8 | 0.516 |
| `cm163a_213` | nonequiv | not_equivalent | 0.0684 | 2.77 | 2.81 | 1.61 | 0.49 |
| `cu_219` | equiv | equivalent | 0.105 | 3.07 | 3.07 | 1.88 | 0.517 |
| `cu_219` | nonequiv | not_equivalent | 0.1 | 2.96 | 3.06 | 1.78 | 0.506 |
| `dk17_224` | equiv | equivalent | 0.122 | 3.15 | 2.11 | 2.06 | 0.559 |
| `dk17_224` | nonequiv | not_equivalent | 0.1 | 3.53 | 1.77 | 2.28 | 0.708 |
| `example2_231` | equiv | equivalent | 0.397 | 6.66 | 5.42 | 5.02 | 0.843 |
| `example2_231` | nonequiv | not_equivalent | 0.316 | 3.25 | 3.66 | 1.94 | 0.762 |

## Comparison with the historical handoff (`simulate`)

Source: COMPARAISON_EXISTANT.md, frozen comparison of 27 Oct 2026 (user-supplied handoff), table 'Résultat principal sur les circuits COMPLETS'. historical, externally produced; not reproduced by these files. Different machine and different (reconstructed) code: compare speedup ratios, not absolute times.

| circuit | copy_set hist / `sparse-copy` here (ms) | fast_set hist / `sparse` here (ms) | zdd hist / `zdd` here (ms) | auto_zdd hist / `auto-zdd` here (ms) | auto_zdd speedup hist | here |
|---|---|---|---|---|---|---|
| `c2_181` | 226 / 161 | 209 / 161 | 0.835 / 2.73 | 2.28 / 4.35 | 99.31× | 36.95× |
| `mod5adder_306` | 0.173 / 0.24 | 0.146 / 0.202 | 1.12 / 0.726 | 0.179 / 0.239 | 0.97× | 1.00× |
| `rd73_312` | 0.205 / 0.235 | 0.137 / 0.181 | 1.3 / 0.522 | 0.15 / 0.208 | 1.37× | 1.13× |
| `rd84_313` | 0.382 / 0.486 | 0.299 / 0.374 | 2.32 / 0.897 | 0.321 / 0.415 | 1.19× | 1.17× |
| `sym9_317` | 0.532 / 0.528 | 0.309 / 0.409 | 2.39 / 0.844 | 0.31 / 0.437 | 1.72× | 1.21× |
| `5xp1_194` | 0.212 / 0.214 | 0.173 / 0.184 | 0.764 / 0.471 | 0.202 / 0.23 | 1.05× | 0.93× |
| `alu1_198` | 0.046 / 0.0547 | 0.039 / 0.051 | 0.195 / 0.125 | 0.048 / 0.0664 | 0.96× | 0.82× |
| `dk27_225` | 0.066 / 0.0704 | 0.063 / 0.0725 | 0.185 / 0.103 | 0.073 / 0.0857 | 0.90× | 0.82× |
| `cm150a_210` | 0.198 / 0.195 | 0.117 / 0.138 | 0.605 / 0.572 | 0.134 / 0.167 | 1.48× | 1.17× |
| `pcler8_248` | 0.042 / 0.0477 | 0.036 / 0.046 | 0.169 / 0.118 | 0.044 / 0.0579 | 0.95× | 0.82× |
| `mlp4_245` | 0.434 / 0.418 | 0.302 / 0.345 | 1.51 / 0.998 | 0.342 / 0.395 | 1.27× | 1.06× |
