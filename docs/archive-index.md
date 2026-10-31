# Research archive index

On 31 October 2026 the repository was reorganized so that `main` holds the maintained package,
its tests, the public corpora and the documentation. Prototypes, recorded measurements and dated
audit reports were removed from the tree. **Nothing was rewritten:** every removed file is
byte-identical in the history of `main` at commit
[`d18e0183`](https://github.com/yoch/symq/tree/d18e0183f8a3279e79757ffd75bd285da5323bb3), including
the sealed `MANIFEST.sha256` and `SHA256SUMS` files.

To work with the archived material:

```bash
git worktree add ../symq-archive d18e0183f8a3279e79757ffd75bd285da5323bb3
cd ../symq-archive
python research/verify_archive.py
```

A maintainer can name that commit with an annotated tag:

```bash
git tag -a archive/2026-10-31 d18e0183f8a3279e79757ffd75bd285da5323bb3 -m "Research and benchmark archive"
git push origin archive/2026-10-31
```

## What moved where

| Former location | Now |
| --- | --- |
| `research/archive/2026-10-27/` (sealed ANF/ZDD handoff) and `research/verify_archive.py` | archive commit only |
| `research/audit_crossrepo_20261029/`, `research/external_audit/`, the cross-repository audit tests and workflows | archive commit only; they tested code on other branches |
| `research/engineering/2026-10-28/` | Cuccaro adder → `symq.generators.arithmetic`; order/cache benchmarks → archive |
| `research/innovation/2026-10-28/` | scalar, factored, liveness and continuous oracles → `tests/testkit/`; pilots → archive |
| `research/hmr_native_channel/` | program families, profiler wrapper and width study → `tests/testkit/`; re-export shims removed; reports → archive |
| `research/public_qualification/` | field HMR reference → `tests/testkit/`; notes → archive |
| `research/hybrid_channel/`, `research/temporal_substitution/`, `research/phase8/`, `research/hybrid_phase_stream/` | re-export shims removed; tests import `symq.experimental.*` directly |
| `research/symq-v2/` | SAT, relational composition and strategy content condensed into [the SAT guide](guide/sat.md), [backends](guide/backends.md#native-collection) and [strategy evidence](evidence/strategy.md); pilots and results → archive |
| `research/verification_api/RESULTS/`, `RAPPORT.md`, `campaign.py` | archive commit only |
| `research/xag-synthesis/REPORT.md` | archive commit only |
| `benchmarks/results/`, `benchmarks/qualification/`, `benchmarks/native_*` | archive commit only; new results are CI artifacts |
| `docs/integration-audit.md`, `docs/research/AUDIT_2026-10-27.md`, `docs/research/IMPORT_STATUS.md`, `docs/research/ROADMAP.md` | summarized in the [changelog](../CHANGELOG.md) |

Research modules that still need work before graduation into `symq` stay under
[`research/`](../research/README.md) with their tests.

## Checks that now run only at the archive commit

- Integrity of the sealed 27 Oct 2026 handoff and its 24 archived tests.
- Output-polynomial parity between the archived engines and `sparse`/`zdd` on the 11 QCEC DEV and
  holdout circuits.
- The cross-repository audits of PRs #90–#98, which fetched pinned commits from other branches.
