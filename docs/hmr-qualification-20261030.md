# Public HMR qualification protocol (2026-10-30)

Base: `main@332de59677bd5e21a125c5d6f6f5f43264b4b734`. This protocol qualifies
the existing installed experimental engines; it neither creates a new HMR
theorem nor promotes a stable API.

The public source is Qualtran GF2MulMBUC, revision
`638777fac4379bc62e2a1e4a52cf1a1753895d48`, Apache-2.0. The existing degree-one
and degree-two fixtures retain their original source/decomposition hashes,
normalization, license, bit conventions and explicit product preparation.
They were explored previously. This is **not an untouched holdout** and cannot
establish generality across compilers or large multipliers.

## Semantics before measurements

The manifest pins nine cases: prepared full-channel equality at m=1 and m=2;
missing feedback at both sizes; wrong event/parity/bit-order at m=2; and reduced
channel equality/missing feedback at m=2 with an explicit ordered retained-output
map. Every label is checked with a separate exact rational Kraus implementation
on all input matrix units (16 or 256 per case), including partial trace. Every
negative timing result is replayed with both the scalar API and the independent
Kraus oracle. A basis-value-only test must not certify a channel: missing
feedback preserves the diagonals but changes off-diagonal coherences.

The matrix separately records the restricted O1/O2 branch theorem and a derived
instrument control on raw normalized measurement events. The latter exposes
records that the upstream cleanup discards; it is not a claim that Qualtran
returns observed events. The sign/HMR factorized engines still forget events,
so their channel proof does not establish an arbitrary observed instrument.

Missing preparation produces an explicit coherent counterexample. A 65-wire
connected synthetic context embeds two unchanged public-derived m=1 gadgets;
the composition checker proves clean cut facts and every local coherence, while
dirty-ancilla and missing-feedback mutants are refused. This global context is
synthetic, not a larger compiler-generated Qualtran circuit.

Static boundary controls distinguish native 64 and 128 paired-variable limits
from the independent common-block theorem. They are diagnostic controls, not
scaling benchmarks or measured proofs at every declared width.

Three labeled synthetic counterexamples prevent theorem upgrades: an invert of
an observed event preserves the forgotten channel while changing the instrument;
permuting discarded outputs can preserve a reduced channel while changing the
full channel; and a nonunitary self-comparison proves a channel equality but
violates the O2 obligation for the strict branch/unitary theorem.

## Frozen, bounded cost experiment

Before measurement, commit the protocol, build ABI 5 from that exact source,
and record the loaded extension SHA-256, C/Python source hashes, toolchain and
environment. A worker rejects any package/extension from another checkout and
any changed source or binary. The protocol checks provenance before and after
each worker and the complete campaign. No code is changed during measurement.

Run serial fresh workers, randomized paired order, 15 repetitions per case and
backend (270 workers). Both `zdd` and `zdd-native` receive the same contracts and
limits: 60-second process wall/CPU ceilings, 2-GiB address-space cap; the public
verification cooperatively receives 50 seconds and two million nodes, with up
to five seconds for an additional replay. The parent retains the process limit.
Address-space limits are not RSS limits; whole-worker peak RSS is recorded.

Input fixture materialization, uninstrumented public-call wall/CPU, additional
independent replay, process wall, whole-worker CPU and RSS are separate fields.
Whole-worker CPU is measured from serial reaped-child usage deltas; the worker's
own CPU/RSS sample is explicitly taken before response encoding. The measured
RSS peak therefore does not promise to include the last encoding allocation.
The public call includes its own validation, normalization and counterexample
work. No unsupported decision is counted as a difference, and no missing timing
is treated as zero. Failures retain status, reason, exit code and denominator.

The two sizes belong to one family. Report each case and paired dispersion;
there is no cross-family confidence interval or population speedup claim.
Native superiority and stable promotion remain open even if these tiny cases
all succeed. The historical 210-worker synthetic campaign stays untouched.

Commands after the protocol commit is frozen:

```sh
PYTHONPATH=src python -m pytest -q tests/test_hmr_qualification.py
PYTHONPATH=src python benchmarks/hmr_qualification.py --build-native --out benchmarks/qualification/hmr-20261030/build.json
PYTHONPATH=src python benchmarks/hmr_qualification.py --build-receipt benchmarks/qualification/hmr-20261030/build.json --out benchmarks/qualification/hmr-20261030/results.json
```

Measured results and the promotion recommendation are appended only after an
actual completed campaign; this protocol contains no invented performance data.


## Recorded public qualification

The campaign ran on the public, source-frozen protocol commit
`b69babec7f0e6456f8358c48b6142788d29ef793`, tree
`d6c7bb6f2e302f8cf9f90dbdafb79b655a1b7a5d`, using a newly created standalone
venv and an ABI-5 extension built with `cc (Debian 14.2.0-19) 14.2.0`.
Native binary SHA-256: `2915552e4c316c592a7217f529289d370b71129a844d7b4b17ef7d6fd2103649`.
The loaded C and Python wrapper hashes match the source-pinned receipt. The
parent and every worker retained CPU affinity `[4]`, and the source/binary
snapshots remained identical before/after each worker and the complete campaign.

