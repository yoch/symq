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


def test_only_the_publishing_jobs_hold_a_credential(workflow):
    assert workflow["permissions"] == {"contents": "read"}
    elevated = {name: job["permissions"] for name, job in workflow["jobs"].items()
                if "permissions" in job}
    assert elevated == {
        "testpypi": {"id-token": "write"},
        "pypi": {"id-token": "write"},
        "github-release": {"contents": "write", "id-token": "write", "attestations": "write"},
    }


@pytest.mark.parametrize("name", [*PUBLISHERS, "github-release"])
def test_a_job_with_a_credential_runs_no_code_of_the_repository(workflow, name):
    """It downloads the verified files and hands them over: no checkout, no install, no build."""
    job = workflow["jobs"][name]
    assert "actions/checkout" not in _uses(job)
    assert "actions/setup-python" not in _uses(job)
    for word in ("python", "pip", "tools/", "pytest", "curl", "wget"):
        assert word not in _runs(job), (name, word)


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
    assert "pypi" in jobs["github-release"]["needs"]  # a GitHub Release only for what PyPI took
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
    assert "refs/heads/release/*" in _runs(nightly["jobs"]["branches"])
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
