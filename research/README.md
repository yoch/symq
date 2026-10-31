# Research modules awaiting graduation

These modules are not installed with `symq`. Each one is still exercised by tests under `tests/`
and is scheduled either to graduate into the package (with a written contract, differential
tests and mutants) or to be archived.

| Module | Content | Planned destination |
| --- | --- | --- |
| [`bitset_degree3/`](bitset_degree3/README.md) | degree-≤k integer-bitset ANF, finite outcome domains, GF(2) dual certificates | a bounded-degree backend and a finite-domain helper |
| [`hmr_feedback/`](hmr_feedback/README.md) | synthesis of late HMR phase repairs | the unified HMR checker |
| `xag-synthesis/` | exact bilinear decompositions of GF(2ⁿ) multiplication and an ANF proof harness | public arithmetic generators |
| `verification_api/` | contract grammar and corpus qualification prototypes | merged into the experimental contracts or the benchmark harness |

Prototypes, recorded measurements and audits removed on 31 October 2026 remain byte-identical in
the history of `main`; see the [archive index](../docs/archive-index.md).

A module graduates only by being ported into `src/symq/` with its accepted theorem documented and
its tests moved; nothing in `src/symq/` may import from this directory.
