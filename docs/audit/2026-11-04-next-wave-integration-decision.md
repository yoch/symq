# Integration decision — SymQ next-wave research (4 November 2026)

**Scope:** proposed integration of [#183](https://github.com/yoch/symq/pull/183) **including** the independent fix [#188](https://github.com/yoch/symq/pull/188), and [#184](https://github.com/yoch/symq/pull/184) **including** the independent fix [#190](https://github.com/yoch/symq/pull/190).
Independent review: [#191](https://github.com/yoch/symq/pull/191) (the source of the included audit report).
Base at assembly creation: `main@766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc`. Actual final assembly HEAD/tree and CI must be recorded **after** completion.

## Review verdict

- **Accept reset pilot as `symq.labs` research only.** Exact source snapshot,
  monomial reversible/diagonal prefix and explicitly caller-declared affine
  coherent support; every removed reset must have a fresh all-support zero
  polynomial proof. No automatic reachability contract, HMR or measurement
  theorem. Fix #188 closes unsafe acceptance of hostile `str` subclasses,
  unbounded-input preflight and inherited-budget handling.
- **Accept classical SAT-miter proof pilot as `symq.labs` research only**,
  with restricted `Contract`, normalized deterministic Tseitin CNF, fresh
  solver-free positive-hint RUP checking, and explicit source/contract
  fingerprint. Fix #190 prevents non-`str` labels and makes the contextual
  CCX negative test non-vacuous. The Python encoder, normalization loop and
  `lrat_rup` implementation are still trusted; neither a Lean-refined
  runtime nor a general contextual-cut/coherent-channel theorem is proven.
- **Do not integrate #185 / #189 yet.** The Qiskit test is valid and source
  licences are corrected in #189, but an optimizer at levels 1–2 already
  finds the same one-gate circuits. No independent held-out utility or
  meaningful comparative performance advantage is established. Preserve
  the research branch/CI results. Its provenance fix must be folded in
  before any redistribution or eventual merge.

## Accepted resource limitation and follow-up

Open resources issue [#193](https://github.com/yoch/symq/issues/193).
The `build_miter` encoder currently runs **before** variable/clause caps
are checked and polls the deadline only before and after encoding.
The independent auditor observed a 400,000-gate circuit with
`max_variables=10` and a `0.05 s` deadline consuming about **0.95 s
and 175 MB** before returning an inconclusive/refusal outcome.
This **is not a false positive**, but **is not a strict wall-time
or RSS bound**. The optional proof-logging Glucose worker also
has cooperative interrupt delays. Consequently:

- no untrusted-input-facing API, service, stable API, default backend,
  hard-timeout security guarantee or unrestricted workload claim;
- only research/`labs` usage on **trusted, bounded input** with explicit
  size/resource controls and awareness that the controls are cooperative;
- issue #193 must address in-encoding caps and hard isolation before any
  external-API promotion or untrusted remote input processing.

The reset pilot likewise does not impose an OS memory cap or guarantee
instant interruption of large in-progress snapshots.

## Qualification and inclusion provenance

| Included source | Exact reviewed head | Intended files |
| --- | --- | --- |
| #183 + #188 | `9c57ad4ca275521c4f1aa9f96568ccd9fa62dd56` | `src/symq/labs/reset_support.py`, `tests/test_reset_support.py`, `docs/evidence/2026-11-03-reset-affine-pilot.md`, defensive `src/symq/experimental/hybrid.py` |
| #184 + #190 | `f4e014af1bb438223136593ea8c7bd67a66038fd` | `miter_cnf.py`, `miter_proof_bundle.py`, their tests and two evidence pages |
| #191 | `261d3c93c73586131f711ab3e63d0dd5b3da2a74` | independent audit report only |

All three source trees were separately CI qualified on their respective
HEAD SHAs (review: #188 run 41728313311, #190 run 41728075155,
#191 run 41728404154). **None of those runs qualifies the combined tree**.
The final integration is built as a single clean commit from main using
the exact **Git blob SHAs** of the above source files, rather than merging
overlapping/superseded historical branches independently. The assembly
must have 14/14 general CI plus all applicable specialized jobs on its
actual head and require one final full diff review.

No unrelated #182 / #186 / #187 / #189 change, publication manuscript,
release, stable API or default engine change belongs in this integration.
Original Draft source branches stay available as review evidence.

## No automatic merge

This document does **not** authorize merging by itself. A final
maintainer-approved merge requires re-reading base and HEAD, actual
diff and checks, any blocking review threads, and verifying the
**published Git tree** against the tested assembly.
