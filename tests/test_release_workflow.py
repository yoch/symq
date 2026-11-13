"""The release workflow publishes only what it built, verified and was allowed to publish.

``.github/workflows/release.yml`` cannot be run by the test suite. These guards read it and hold
the properties that matter if someone edits it: where the credentials are, what each publishing
job may do, and that nothing reaches an index without passing through the checks.
"""
from __future__ import annotations

import pytest
import yaml

from tests.conftest import ROOT

PATH = ROOT / ".github" / "workflows" / "release.yml"
PUBLISHERS = {"testpypi": "testpypi", "pypi": "pypi"}
"""Job -> GitHub environment. PyPI's Trusted Publisher is registered with these exact names and
with the file name ``release.yml``."""


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def _uses(job: dict) -> list[str]:
    return [str(step["uses"]).split("@")[0] for step in job["steps"] if "uses" in step]


def _runs(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def test_the_file_and_environment_names_are_the_ones_registered_with_pypi(workflow):
    assert PATH.name == "release.yml"
    for name, environment in PUBLISHERS.items():
        assert workflow["jobs"][name]["environment"] == environment


def test_it_runs_for_version_tags_and_manual_rehearsals_only(workflow):
    triggers = workflow[True]  # PyYAML reads the key ``on`` as the boolean True
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"tags": ["v*"]}
    target = triggers["workflow_dispatch"]["inputs"]["target"]
    assert target["options"] == ["none", "testpypi"] and target["default"] == "none"
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_only_the_publishing_jobs_hold_write_permissions(workflow):
    assert workflow["permissions"] == {"contents": "read"}
    elevated = {name: job["permissions"] for name, job in workflow["jobs"].items()
                if "permissions" in job}
    assert elevated == {
        "preflight": {"contents": "read", "actions": "read", "checks": "read"},
        "testpypi": {"id-token": "write", "checks": "read"},
        "pypi": {"id-token": "write", "checks": "read"},
        "github-release": {"contents": "write", "id-token": "write", "attestations": "write"},
    }


DOWNLOAD = "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333"
PUBLISH = "pypa/gh-action-pypi-publish@7245906fb61fa33a13554f9d5fb856fe61758086"
ATTEST = "actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8"

VERIFIED = {
    "name": "The files are the verified ones",
    "env": {"SUMS": "${{ needs.verify.outputs.sums }}"},
    "run": 'echo "$SUMS  dist/SHA256SUMS" | sha256sum -c -\ncd dist && sha256sum -c SHA256SUMS\n',
}
RELEASE_FILES = {"uses": DOWNLOAD, "with": {"name": "release", "path": "dist"}}
TAG_IS_CURRENT = "The tag still points at the commit that was built"
CI_STILL_PASSES = "ci-ok still passes on the release commit"

CREDENTIALED = {
    "testpypi": [
        CI_STILL_PASSES, RELEASE_FILES, VERIFIED, {"run": "rm dist/SHA256SUMS"},
        {"uses": PUBLISH, "with": {"repository-url": "https://test.pypi.org/legacy/",
                                   "packages-dir": "dist"}},
    ],
    "pypi": [
        TAG_IS_CURRENT, CI_STILL_PASSES, RELEASE_FILES, VERIFIED, {"run": "rm dist/SHA256SUMS"},
        {"uses": PUBLISH, "with": {"packages-dir": "dist"}},
    ],
    "github-release": [
        TAG_IS_CURRENT, RELEASE_FILES, VERIFIED,
        {"uses": DOWNLOAD, "with": {"name": "release-notes", "path": "notes"}},
        {"uses": ATTEST, "with": {"subject-path": "dist/*.whl\ndist/*.tar.gz\n"}},
        "gh release create",
    ],
}
"""The complete list of steps of each job that holds a credential. An allow-list: a step added
to one of these jobs fails the test until it is written here, where a reviewer sees it."""


