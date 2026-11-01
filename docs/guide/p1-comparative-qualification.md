# P1 — Source-pinned, paired comparative qualification (development pilot)

**Status:** opt-in research, not a published superiority benchmark and not a
stable compiler API. The objective is to measure **coverage and failures**
on common contracts before comparing speed. This campaign deliberately
reuses previously admitted public corpora and work already present in
SymQ, rather than introducing a misleading new synthetic "real" benchmark.

## Two theorems; no invalid cross-family ranking

| Lane | Contract | Measured checker adapters | Explicit exclusions |
| --- | --- | --- | --- |
| Reversible arithmetic, dirty borrowed wires and compute/uncompute | Complete X/CX/CCX/MCX permutation on **all** input bits; phase-free full unitary follows | SymQ SAT, SymQ ZDD, MQT QCEC exact alternating checker | Restricted clean-cut SAT predicates are not claimed; PyZX has no qualified equivalent-theorem adapter |
| Measurement-assisted Qualtran cleanup | Prepared-zero ancillas, arbitrary coherent data, full output channel after discarding classical measurement record | SymQ exact ZDD channel backend, independently implemented exact `hybrid-exact` Kraus comparison | MQT QCEC's existing unitary adapter, PyZX and arbitrary observed instruments are **not applicable** |

MQT QCEC disables probabilistic simulation. A decisive
`equivalent_up_to_global_phase` result is semantically compatible with
**phase-free permutation matrices**; it does **not** justify running
QCEC on the dynamic/HMR lane.

The HMR oracle is Qualtran's actual public GF2Multiplication/GF2MulMBUC
decomposition imported into a declared prepared ancilla/channel frame,
not a measurement circuit projected to classical truth tables. Its
missing-correction mutant is an especially important negative control:
the classical diagonals may agree while **off-diagonal coherences differ**.
The independent Kraus oracle checks all 16 or 256 input matrix units
for the m=1/m=2 public cases.

## Source identities, partition and provenance

The immutable manifest is
[`benchmarks/p1_manifest.json`](../../benchmarks/p1_manifest.json),
with Git blob SHA-1
`fcf3161aa8bae5aa6f5000709fc2210bc1e884e6`;
the runner records its actual raw SHA-256, checked source-file hashes,
loaded SymQ source/backend binary identity, machine and tool versions.

- **James Barlow public Kaggle bilinear KMB dataset**, Apache-2.0
  *declared* in the original supplied archive. The existing byte-pinned
  loader authenticates gf16-07/gf64-03 and lowers their strict CX,
  SWAP and CCX operations into identical reversible permutations.
  GF16's 4096 complete states are independently checked; GF64 gets
  fixed basis/seeded probes and benefits from separate earlier
  exhaustive corpus qualification.
- **MQT QCEC**, MIT, upstream commit
  `98d6784176bfeb6ef923d4d0220e8d486dc1982f`, original
  public source `rd73_312` from the existing **dev** split. Its
  commuting variants and appended-X mutants are **synthetic
  derivatives**, not independently compiler-generated optimized pairs.
- **Qualtran**, Apache-2.0, commit
  `638777fac4379bc62e2a1e4a52cf1a1753895d48`.
  The pinned public m=1/m=2 cleanup instances, their missing-correction
  and wrong-parity controls, and normalized source checksums are
  supplied by the existing SymQ Qualtran fixture/qualification harness.
  They are already publicly explored, **not new blind holdout**.
- **Borrowed dirty wires and nonlinear compute/uncompute**:
  small, independently authored synthetic cases with full-input
  exhaustive oracle checks and missing-cleanup mutants.

The manifest admits **13 development cases** (3 original public KMB
derivatives, 2 QCEC source derivatives, 4 synthetic dirty/uncompute,
4 source-pinned Qualtran HMR). They produce **35 eligible
checker×case cells per repetition**: 27 full permutations
(9×3) and 8 coherent-channel cells (4×2). Ineligible theorem/engine
combinations are recorded as *not applicable*, **not as failures**.

The existing legacy QCEC `holdout` and `extension` splits are
**excluded entirely** from this pilot. QCEC's legacy holdout was
previously inspected in earlier project work; the new campaign
cannot relabel it as untouched. A future confirmatory holdout needs
fresh, source-cleared compiler output acquired and sealed **before**
any choice of parameters or backends.

## Reproduction and bounded workload

Install from the **exact P1 PR snapshot**, then:

```bash
python -m pip install -e ".[dev,external]"
python -m pytest -q tests/test_p1_comparative.py

# Full 13-case one-repetition coverage smoke — NOT a speed ranking.
python -m benchmarks.p1_comparative \
  --output /tmp/symq-p1-smoke.json --repetitions 1 --wall-seconds 12
python -m benchmarks.p1_report \
  --input /tmp/symq-p1-smoke.json --output /tmp/symq-p1-smoke.md

# Fixed small-cohort 15-paired-repetition qualification.
# Selected BEFORE results; development cases only.
python -m benchmarks.p1_comparative \
  --output /tmp/symq-p1-paired.json --repetitions 15 \
  --case kmb-gf16-original-vs-tower \
  --case borrowed-dirty-missing-uncompute \
  --case qualtran-m1-hmr-cleanup \
  --case qualtran-m1-hmr-missing-correction
python -m benchmarks.p1_report \
  --input /tmp/symq-p1-paired.json --output /tmp/symq-p1-paired.md
```

Each eligible trial uses a **fresh spawned hard-limited subprocess**.
The manifest fixes 12-second whole-worker wall and CPU limits,
1 GiB address-space limit and a 9-second inside decision limit;
a tighter `--wall-seconds` may be applied in CI. Case order and
backend order are randomized by a fixed seed. The report retains
both *whole-worker* wall/CPU/peak RSS (imports, materialization,
conversion, and checks) and *checker decision* wall/CPU separately.
No measurement of unexposed conversion stages is fabricated.

A success means the verdict matches the **independent preregistered
oracle**, and when a SymQ difference returns a witness it must be
replayed concretely. QCEC does not return its own witness through
this adapter; negative labels are prequalified by an independent
concrete oracle and QCEC's exact verdict is recorded separately.

Every case/engine/repetition row retains: exact source/candidate
SHA-256, original source/license and source type, gate/quantum domain,
execution status, exit code, error/timeout/unsupported reasons,
full time/CPU/peak RSS and verifier-specific details. Classification
is strict: `matched`, `incorrect_decision`, `invalid_witness`,
`unsupported`, `inconclusive`, `timeout`, `error`.
No skipped/unsupported cell becomes a proof of non-equivalence.
Intervals (median/p10/p90) and paired engine ratios include only
properly matched successful decisions; their denominator is reported.
The Markdown view refuses to label one smoke repetition as a
performance comparison.

## P1 scientific acceptance gates still open

This pilot is a **validity/coverage and measurement-infrastructure
milestone**, not a paper-ready result. Remaining work:
a fresh sealed holdout, independent optimized compiler output beyond
self-cancelling rewrites, enough paired families/repetitions to
establish robust CPU/memory distributions and test hypotheses,
and a **vetted PyZX comparison** on an actually common theorem.
For HMR, add genuine source-pinned correction-after-measurement
variants and report full instrument/observed outcome semantics
separately when claimed. Then perform cross-verifier validation of
the entire exact toolchain on fixed source hashes. The stable
public API/P2 must remain a separate review and adoption decision.

No new private Qant workload, false Kaggle score delta, general
quantum-equivalence, physical T-cost or default backend promotion
is claimed by this report.
