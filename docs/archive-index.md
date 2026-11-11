# Research archive index

On 31 October 2026 the repository was reorganized so that `main` holds the maintained package,
its tests, the public corpora and the documentation. Prototypes, recorded measurements and dated
audit reports were removed from the tree. **Nothing was rewritten:** every removed file is
byte-identical in the history of `main` at commit
[`d18e0183`](https://github.com/yoch/symq/tree/d18e0183f8a3279e79757ffd75bd285da5323bb3), including
the sealed `MANIFEST.sha256` and `SHA256SUMS` files.

The annotated tag
[`archive/2026-10-31`](https://github.com/yoch/symq/tree/archive/2026-10-31) names that
commit and is the stable reference to the archive. It is a Git tag, not a published release. The
`research-archive` branch mentioned in the original work plan was not created; the tag replaces
it, and it must never be moved or deleted.

To work with the archived material:

```bash
git fetch origin tag archive/2026-10-31
git worktree add ../symq-archive archive/2026-10-31
cd ../symq-archive
python research/verify_archive.py
```

`verify_archive.py` checks the 29 digests of the sealed manifest; it passed on the tagged commit on
31 October 2026.

## What moved where

| Former location | Now |
| --- | --- |
| `research/archive/2026-10-27/` (sealed ANF/ZDD handoff) and `research/verify_archive.py` | archive commit only |
| `research/audit_crossrepo_20261029/`, `research/external_audit/`, the cross-repository audit tests and workflows | archive commit only; they tested code on other branches |
| `research/engineering/2026-10-28/` | Cuccaro adder → `symq.generators.arithmetic`; order/cache benchmarks → archive |
| `research/innovation/2026-10-28/` | scalar, factored, liveness and continuous oracles → `tests/testkit/`; pilots → archive |
| `research/hmr_native_channel/` | program families, profiler wrapper and width study → `tests/testkit/`; re-export shims removed; reports → archive |
| `research/public_qualification/` | field HMR reference → `tests/testkit/`; notes → archive |
| `research/hybrid_channel/`, `research/temporal_substitution/`, `research/phase8/`, `research/hybrid_phase_stream/` | re-export shims removed; tests import `symq.labs.*` directly |
| `research/symq-v2/` | SAT, relational composition and strategy content condensed into [the SAT guide](guide/sat.md), [backends](guide/backends.md#native-collection) and [strategy evidence](evidence/strategy.md); pilots and results → archive |
| `research/verification_api/RESULTS/`, `RAPPORT.md`, `campaign.py` | archive commit only |
| `research/xag-synthesis/REPORT.md` | archive commit only |
| `benchmarks/results/`, `benchmarks/qualification/`, `benchmarks/native_*` | archive commit only; new results are CI artifacts |
| `docs/integration-audit.md`, `docs/research/AUDIT_2026-10-27.md`, `docs/research/IMPORT_STATUS.md`, `docs/research/ROADMAP.md` | summarized in the [changelog](../CHANGELOG.md) |

The research modules that were still under test moved into the installed `symq.labs` package:
`bitset_degree3` → `symq.labs.bitset_anf`, `finite_domain`, `linear_certificate`;
`hmr_feedback` → `symq.labs.hmr_repair`; `verification_api` → `symq.labs.verification_contracts`
and `corpus_qualification`; `xag-synthesis` → `symq.generators.gf2n` (field arithmetic and
multipliers) and `symq.labs.xag` (analyses). Their notes are in [docs/labs](labs/).

## Documents retired after the reorganization

Two French-language working documents were removed from the tree in November 2026, because public
documentation is kept in English. They are unchanged in the history of `main` and are **not** part
of the `archive/2026-10-31` tag, which predates them; the links below name a commit of
`main` that contains them.

| Former location | Content | Commit containing it |
| --- | --- | --- |
| `docs/plans/2026-10-31-workplan.md` | Work plan of 31 Oct 2026 (lots, deferred items, proposed version tags); superseded by the [changelog](../CHANGELOG.md) and later plans | [`2db0af8`](https://github.com/yoch/symq/blob/2db0af8fb29d1e756094ba47b54ebc217824e57b/docs/plans/2026-10-31-workplan.md) |
| `docs/audit/phase_discovery_163.md` | Reviewer brief for the independent audit of pull request #163 | [`2db0af8`](https://github.com/yoch/symq/blob/2db0af8fb29d1e756094ba47b54ebc217824e57b/docs/audit/phase_discovery_163.md) |

## Imports from `research.*`

The `research` directory is no longer a package on `main`, so `import research...` fails. The
modules that were still under test are installed as `symq.labs.*` (table above); the others are
available only at the archive tag. They never had an API promise.

## Open historical pull requests

Two draft pull requests predate the reorganization and are left untouched by it:

- [#26](https://github.com/yoch/symq/pull/26) holds the matched benchmark harness and its
  qualification data. Its measurements keep their recorded source and binary identities (native
  ABI 4 and 5). They are not relabelled, and they are not presented as reproduced on ABI 6.
- [#27](https://github.com/yoch/symq/pull/27), the manuscript, stays bound to the frozen data of #26.

`main` now uses native ABI 6. A future measurement campaign starts from a harness rebased on ABI 6
and records new source, binary and environment receipts. It does not overwrite or reinterpret the
historical results.

## Checks that now run only at the archive commit

- Integrity of the sealed 27 Oct 2026 handoff and its 24 archived tests.
- The cross-repository audits of PRs #90–#98, which fetched pinned commits from other branches.

The output-polynomial parity between the archived engines and the current backends on the 11 QCEC
DEV and holdout circuits still runs on `main`. The archived engines' outputs were recorded once
at the archive commit as per-circuit digests (`tests/data/archived_engine_outputs.json`), and
`tests/test_archived_parity.py` checks that every current backend reproduces them.