@pytest.mark.parametrize("name", list(CREDENTIALED))
def test_a_job_with_a_credential_does_exactly_these_steps_and_nothing_else(workflow, name):
    """It checks the tag, downloads the verified files, checks them and hands them over.

    No checkout, no interpreter, no build: the code of the tagged tree never runs where a
    credential is.
    """
    job = workflow["jobs"][name]
    assert job["runs-on"] == "ubuntu-latest"
    assert "env" not in job and "container" not in job and "services" not in job
    steps = job["steps"]
    expected = CREDENTIALED[name]
    assert len(steps) == len(expected), [step.get("name") or step.get("uses") or step.get("run")
                                         for step in steps]
    for step, wanted in zip(steps, expected):
        assert "if" not in step and "continue-on-error" not in step and "shell" not in step
        if wanted == TAG_IS_CURRENT:
            assert step["name"] == TAG_IS_CURRENT and set(step) == {"name", "run"}
            run = step["run"]
            assert 'git ls-remote "$remote" "refs/tags/$GITHUB_REF_NAME^{}"' in run
            assert run.rstrip().endswith('test "$resolved" = "$GITHUB_SHA"')
            assert "||" not in run and "true" not in run
        elif wanted == CI_STILL_PASSES:
            assert step["name"] == CI_STILL_PASSES and set(step) == {"name", "env", "run"}
            assert step["env"] == {"GH_TOKEN": "${{ github.token }}",
                                   "GH_REPO": "${{ github.repository }}"}
            assert step["run"].startswith("checks=$(gh api --method GET ")
            assert "python" not in step["run"] and "||" not in step["run"]
        elif wanted == "gh release create":
            assert set(step) == {"env", "run"}
            assert step["env"] == {
                "GH_TOKEN": "${{ github.token }}", "GH_REPO": "${{ github.repository }}",
                "TAG": "${{ github.ref_name }}", "VERSION": "${{ needs.preflight.outputs.version }}"}
            lines = [line.strip() for line in step["run"].strip().splitlines()]
            assert lines == [
                'prerelease=""',
                'case "$VERSION" in *rc*) prerelease="--prerelease" ;; esac',
                ('gh release create "$TAG" dist/* --verify-tag --title "SymQ $VERSION" '
                 "--notes-file notes/release-notes.md $prerelease"),
            ]
        else:
            assert step == wanted


def test_no_run_block_interpolates_an_expression(workflow, nightly):
    """``${{ ... }}`` inside a script is pasted into it before the shell reads it: a ref name
    or an input could then be code. Values reach scripts through ``env`` only."""
    for document in (workflow, nightly):
        for name, job in document["jobs"].items():
            for step in job["steps"]:
                assert "${{" not in str(step.get("run", "")), (name, step.get("run"))


def test_no_secret_is_used_anywhere(workflow, nightly):
    for path in (PATH, ROOT / ".github" / "workflows" / "nightly.yml"):
        assert "secrets." not in path.read_text(encoding="utf-8")


def test_only_the_verify_job_produces_the_artifact_that_gets_published(workflow):
    """Any other job uploading an artifact named ``release`` could replace the verified files."""
    uploads = {}
    for name, job in workflow["jobs"].items():
        for step in job["steps"]:
            if "upload-artifact" in str(step.get("uses")):
                uploads.setdefault(name, []).append(step["with"])
    assert set(uploads) == {"preflight", "sdist-pure", "wheels", "verify"}
    assert [upload["name"] for upload in uploads["verify"]] == ["release"]
    for name in ("preflight", "sdist-pure", "wheels"):
        for upload in uploads[name]:
            assert upload["name"] != "release" and not upload["name"].startswith("release-") \
                or upload["name"] == "release-notes", (name, upload)
    assert all("overwrite" not in upload for group in uploads.values() for upload in group)


def test_the_verify_job_checks_last_and_exports_the_digest_of_the_checksums(workflow):
    job = workflow["jobs"]["verify"]
    assert job["outputs"] == {"sums": "${{ steps.sums.outputs.digest }}"}
    runs = [str(step.get("run", "")) for step in job["steps"]]
    check = next(i for i, run in enumerate(runs) if "release_check.py artifacts dist --write-sums" in run)
    sums = next(i for i, step in enumerate(job["steps"]) if step.get("id") == "sums")
    upload = next(i for i, step in enumerate(job["steps"])
                  if "upload-artifact" in str(step.get("uses")))
    # Nothing that installs or runs a tool comes between the check and the upload.
    assert (check, sums, upload) == (len(runs) - 3, len(runs) - 2, len(runs) - 1)
    assert runs[check] == "python tools/release_check.py artifacts dist --write-sums"
    assert "sha256sum dist/SHA256SUMS" in runs[sums] and "pip" not in runs[sums]
    for step in job["steps"]:
        assert "if" not in step and "continue-on-error" not in step