All **270 workers completed and qualified** in 46.104 seconds: **90 equivalent,
180 different**. There were **zero timeouts, OOMs, unsupported, inconclusive,
not-run or other failures** in these nine predeclared eligible cases. All 180
negative results were replayed by both the scalar API and the independently
implemented exact Kraus oracle. Preflight checked **1,824 input matrix units**
over the nine cases. Every negative case preserved all classical diagonals and
was distinguished by an off-diagonal coherence. The derived instrument and
composition controls are separate semantic checks, not extra comparative
performance samples.

| Case | Python verified | Native verified | Python public-call median, ms | Native public-call median, ms | Paired Python/native median [p10,p90] |
| --- | ---: | ---: | ---: | ---: | --- |
| m1-full-none | 15/15 | 15/15 | 8.397 | 8.590 | 0.978 [0.811, 1.091] |
| m1-full-missing_correction | 15/15 | 15/15 | 8.242 | 8.274 | 1.018 [0.905, 1.050] |
| m2-full-none | 15/15 | 15/15 | 8.668 | 8.362 | 1.061 [0.850, 1.190] |
| m2-full-missing_correction | 15/15 | 15/15 | 9.069 | 8.827 | 1.055 [0.887, 1.142] |
| m2-full-wrong_event | 15/15 | 15/15 | 9.420 | 8.979 | 1.040 [0.874, 1.168] |
| m2-full-wrong_parity | 15/15 | 15/15 | 9.081 | 8.893 | 1.027 [0.895, 1.094] |
| m2-full-wrong_bits | 15/15 | 15/15 | 9.283 | 9.561 | 0.944 [0.851, 1.030] |
| m2-reduced-none | 15/15 | 15/15 | 9.021 | 8.684 | 1.019 [0.924, 1.128] |
| m2-reduced-missing_correction | 15/15 | 15/15 | 9.062 | 8.902 | 1.020 [0.885, 1.177] |

Each row has 15 paired repetitions. Ratios greater than one favor native. Every
empirical p10–p90 interval straddles one. The positive median for m2 full-channel
equality and the negative median for the wrong-bit mutant are both retained;
this experiment supports **near parity on these tiny instances**, not a
family-independent speedup. The two sizes and their mutants are one dependent
family, so no cross-family bootstrap or confidence claim is made.

Median fresh-process wall time was 167.589 ms; median whole reaped-worker CPU was
166.745 ms. These include startup, imports, provenance checks, input construction,
additional independent replay, receipt processing and cleanup; they are not
measurements of the symbolic kernel. The public-call wall medians above and
per-row public-call CPU fields have their own boundary. Worker RSS samples
ranged from 25.469 to 27.219 MiB before final response encoding. The 2-GiB
limit is an address-space ceiling, not an observed RSS requirement. Resource
explosion frontiers are unknown from these tiny successful cases.

## Demonstrated capability and remaining gates

| Contract/control | Demonstrated evidence | Limit |
| --- | --- | --- |
| Prepared full sign/HMR channel | Authenticated m=1/m=2, all 16/256 coherent matrix units; 15 pairs per engine/case | Largest real fixture has four independent data wires and six physical wires |
| Reduced channel | Explicit retained-data maps and the same exhaustive oracle; separate workspace-permutation control distinguishes reduced from full equality | Discarded classical outcomes remain forgotten |
| Restricted O1/O2 branch theorem | Correct prepared fixtures satisfy clean/outcome-independent obligations | Self-equal dephasing example violates O2; a general channel is not an induced unitary |
| Observed instrument | Exact m=1/m=2 derived raw-event controls; event-inversion counterexample has coherent witness `(0,1)` | Dense oracle only, width six/eight events; upstream Qualtran discards these records |
| Preparation | Unprepared cleanup fails with explicit coherent counterexamples | A dependent product register cannot be declared a free input |
| Local composition | Two unaltered public-derived m=1 gadgets in a connected 65-wire synthetic context, one reused lemma, 16 local coherences | Global context is not itself authentic compiler output; clean-cut facts remain required |
| Native width eligibility | Ordinary/wide/common-block controls at 32/33/36/64/65 coherent data variables | Static diagnostics do not establish completion or beneficial runtime at those widths |

**Recommendation: keep these capabilities experimental.** The new evidence
shows a useful, exact coherent qualification path for one licensed real family,
including preparation and local composition. It does not establish broad
compiler coverage, large-multiplier scaling, an advantage over external HMR
verifiers, a useful need for 256 variables, or a stable production API contract.
Issues #19 and #100 therefore retain substantive qualification gates. No SAT
HMR pilot was relaunched, no stable default changed, and no private repository
was used.

Raw data and reproducibility: [results](../benchmarks/qualification/hmr-20261030/results.json),
[build receipt](../benchmarks/qualification/hmr-20261030/build.json),
[completion receipt](../benchmarks/qualification/hmr-20261030/receipt.json) and
[checksums/commands](../benchmarks/qualification/hmr-20261030/README.md).
The results JSON SHA-256 is `0f689a9ff33232ef329810fec48cebea95380a6c0d7dcb9a266c17091277ddaa`.
These measurements belong to the protocol commit above, not to a later commit
that only appends their report or data.
