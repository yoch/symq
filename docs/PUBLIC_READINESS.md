# Public presentation and release-readiness checklist

**Scope:** preparing the already-public GitHub repository for a clear public
demonstration. This is **not** a production-security certification, an arXiv
submission decision or permission to publish unreviewed scientific claims.

Snapshot assessed: 30 October 2026, after the reviewed README, CLI test,
bounded Qualtran HMR qualification and CUDD lifetime correction entered
`main`. Always verify current HEAD/CI and compare against the specific commit
you intend to demonstrate.

## A. Demonstration gates

- [ ] Clone a fresh checkout of the **intended demonstration SHA**.
- [ ] Run `python -m pip install -e .` and
      `python examples/public_demo.py` in a clean Python ≥3.10 environment.
- [ ] With `.[dev]` installed, run
      `python -m pytest -q tests/test_public_demo.py`.
- [ ] Run the public JSON `inspect / verify / replay` commands in
      [PUBLIC_DEMO.md](PUBLIC_DEMO.md). Record the return codes.
- [ ] Check the exact-head [CI workflow](../.github/workflows/ci.yml)
      (Python 3.10/3.12/3.13, pure Python, external, wheels, sanitizers).
- [ ] Make the audience-facing limitation explicit: **the demo shows two
      small declared theorem contracts, not general quantum-circuit soundness**.

The project [README](../README.md) and [architecture](ARCHITECTURE.md) are
the recommended public entry points. The demo script intentionally works
without the optional native extension; the `doctor` diagnostic returning
nonzero in that setup is not a failure of the demonstration.

## B. Repository structure and maintenance

The important division is **installed code** vs **research** vs **sealed
measurements**, not “old = broken” or “committed = generally validated”.

| Location | Policy |
| --- | --- |
| `src/symq/` | Maintained importable package; changes require semantic contracts, differential/adversarial tests and ordinary CI |
| `src/symq/experimental/` | Importable opt-in research; explicit theorem, backend, width, preparation, observation and resource limits |
| `research/` | Prototypes, prior audits and historical snapshots; useful but may contain obsolete PR statuses; no implicit API promotion |
| `benchmarks/corpus/` | Public sources with license/provenance and input manifests |
| `benchmarks/results/` and `benchmarks/qualification/` | Experimental records with exact source/binary/measurement boundaries; not runtime dependencies |
| `docs/` and `examples/` | API guides, runnable public demo, architecture and documented evidence |
| `tests/` | CI, oracle/mutation and regression checks |

**Finding:** the historical data and prototype archive are sizable and
scattered, but blindly moving or compressing tracked, sealed files would break
the existing source hashes and reproduction links. Prefer an explicit index
first. Any future migration needs a signed-off retention plan and checksum
translation. Do not copy large third-party corpora into the wheel.

## C. Public scientific claims: what is still open

The HMR `m=1/2` [Qualtran study](hmr-qualification-20261030.md) passed
coherence-sensitive checks and was integrated as **experimental qualification**,
not as a new general full-channel theorem. The earlier
[210-worker synthetic roadmap study](roadmap-evidence.md) does not establish
a native speedup.

The following remain **distinct** questions:

- [#18](https://github.com/yoch/symq/issues/18),
  [#44](https://github.com/yoch/symq/issues/44) and
  [#46](https://github.com/yoch/symq/issues/46): externally sourced,
  independently compiled and untouched confirmatory workload comparisons.
- [#19](https://github.com/yoch/symq/issues/19) and
  [#100](https://github.com/yoch/symq/issues/100): real HMR compiler coverage,
  admissibility rates, larger coherent channels and possible API promotion.
- [#20](https://github.com/yoch/symq/issues/20) and
  [#22](https://github.com/yoch/symq/issues/22): independent theorem and C
  lifecycle/resource scrutiny beyond present tests.
- [#17](https://github.com/yoch/symq/issues/17),
  [#21](https://github.com/yoch/symq/issues/21) and
  [#52](https://github.com/yoch/symq/issues/52): novelty, independent final
  scientific review, authorship/disclosures and paper presentation.

Classical [PR #26](https://github.com/yoch/symq/pull/26) and manuscript
[PR #27](https://github.com/yoch/symq/pull/27) remain separate drafts:
the former contains extensive historical records and bounded synthetic
benchmarks; the latter additionally requires author approval. Their data
must not be described as a merged `main` feature or externally confirmed
global performance advantage. The narrow CUDD finalizer fix has already
been extracted into its own maintained-code PR.

## D. Licensing, provenance and responsible disclosure

- [ ] Confirm `LICENSE` / MIT coverage for original source and retained
      [QCEC MIT corpus](../benchmarks/corpus/qcec/MANIFEST.json).
- [ ] Preserve Qualtran's [Apache-2.0 license, upstream commit and
      normalization details](../benchmarks/corpus/qualtran/README.md).
- [ ] Check historical audit archives and new large datasets for permission
      to redistribute, personal machine paths and accidental sensitive values.
      Existing integrity hashes are **not** evidence of licensing approval.
- [ ] Before an official **release or preprint**, approve author identity,
      affiliation, funding, AI assistance, citations and content in writing.
      No `CITATION.cff` or DOI is invented on the author's behalf.
- [ ] Keep [SECURITY.md](../SECURITY.md) honest about research status. No
      production security or independent formal verification is claimed.

The repository is **already public**. This checklist is a quality/review gate,
not an assertion that old public commits can be made private retrospectively.

## E. GitHub presentation and governance (maintainer action)

At this audit snapshot the repository is public and MIT-licensed. The REST
metadata showed **no topics** and an overly broad description:

> Adaptive symbolic algebra and exact verification for reversible and quantum circuits.

A more accurate suggested description:

> Exact Boolean ANF and reversible-circuit verification, with opt-in coherent HMR research.

Suggested GitHub topics: `boolean-algebra`, `reversible-computing`,
`formal-verification`, `zero-suppressed-decision-diagrams`, `quantum-computing`.
These are **recommendations**; they are not changes already made to the
repository metadata.

The GitHub `main` branch was reported **not protected** in this snapshot.
Before a wider contributor launch, configure branch protection or a ruleset
in repository Settings: require the relevant CI jobs and PR review, restrict
force pushes and require non-stale approvals where appropriate. This requires
repository administration and must be checked separately from a green CI run.

The public workflow set includes intentionally *research-specific* extra
jobs; some fetch pinned historical commits. Ordinary CI and optional audit
workflows should be distinguished in the presenter’s narrative.

## F. Release decision

**Ready to demonstrate** is satisfied when section A passes on the exact
source to be shown. **Ready for a software release** additionally requires
licensing and governance review, clearly scoped support/versioning and a
repeatable installed-wheel demo. **Ready to publish a paper** additionally
requires the separate scientific and authorship gates above.

A conference or developer presentation should not wait for every open
long-term research question, but it should **never present an exploratory
benchmark as a universal result**.

References: [README](../README.md) · [Demo](PUBLIC_DEMO.md) ·
[Architecture](ARCHITECTURE.md) · [Theorem API](experimental.md) ·
[Evidence](roadmap-evidence.md).