def test_pypi_is_reached_from_a_tag_only_and_the_test_index_from_a_manual_run_only(workflow):
    jobs = workflow["jobs"]
    assert jobs["pypi"]["if"] == (
        "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')")
    assert jobs["github-release"]["if"] == jobs["pypi"]["if"]
    assert jobs["testpypi"]["if"] == (
        "github.event_name == 'workflow_dispatch' && inputs.target == 'testpypi'")
    publish = {name: next(step for step in jobs[name]["steps"]
                          if "gh-action-pypi-publish" in str(step.get("uses")))
               for name in PUBLISHERS}
    assert publish["testpypi"]["with"]["repository-url"] == "https://test.pypi.org/legacy/"
    assert "repository-url" not in publish["pypi"]["with"]  # the default index: PyPI itself
    for step in publish.values():
        assert "password" not in step["with"] and "user" not in step["with"]  # OIDC only


def test_nothing_is_published_before_it_was_verified_and_installed(workflow):
    jobs = workflow["jobs"]
    for name in PUBLISHERS:
        assert set(jobs[name]["needs"]) == {"verify", "install"}
    # A GitHub Release only for what PyPI took.
    assert set(jobs["github-release"]["needs"]) == {"preflight", "verify", "pypi"}
    assert "wheels" in jobs["verify"]["needs"] and "verify" in jobs["install"]["needs"]
    assert jobs["wheels"]["needs"] == "sdist-pure" and jobs["sdist-pure"]["needs"] == "preflight"
    for job in jobs.values():
        assert "continue-on-error" not in job
        assert all("continue-on-error" not in step for step in job["steps"])


def test_the_publishing_jobs_take_the_verified_files_and_nothing_else(workflow):
    for name in (*PUBLISHERS, "github-release"):
        downloads = [step["with"] for step in workflow["jobs"][name]["steps"]
                     if "download-artifact" in str(step.get("uses"))]
        assert {"name": "release", "path": "dist"} in downloads, name
        assert all("pattern" not in download for download in downloads), name
    uploads = [step["with"] for step in workflow["jobs"]["verify"]["steps"]
               if "upload-artifact" in str(step.get("uses"))]
    assert [upload["name"] for upload in uploads] == ["release"]
    assert "tools/release_check.py artifacts dist --write-sums" in _runs(workflow["jobs"]["verify"])


def test_the_tag_is_checked_before_anything_is_built(workflow):
    job = workflow["jobs"]["preflight"]
    assert "tools/release_check.py preflight" in _runs(job)
    checkout = next(step for step in job["steps"] if "checkout" in str(step.get("uses")))
    assert checkout["with"]["fetch-depth"] == 0  # the ancestry check needs the release branch
    assert " | " not in _runs(job)  # a pipe would hide the failure of the check


def test_exact_commit_ci_is_required_before_every_release_or_rehearsal(workflow):
    job = workflow["jobs"]["preflight"]
    step = next(step for step in job["steps"] if "release_ci.py" in step.get("run", ""))
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}", "GH_REPO": "${{ github.repository }}"}
    assert "if" not in step and "continue-on-error" not in step
    assert step["run"].strip().splitlines() == [
        'commit=$(git rev-parse --verify "$GITHUB_SHA^{commit}")',
        'test "$commit" = "$(git rev-parse --verify HEAD^{commit})"',
        'python tools/release_ci.py --repo "$GH_REPO" --sha "$commit" --wait 1800',
    ]
    # Preflight holds only read permissions; tagged source still never runs with write access.
    assert job["permissions"] == {"contents": "read", "actions": "read", "checks": "read"}
    assert workflow["jobs"]["sdist-pure"]["needs"] == "preflight"


