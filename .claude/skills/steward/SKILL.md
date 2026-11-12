---
name: steward
description: How to look after a symq pull request or release branch once it is open - reading CI, reproducing a failing job locally, fixing it, keeping release branches in step with main. Read before acting on CI results, review comments or merge conflicts in this repository.
---

# Stewarding symq pull requests

This file sets conventions for an agent that watches a pull request of this repository. It
adds nothing to anyone's access: it cannot authorize a merge, a tag, a publication or a change
of repository settings. Those stay with the maintainer. `AGENTS.md` applies in full.

## What counts

- **`ci-ok` is the only check that decides.** It is the job of `.github/workflows/ci.yml`
  that succeeds only if every required job succeeded. A green run proves something about the
  commit it ran on, and nothing about any other: read the head SHA of the run.
- The research workflows (`research.yml` and one workflow per qualification) are not
  required. A failure there is reported, not ignored, but it does not block a merge.
- Before a conditional write (`expectedHeadSha` on a merge, for example), read the full SHA
  with `git fetch` then `git rev-parse`. Never retype or reconstruct one.

## Reproducing a failing job

Each job of `ci.yml` is reproducible from a checkout. Read the job's `env:` and `run:` steps in
the workflow file rather than this summary when they differ.

| Job | Environment | Reproduce with |
| --- | --- | --- |
| `test` (3.11 to 3.14) | `SYMQ_REQUIRE_NATIVE=1`, `SYMQ_TEST_REQUIRE=native,sat,checkout,corpus_bilinear` | `ruff check .`, then `pytest -n auto -m "not timing"`, then `pytest -m timing` |
| `typecheck` | | `mypy` |
| `macos` | `native,sat` | `pytest -m "core and not timing"`, `pytest -m "core and timing"`, `pytest tests/test_public_api.py` |
| `windows-pure` | `sat`, no native core | `pytest --collect-tier core -m "core and not native and not timing"` |
| `pure-python` | `sat`; installed with `SYMQ_SKIP_NATIVE=1` | `pytest -m "not native and not timing"` |
| `qcec-crosscheck` | `native,sat,qcec`, extra `crosscheck` | `pytest tests/test_qcec_crosscheck.py tests/test_external.py -k qcec` |
| `wheel` | | builds the wheel and the sdist, `tools/release_check.py sdist`, `tools/pypi_readme.py --check`, then runs the suite inside the extracted sdist |
| `sanitizers` | | `python tools/sanitize_native.py` |
| `coverage` | `native,sat,checkout` | the `core` tests with `--cov`; the floor is `--cov-fail-under` in the workflow |

`SYMQ_TEST_REQUIRE` turns the skip of a missing capability into an error; set it locally to
the job's value, or a failure may hide as a skip. `python tools/build_native.py --require`
builds the native core and fails rather than skipping. With `mqt.qcec` installed, `mypy`
reports one known mismatch in `src/symq/external/qcec.py`; the CI job does not install it.

## Fixing

- Find the root cause. A job gets one re-run at most; "flaky" is not a cause.
- Never skip, `xfail`, loosen or delete a test to get green, and never lower the coverage
  floor, a budget of the cross-check or a ceiling of `tools/release_check.py` for that purpose.
- Several tests pin the exact steps of the workflows (`tests/test_ci_workflow.py`,
  `tests/test_release_workflow.py`). A change to a workflow updates those tests in the same
  pull request, with the reason. An automated update of pinned actions fails them by design:
  report it to the maintainer instead of editing the tests on that branch.
- `tests/data/api_snapshot.json` changes only through `python tools/api_snapshot.py --write`
  (Python 3.12, native core and SAT present, `symq` imported from this checkout), and only when
  the interface change is intended and stated in the pull request.
- Before pushing: `ruff check .`, `mypy`, and the tests of the job that failed with its
  environment; for anything wider, the full suite with
  `SYMQ_TEST_REQUIRE=native,sat,checkout,corpus_bilinear` (add `qcec` when it is installed).
- Figures in commit messages and pull request descriptions (tests passed, files changed,
  cases found) are copied from the output of the run that produced them.

## Merge conflicts and stuck runs

- Merge the base into the head; do not rebase or force-push a shared branch.
- GitHub can report a conflict on a branch whose history crosses the base twice (a branch
  that merged an integration branch) although `git merge` is clean. Merging the base into the
  head resolves it; the tree may stay identical.
- A run that stays queued with no job and cannot be cancelled or re-run is replaced by
  pushing a real change, such as merging the updated base. Never push an empty commit and never
  close and reopen a pull request to start CI.

## Release branches

- `release/X.Y` is cut from a commit of `main` whose `ci-ok` is green. A fix found on a release
  branch goes to `main` first, then to the release branch with `git cherry-pick -x`, through a
  pull request on that branch.
- A tag `v*` is a publication: the Release workflow uploads to PyPI, where a version can never
  be replaced. No agent pushes such a tag without the maintainer's explicit go, given at that
  moment for that commit. The procedure is `RELEASING.md`.
