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