def test_every_binary_wheel_is_built_from_the_source_distribution(workflow):
    job = workflow["jobs"]["wheels"]
    assert "actions/checkout" not in _uses(job)  # nothing but the sdist reaches the build
    build = next(step for step in job["steps"] if "cibuildwheel" in str(step.get("uses")))
    assert build["with"]["package-dir"] == "${{ steps.sdist.outputs.path }}"
    assert "dist/symq-*.tar.gz" in _runs(job)
    assert job["strategy"]["matrix"]["os"] == [
        "ubuntu-latest", "ubuntu-24.04-arm", "macos-15-intel", "macos-15"]
    assert job["strategy"]["fail-fast"] is False
    pure = _runs(workflow["jobs"]["sdist-pure"])
    assert "pip wheel --no-deps -w dist dist/*.tar.gz" in pure and "build --sdist" in pure


def test_installation_is_tried_where_users_are_including_where_no_binary_wheel_exists(workflow):
    job = workflow["jobs"]["install"]
    rows = job["strategy"]["matrix"]["include"]
    assert {row["os"] for row in rows} == {
        "ubuntu-latest", "ubuntu-24.04-arm", "macos-15", "macos-15-intel", "windows-latest"}
    pure = [(row["os"], row["python"]) for row in rows if not row["native"]]
    assert pure == [("windows-latest", "3.12"), ("ubuntu-latest", "3.14t")]
    runs = _runs(job)
    # Only the built files, and never a silent build from the source distribution.
    assert "--no-index --find-links dist --only-binary symq" in runs
    assert "doctor --require-native" in runs
    assert job["defaults"]["run"]["shell"] == "bash"


# ---- nightly.yml: drift that no commit causes ----

@pytest.fixture(scope="module")
def nightly() -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / "nightly.yml").read_text(encoding="utf-8"))


def test_the_nightly_run_publishes_nothing_and_holds_no_credential(nightly):
    assert nightly["permissions"] == {"contents": "read"}
    for name, job in nightly["jobs"].items():
        assert "permissions" not in job and "environment" not in job, name
        assert not any("pypi-publish" in str(step.get("uses")) for step in job["steps"]), name
        assert "gh release" not in _runs(job) and "twine upload" not in _runs(job), name


def test_the_nightly_run_covers_main_and_every_release_branch(nightly):
    """A scheduled workflow only runs from the default branch: the other branches are checked
    out explicitly, or a quiet release branch would never learn that a dependency moved."""
    listing = _runs(nightly["jobs"]["branches"])
    assert 'gh api "repos/$GITHUB_REPOSITORY/branches" --paginate' in listing
    assert 'n.startswith("release/")' in listing and '"main"' in listing
    for name in ("fresh-dependencies", "next-python", "wheels"):
        job = nightly["jobs"][name]
        assert job["strategy"]["matrix"]["branch"] == "${{ fromJSON(needs.branches.outputs.list) }}"
        checkout = next(step for step in job["steps"] if "checkout" in str(step.get("uses")))
        assert checkout["with"]["ref"] == "${{ matrix.branch }}", name


def test_the_nightly_wheels_are_built_the_way_the_release_builds_them(nightly, workflow):
    release = next(step for step in workflow["jobs"]["wheels"]["steps"]
                   if "cibuildwheel" in str(step.get("uses")))
    rehearsal = next(step for step in nightly["jobs"]["wheels"]["steps"]
                     if "cibuildwheel" in str(step.get("uses")))
    assert rehearsal["uses"] == release["uses"]  # the same pinned builder
    assert rehearsal["with"]["package-dir"] == "${{ steps.sdist.outputs.path }}"  # from the sdist
    assert (nightly["jobs"]["wheels"]["strategy"]["matrix"]["os"]
            == workflow["jobs"]["wheels"]["strategy"]["matrix"]["os"])


def test_only_the_look_at_the_next_python_may_fail_quietly(nightly):
    quiet = [name for name, job in nightly["jobs"].items() if job.get("continue-on-error")]
    assert quiet == ["next-python"]
    assert nightly["jobs"]["fresh-dependencies"]["env"]["SYMQ_TEST_REQUIRE"] == "native,sat"


