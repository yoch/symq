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
- Release preflight also requires the latest push run of `.github/workflows/ci.yml` and its
  `ci-ok` check to have succeeded on the exact checked-out commit. Missing, pending, cancelled
  or failed CI blocks both releases and rehearsals. Wait for CI, then rerun Release; a green
  run for another SHA, an older successful attempt, or another workflow cannot satisfy it.
  For multiple runs on that SHA, the highest `run_number` is required, every unfinished run
  blocks, and older runs updated at or after the newest run's `created_at` must also pass with
  their own `ci-ok`. This conservative rule catches reruns without mistaking a late finish for
  a later launch. Resolve those recent failures by rerunning CI before retrying Release; a
  failure already finished before the newest run was created does not block its success.
  An older run that ended `cancelled` (CI groups push runs by commit, so pushing one commit
  to several branches can cancel a waiting run) is not evidence either way and does not block;
  a cancelled newest run does, as do older failures, timeouts and skips. This also accepts
  an older run someone cancelled by hand: the newest run of the identical commit passed.
  This read-only, point-in-time check does not replace the protections below or the approval
  check before publication.

## Once per repository

The release workflow cannot protect itself: a tag or a manual run takes `release.yml` from the
ref it runs on, so whoever may push a `v*` tag may also change the checks. These settings are
the protection, and all of them must be in place before the first tag.

1. **Trusted Publishers**, one on PyPI and a separate one on TestPyPI. Until the first upload
   the project does not exist on the index, so each is a *pending* publisher, created from the
   account's publishing page: repository `yoch/symq`, workflow `release.yml`, and **one**
   environment, `pypi` on PyPI and `testpypi` on TestPyPI. A PyPI publisher that also accepted
   `testpypi` would let a manual run reach PyPI without approval. A pending publisher does not
   reserve the name: until the first upload, someone else can still take it.
2. **GitHub environments** `pypi` and `testpypi`, created by hand. GitHub creates a missing
   environment the first time a job names it, without any protection: `pypi` must exist
   beforehand with a required reviewer, and should allow deployments from `v*` tags only.
3. **Rulesets**: one that restricts who may create, move or delete tags matching `v*`; one that
   requires the check `ci-ok` on `main` and `release/*`.

No API token is stored anywhere.

## Cutting a release series

1. On `main`, every pull request meant for the series is merged and `ci-ok` is green.
2. Create `release/X.Y` from that commit.
3. On `main`: bump the version to the next series, `X.(Y+1).0.dev0`, in both files.
4. On `release/X.Y`: set the version (`X.Y.0rc1` for a rehearsal, `X.Y.0` for the release) in
   both files, and for the release also `date-released` in `CITATION.cff`. Turn the
   `[Unreleased]` section of `CHANGELOG.md` into `## [X.Y.0] — YYYY-MM-DD` and add its entry to
   the link definitions at the end of the file. The release notes are that section, with its
   links to repository files pointed at the tag: read it once as a reader of the release page
   would, tenses included.

## Rehearsal

Run the **Release** workflow by hand (Actions → Release → Run workflow) on the release branch.

- Target `none` builds and verifies: source distribution, pure-Python wheel, 24 binary wheels,
  each built from the source distribution and tested; the set of files is checked to be exactly
  one release; pip installs it on Linux, macOS and Windows runners.
- Target `testpypi` then uploads the same files to TestPyPI. A version can be uploaded to an
  index once: use `X.Y.0rc1`, `rc2`, ... for repeated rehearsals. The workflow can only be run
  by hand once `release.yml` is on the default branch.

After a TestPyPI upload, in a fresh environment outside any checkout:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ "symq==X.Y.0rc1"
python -m symq doctor --require-native   # where a binary wheel exists: see the README
python -m symq --version
```

SymQ has no runtime dependency, so no second index is needed, and none should be added: pip
does not rank indexes, and a package of the same name and version elsewhere could be chosen.

Read the TestPyPI project page: the description renders, the classifiers and the licence are
right. Its links to repository files point at the tag `vX.Y.0rc1`, which does not exist (only
the final version is tagged): they are expected to be dead on a rehearsal page, and alive on
the page of the release.

## Release

1. Name the commit: the head of `release/X.Y`, with version `X.Y.Z` and its changelog section.
2. `ci-ok` is green **on that commit**. A green run on another commit proves nothing about it.
3. Tag it and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "SymQ X.Y.Z" <commit>
   git push origin vX.Y.Z
   ```

4. The **Release** workflow starts. It builds and verifies as in the rehearsal, then waits at
   the `pypi` environment for approval. If a rehearsal with target `none` was run on this very
   commit, compare its `SHA256SUMS` with the one of this run for the source distribution and
   the pure wheel: they are identical when the build tools are the same (binary wheels are not
   expected to be bit-identical). A difference means a tool changed between the two runs, for
   example a new release of the build backend: find out which before approving.
5. Approve. The workflow checks that the tag still points at the commit it built and that the
   files are the verified ones, uploads to PyPI, attests build provenance and creates the
   GitHub Release with the files, the checksums and the changelog section. If the upload
   stops half-way, use "Re-run failed jobs": rebuilding would produce other files, which PyPI
   refuses under a version it already holds.
6. Afterwards, from a fresh environment: `python -m pip install symq==X.Y.Z`, run
   `symq doctor`, compare the hashes PyPI shows with `SHA256SUMS`, and verify one file's
   provenance:

   ```bash
   gh release download vX.Y.Z --repo yoch/symq --pattern "symq-X.Y.Z.tar.gz"
   gh attestation verify symq-X.Y.Z.tar.gz --repo yoch/symq
   ```

7. On `main`, carry over the dated changelog section.

## If something is wrong after publication

A file on PyPI cannot be replaced. The remedy depends on what is wrong.

- **A wrong `equivalent` or `different` verdict in the stable tier.** Publish a patch release
  with the fix and a regression test, and say in its changelog which inputs were affected;
  then yank every release that has the defect (a yanked release stays installable by exact
  version and is no longer chosen by default). In that order: yanking first would leave
  `pip install symq` with nothing to install while the fix is being made. The
  [stability policy](docs/stability.md) exempts correctness fixes from the deprecation period.
- **A broken wheel for one platform.** Publish a patch release; yank only if the broken wheel
  can be selected by default on a supported platform.
- **A mistake in the description or metadata only.** Fix it in the next release.

Never delete a release to reuse its version number.
