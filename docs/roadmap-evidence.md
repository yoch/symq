# Experimental roadmap evidence

Publication CI exposed three portability issues that were corrected after the
measurements below: declared native width limits must survive an absent optional
extension; the campaign test must ship with its campaign module rather than in
an earlier stacked PR; and exclusive accounting must not be tested through a
host-dependent wall-time percentage. The raw measurements retain their original
source fingerprints. They are historical measurements of that exact content,
not a new performance claim about the subsequent CI hardening.

The installed experimental API and the stable verification facade have separate
contracts. An exact result records the requested theorem, input domain, retained
quantum outputs, classical observation, backend and source fingerprints. A
successful computation is not an independently checked UNSAT certificate.

## Profiling

`symq.experimental.profile` calls the same public `verify` implementation. There
is no separate profiled channel algorithm. Stage timers maintain a stack:
each parent subtracts its children's inclusive durations. Residual whole-call
time is assigned to orchestration, and the sum of exclusive stages reconciles
to the measured wall time. Nested stages and exceptional exits have deterministic
clock tests. Instrumented times include profiling overhead and are not used as
unbiased comparative benchmarks.

Symbolic output, kernel, reduction, phase, rename, witness and diagnostic stages
are recorded when reached. The fused native loop computes values and phase
coefficients together: its elapsed time is attributed to the symbolic pass;
there is no invented split between work performed inside one native call. A
missing stage means that stage was not measured separately. Conversion counters
come from the actual backend, and unavailable counters remain unavailable.

Profile reports export JSON and standalone HTML containing the exact result,
source and contract hashes, exclusive times, counters, environment and semantic
limits. The legacy research profile is a compatibility adapter to that public
implementation.

## Fixed synthetic qualification campaign

Run the complete campaign from the source checkout using an installed SymQ:

```sh
python benchmarks/roadmap_campaign.py --out benchmarks/results/roadmap-campaign.json
```

The version 1 manifest is frozen by its canonical SHA-256:
`9f4ee48a72ad334debd9168a9cd90670034c9c4c9282588a6aa24339ffe1bc72`.
Seven deterministic synthetic cases cover affine HMR repair, nonlinear repaired
data permutations, a dephasing-kernel mutant, an unsupported reset request,
different discarded-ancilla widths and output ordering, and a relative-phase
mutant. Development and holdout IDs, seeds and source fingerprints are disjoint.
The holdout cases are fixed before execution; this is a synthetic partition,
not an untouched external workload corpus.

The default campaign runs 15 paired repetitions of Python ZDD and native ZDD
per case. Pair order and backend order are deterministically randomized. Every
measurement gets a fresh spawned process, a 60-second wall deadline, a
60-second CPU limit and a 2-GiB address-space cap. Counterexamples are replayed
against concrete scalar semantics. Unsupported requests, timeouts, worker
failures and semantic mismatches remain in the raw records.

The output records the complete public-call wall time separately from worker
trial time and fresh-process wall time. Their difference includes interpreter
startup, imports outside the trial, IPC and cleanup; it is not a measurement of
pure interpreter startup. CPU and peak RSS describe the entire worker, including
imports and witness replay. Conversion counts, volumes and durations are taken
from backend statistics; null values do not mean zero cost.

The JSON contains all raw repetitions, paired ratio distributions, CPU/RSS,
limits, source hashes, native-extension hash, package versions and machine
characteristics. Source snapshots before and after the campaign must agree.
The standalone HTML links each summary to the embedded raw evidence. Pairwise
ratios exclude unsupported or failed computations, while those rows remain
visible in the qualification totals.

These small synthetic cases establish reproducibility and the recorded
semantic outcomes. They do not establish general native speedup, scaling on
large connected circuits, or comparative superiority on real workloads.

## Recorded execution

The final campaign ran at 2026-10-29T19:11:50.332856+00:00 in 30.808 seconds. All 210 fresh workers completed: 180 decisive outcomes matched their expected result, and 30 requests were rejected as expected. All 60 reported differences passed concrete witness replay. There were no unexpected failures or inconclusive results.

The source snapshots agree before and after the campaign and matched the working files and native binary when the reports were generated. The recorded code revision is `e232abcf875546b71e93546ba8bf9699952513e6`. The per-file hashes and native-extension hash identify the exact measured contents. The later evidence-only commit does not alter those measured source files.

Environment: Python 3.12.14, Linux-6.18.55-x86_64-with-glibc2.41, 5 logical CPUs. Whole-worker peak RSS ranged from 24.41 to 25.16 MiB. The median fresh-process elapsed time was 145.18 ms, including a median 135.64 ms of startup/import/IPC/cleanup overhead. Host contention was not controlled.

| Case | Python verify median, ms | Native verify median, ms | Paired Python/native median | Paired p10–p90 |
| --- | ---: | ---: | ---: | ---: |
| dev-affine-repair | 9.233 | 9.077 | 0.999 | 0.901–1.108 |
| dev-nonlinear-repair | 9.518 | 9.671 | 1.015 | 0.916–1.110 |
| dev-kernel-mutant | 8.491 | 8.917 | 0.986 | 0.833–1.168 |
| holdout-nonlinear-repair | 9.364 | 9.142 | 1.043 | 0.920–1.195 |
| holdout-reduced-discard | 8.855 | 9.040 | 0.989 | 0.854–1.095 |
| holdout-phase-mutant | 8.730 | 9.048 | 0.974 | 0.829–1.053 |

These distributions straddle a ratio of 1 on every decisive family. This campaign supports the recorded correctness and full-call cost measurements; it does not establish a general native performance advantage. It compares current Python ZDD with current native ZDD and cannot isolate the effect of a native optimization against its previous implementation.

All 180 accepted computations reported zero backend conversions. The benchmark does not infer this from missing counters: unsupported requests retain null conversion fields.

Artifacts:

- [Campaign JSON with raw repetitions and source hashes](../benchmarks/results/roadmap-campaign.json)
- [Standalone campaign HTML](../benchmarks/results/roadmap-campaign.html)
- [Public native profile JSON](../benchmarks/results/roadmap-profile.json)
- [Standalone public native profile HTML](../benchmarks/results/roadmap-profile.html)

The campaign JSON SHA-256 is `939fc71fb911ba1e586f0253fec3bf284322eebbc2d3078ed5b277e780b87218`. The profile is an additional instrumented call on `dev-nonlinear-repair`; it returned equivalent and reconciled its exclusive stage timings to 8.804 ms. Its environment records the same code revision, code-snapshot fingerprint and native-extension fingerprint. Its fused native symbolic pass and second-half rename are measured as their actual stages.