def test_the_nightly_run_tests_each_branch_on_the_oldest_python_it_supports(nightly, tmp_path):
    """release/0.2 supports 3.10 and main does not: a fixed version would test one of them on
    a Python it does not claim, or leave the other untested. The oldest version is read from
    the checked-out branch's requires-python."""
    import subprocess
    import sys
    import tomllib

    oldest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"]["requires-python"].removeprefix(">=")
    job = nightly["jobs"]["fresh-dependencies"]
    assert job["strategy"]["matrix"]["python"] == ["oldest", "3.14"]
    steps = job["steps"]
    checkout = next(step for step in steps if "actions/checkout" in step.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ matrix.branch }}"
    reader = next(step for step in steps if step.get("id") == "python")
    assert reader["env"]["WANTED"] == "${{ matrix.python }}"
    setup = next(step for step in steps if "setup-python" in step.get("uses", ""))
    assert setup["with"]["python-version"] == "${{ steps.python.outputs.version }}"
    # After the branch's checkout (it reads that branch's pyproject), before Python is set up.
    assert steps.index(checkout) < steps.index(reader) < steps.index(setup)
    # The shell around it: "oldest" takes the one-liner's output, any other value is kept.
    lines = [line.strip() for line in reader["run"].strip().splitlines()]
    opening = "version=$(python3 -c '"
    assert lines[0] == 'if [ "$WANTED" = oldest ]; then'
    assert lines[1].startswith(opening) and lines[1].endswith("')")
    assert lines[2:] == ["else", 'version="$WANTED"', "fi",
                         'echo "version=$version" >> "$GITHUB_OUTPUT"']
    # The one-liner itself, run on this checkout by the tested interpreter (the workflow runs
    # on Linux only; a Windows runner has no usable python3 on bash's path).
    code = lines[1][len(opening):-len("')")]
    printed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout
    assert printed.strip() == oldest


def _recheck(job: dict) -> dict:
    return next(step for step in job["steps"] if step.get("name") == CI_STILL_PASSES)


@pytest.mark.parametrize("name", ["testpypi", "pypi"])
def test_publishing_rechecks_ci_ok_without_running_repository_code(workflow, name):
    job = workflow["jobs"][name]
    step = _recheck(job)
    assert job["steps"].index(step) < next(
        index for index, item in enumerate(job["steps"]) if "pypi-publish" in str(item.get("uses")))
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}", "GH_REPO": "${{ github.repository }}"}
    assert "if" not in step and "continue-on-error" not in step
    assert "actions/checkout" not in _uses(job) and "python" not in step["run"]
    assert step["run"] == _recheck(workflow["jobs"]["pypi"])["run"]


SHA = "b" * 40


def _check_run(started, conclusion, status="completed", slug="github-actions", sha=SHA):
    return {"app": {"slug": slug}, "head_sha": sha, "status": status, "conclusion": conclusion,
            "started_at": started}


@pytest.mark.parametrize("runs,passes", [
    ([_check_run("2026-11-13T10:00:00Z", "success")], True),
    ([_check_run("2026-11-13T09:00:00Z", "failure"),
      _check_run("2026-11-13T10:00:00Z", "success")], True),
    ([_check_run("2026-11-13T10:00:00Z", "success"),
      _check_run("2026-11-13T11:00:00Z", "failure")], False),
    ([_check_run("2026-11-13T10:00:00Z", "success"),
      _check_run("2026-11-13T11:00:00Z", None, status="in_progress")], False),
    ([_check_run("2026-11-13T10:00:00Z", "success", slug="other-app")], False),
    ([_check_run("2026-11-13T10:00:00Z", "success", sha="c" * 40)], False),
    ([], False),
])
def test_publication_recheck_script(workflow, tmp_path, runs, passes):
    import json
    import os
    import shutil
    import subprocess

    bash, jq = shutil.which("bash"), shutil.which("jq")
    if bash is None or jq is None:
        pytest.skip("bash and jq run the recheck on the release runner; not on this host")
    stub = tmp_path / "gh"
    stub.write_text("#!/bin/sh\ncat \"$GH_FIXTURE\"\n")
    stub.chmod(0o755)
    fixture = tmp_path / "checks.json"
    fixture.write_text(json.dumps({"total_count": len(runs), "check_runs": runs}))
    done = subprocess.run(
        [bash, "-e", "-c", _recheck(workflow["jobs"]["pypi"])["run"]], capture_output=True,
        text=True, check=False,
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
             "GH_FIXTURE": str(fixture), "GITHUB_SHA": SHA, "GH_REPO": "yoch/symq"})
    assert (done.returncode == 0) is passes, done.stderr
