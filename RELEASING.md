# Releasing SymQ

How a version goes from `main` to PyPI. Written for the maintainer; every step that publishes
something is done by a person, not by automation acting on its own.

A release makes four separate statements, and none of them implies another: the continuous
integration passed on the released commit; the public interface is the one recorded in the
[API snapshot](docs/stability.md#how-the-promise-is-checked); the files on PyPI are the ones
that were built and verified; and nothing in the release notes is a performance claim.

## Branches and versions

- Development happens on `main`, whose version ends in `.devN`.
- A release series `X.Y` lives on a branch `release/X.Y`, cut from `main`. After the cut the
  branch only receives fixes: fix on `main` first, then `git cherry-pick -x` to the branch.
- The version is written in two files, which a test keeps equal: `pyproject.toml` and
  `CITATION.cff`.
- A tag `vX.Y.Z` on `release/X.Y` is the release. The workflow refuses a tag that does not name
  the version of its tree, or whose commit is not on that branch.

## Once per repository

1. PyPI and TestPyPI: a Trusted Publisher for repository `yoch/symq`, workflow `release.yml`,
   environment `pypi` (PyPI) or `testpypi` (TestPyPI). No API token is stored anywhere.
2. GitHub environments `pypi` and `testpypi`; `pypi` with a required reviewer.
3. A ruleset that restricts who may create tags matching `v*`, and one that requires the check
   `ci-ok` on `main` and `release/*`.

## Cutting a release series

1. On `main`, every pull request meant for the series is merged and `ci-ok` is green.
2. Create `release/X.Y` from that commit.
3. On `main`: bump the version to the next series, `X.(Y+1).0.dev0`, in both files.
4. On `release/X.Y`: set the version (`X.Y.0rc1` for a rehearsal, `X.Y.0` for the release), and
   turn the `[Unreleased]` section of `CHANGELOG.md` into `## [X.Y.0] — YYYY-MM-DD`. The release
   notes are that section, word for word.

## Rehearsal

Run the **Release** workflow by hand (Actions → Release → Run workflow) on the release branch.

- Target `none` builds and verifies: source distribution, pure-Python wheel, 30 binary wheels,
  each built from the source distribution and tested; the set of files is checked to be exactly
  one release; pip installs it on Linux, macOS and Windows runners.
- Target `testpypi` then uploads the same files to TestPyPI. A version can be uploaded to an
  index once: use `X.Y.0rc1`, `rc2`, ... for repeated rehearsals.

After a TestPyPI upload, in a fresh environment outside any checkout:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ "symq==X.Y.0rc1"
python -m symq doctor --require-native   # on Linux and macOS
python -m symq --version
```

Read the TestPyPI project page: the description renders, its links lead to the tag, the
classifiers and the licence are right.

## Release

1. Name the commit: the head of `release/X.Y`, with version `X.Y.Z` and its changelog section.
2. `ci-ok` is green **on that commit**. A green run on another commit proves nothing about it.
3. Tag it and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "SymQ X.Y.Z" <commit>
   git push origin vX.Y.Z
   ```

4. The **Release** workflow starts. It builds and verifies as in the rehearsal, then waits at
   the `pypi` environment for approval. Before approving, download the `release` artifact and
   check `SHA256SUMS` against what the rehearsal of the same commit produced for the source
   distribution and the pure wheel (binary wheels are not expected to be bit-identical).
5. Approve. The workflow uploads to PyPI, attests build provenance and creates the GitHub
   Release with the files, the checksums and the changelog section.
6. Afterwards, from a fresh environment: `python -m pip install symq==X.Y.Z`, run
   `symq doctor`, compare the hashes PyPI shows with `SHA256SUMS`, and verify one file's
   provenance:

   ```bash
   gh attestation verify symq-X.Y.Z.tar.gz --repo yoch/symq
   ```

7. On `main`, carry over the dated changelog section.

## If something is wrong after publication

A file on PyPI cannot be replaced. The remedy depends on what is wrong.

- **A wrong `equivalent` or `different` verdict in the stable tier.** Yank the release on PyPI
  (it stays installable by exact version, and is no longer chosen by default), publish a patch
  release with the fix and a regression test, and say in its changelog which inputs were
  affected. The [stability policy](docs/stability.md) exempts correctness fixes from the
  deprecation period.
- **A broken wheel for one platform.** Publish a patch release; yank only if the broken wheel
  can be selected by default on a supported platform.
- **A mistake in the description or metadata only.** Fix it in the next release.

Never delete a release to reuse its version number.
