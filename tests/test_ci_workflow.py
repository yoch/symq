"""The CI workflow must parse, and the SAT job must really run the SAT tests.

Four consecutive pushes produced runs with **zero jobs**. The cause was not the code and not
GitHub: a step contained an inline Python string with a colon-space inside a YAML scalar, so the
whole workflow file failed to parse and no job could even start. A green tick is worthless if the
file does not load, and nothing in the suite would have caught it.

This test parses the workflow with a real YAML parser and checks the invariants the audit asked
for: the SAT tests are executed explicitly, and availability is asserted rather than assumed.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # a declared test dependency: a guard that can skip itself is not a guard

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "ci.yml"
RESEARCH = WORKFLOWS / "research.yml"
ALL_WORKFLOWS = sorted(WORKFLOWS.glob("*.yml"))


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


@pytest.fixture(scope="module")
def research() -> dict:
    return yaml.safe_load(RESEARCH.read_text())


def _triggers(document: dict) -> dict:
    # YAML 1.1 reads the bare key ``on`` as the boolean True.
    return document.get("on", document.get(True))


def test_the_workflow_parses(workflow):
    assert workflow.get("jobs"), "the workflow has no jobs"


def test_every_job_has_at_least_one_step(workflow):
    for name, job in workflow["jobs"].items():
        assert job.get("steps"), f"job {name} has no steps"


def test_the_pure_python_job_runs_the_sat_tests(workflow):
    """A job that skips the SAT module validates nothing about it."""
    steps = " ".join(str(step.get("run", ""))
                     for step in workflow["jobs"]["pure-python"]["steps"])
    assert "test_sat_equivalence.py" in steps
    assert "test_sat_timeout.py" in steps
    assert "test_sat_availability.py" in steps


def test_the_pure_python_job_asserts_solver_availability(workflow):
    steps = " ".join(str(step.get("run", ""))
                     for step in workflow["jobs"]["pure-python"]["steps"])
    assert "symq.sat" in steps and "available()" in steps


def test_every_run_step_is_a_syntactically_valid_shell_command(workflow, research):
    """A quoting mistake in a ``run:`` line fails the job at shell level, not at parse time.

    Four pushes were also lost to a stray apostrophe that made bash report "unexpected EOF" --
    the workflow parsed, but the step could never execute. ``bash -n`` catches it.
    """
    import shutil
    import subprocess

    # The full path: on Windows a bare "bash" is resolved in the system directory first, where
    # it is the WSL launcher, not the Git bash that the workflow steps run in.
    bash = shutil.which("bash")
    if bash is None or subprocess.run([bash, "-n"], input=b"true\n",
                                      capture_output=True, check=False).returncode != 0:
        pytest.skip("no working bash to check the syntax with")
    broken = []
    for document in (workflow, research):
        for name, job in document["jobs"].items():
            for step in job.get("steps", []):
                command = step.get("run")
                if not command:
                    continue
                # Bytes, with LF: in text mode Windows would hand bash ``\r\n`` line ends.
                result = subprocess.run([bash, "-n"], input=command.encode("utf-8"),
                                        capture_output=True, check=False)
                if result.returncode != 0:
                    broken.append((name, command.splitlines()[0][:60],
                                   result.stderr.decode("utf-8", "replace").strip()))
    assert not broken, f"invalid shell in {broken}"


def test_windows_jobs_run_their_steps_in_bash(workflow):
    """The default shell on Windows runners is PowerShell, where the quoting of the ``run:``
    lines means something else and ``bash -n`` above would check the wrong language."""
    windows = [name for name, job in workflow["jobs"].items() if "windows" in str(job["runs-on"])]
    assert windows == ["windows-pure"]
    for name in windows:
        job = workflow["jobs"][name]
        assert job["defaults"]["run"]["shell"] == "bash", name
        assert all("shell" not in step for step in job["steps"]), name  # no step opts out


def _pytest_runs(job: dict) -> list[str]:
    return [str(step["run"]) for step in job["steps"] if "pytest" in str(step.get("run"))]


def test_macos_runs_the_whole_core_tier_with_the_native_core(workflow):
    """The release builds macOS wheels: a hand-picked list of test files is not enough."""
    job = workflow["jobs"]["macos"]
    assert job["env"] == {"SYMQ_REQUIRE_NATIVE": "1", "SYMQ_TEST_REQUIRE": "native,sat"}
    assert _pytest_runs(job) == [
        'python -m pytest -q -n auto -m "core and not timing" --durations=25',
        'python -m pytest -q -m "core and timing"',
        "python -m pytest -q tests/test_public_api.py",
    ]


def test_windows_runs_the_whole_core_tier_as_pure_python_without_being_told_to(workflow):
    job = workflow["jobs"]["windows-pure"]
    # SAT must really run there; and no SYMQ_SKIP_NATIVE: the build itself must not compile.
    assert job["env"] == {"SYMQ_TEST_REQUIRE": "sat"}
    assert all("env" not in step for step in job["steps"])
    # --collect-tier: deselecting is not enough there, research modules import POSIX-only
    # modules and fail at collection, before any marker applies.
    assert _pytest_runs(job) == [
        ('python -m pytest -q -n auto --collect-tier core -m "core and not native and not timing"'
         " --durations=25"),
        'python -m pytest -q --collect-tier core -m "core and not native and timing"',
    ]
    runs = [str(step.get("run", "")) for step in job["steps"]]
    assert any("'zdd-native' not in BACKENDS" in run for run in runs)


def test_no_test_step_of_the_required_workflow_can_fail_quietly(workflow):
    """``|| true``, a pipe or ``--collect-only`` would turn a failing or absent run green."""
    for name, job in workflow["jobs"].items():
        for run in _pytest_runs(job):
            for line in run.splitlines():
                if "pytest" in line:
                    for hole in ("||", "|", ";", "--collect-only", "--co ", "-x ", "--exitfirst"):
                        assert hole not in line, (name, line)


def test_the_independent_cross_check_is_a_required_job_that_cannot_skip(workflow):
    """SymQ against MQT QCEC, with the C core and SAT: required by ``ci-ok``, and a missing
    capability is an error, not a skip."""
    import re

    job = workflow["jobs"]["qcec-crosscheck"]
    assert "qcec-crosscheck" in workflow["jobs"]["ci-ok"]["needs"]
    assert "continue-on-error" not in job
    assert job["env"] == {"SYMQ_REQUIRE_NATIVE": "1", "SYMQ_TEST_REQUIRE": "native,sat,qcec"}
    runs = [str(step.get("run", "")) for step in job["steps"] if "run" in step]
    assert runs == [
        'python -m pip install -e ".[test,crosscheck]"',
        "python -m pytest -q tests/test_qcec_crosscheck.py tests/test_external.py -k qcec",
    ]
    # The extra is held to one minor series: an upstream release cannot redden the required
    # check by surprise.
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    extra = re.search(r'^crosscheck = \["mqt\.qcec>=(\d+)\.(\d+),<(\d+)\.(\d+)"\]$', text,
                      re.MULTILINE)
    assert extra is not None, "the crosscheck extra must be bounded on both sides"
    major, minor, upper_major, upper_minor = map(int, extra.groups())
    assert (upper_major, upper_minor) == (major, minor + 1)


def test_the_cross_check_tests_demand_the_engines_they_compare():
    """The markers are what makes ``SYMQ_TEST_REQUIRE=native,sat,qcec`` bite in that job."""
    text = (ROOT / "tests" / "test_qcec_crosscheck.py").read_text(encoding="utf-8")
    assert "pytestmark = [pytest.mark.qcec, pytest.mark.native, pytest.mark.sat]" in text


def test_the_test_job_runs_the_whole_suite(workflow):
    steps = " ".join(str(step.get("run", ""))
                     for step in workflow["jobs"]["test"]["steps"])
    assert "pytest" in steps


def test_one_job_regenerates_the_research_evidence(research):
    """Each research report runs once in CI and is published; QCEC runs where it is installed."""
    steps = research["jobs"]["research-evidence"]["steps"]
    commands = " ".join(str(step.get("run", "")) for step in steps)
    for module in ("rewrite_qualtran_hmr", "rewrite_kmb_context", "bilinear_kmb",
                   "gf24_tower_qualification",
                   "substitution_qualification"):
        assert f"benchmarks.{module}" in commands
    assert any("upload-artifact" in str(step.get("uses", "")) for step in steps)
    external = " ".join(str(step.get("run", "")) for step in research["jobs"]["external"]["steps"])
    assert "benchmarks.substitution_crosscheck" in external
    assert "--output-dir" in commands  # the Qualtran HMR cases go through the CLI


def test_the_comparative_campaign_is_requalified_on_every_commit(research):
    """13 cases / 35 cells once, and the four preregistered cases with 15 paired repetitions."""
    steps = research["jobs"]["external"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]

    def repetitions(run: str) -> str | None:
        tokens = run.split()
        if "benchmarks.comparative" not in tokens or "--repetitions" not in tokens:
            return None
        return tokens[tokens.index("--repetitions") + 1]

    coverage = [r for r in runs if repetitions(r) == "1"]
    paired = [r for r in runs if repetitions(r) == "15"]
    assert len(coverage) == 1 and len(paired) == 1
    for case in ("kmb-gf16-original-vs-tower", "borrowed-dirty-missing-uncompute",
                 "qualtran-m1-hmr-cleanup", "qualtran-m1-hmr-missing-correction"):
        assert f"--case {case}" in paired[0]
    assert sum("benchmarks.comparative_report" in r for r in runs) == 2
    upload = next(step for step in steps if "upload-artifact" in str(step.get("uses", "")))
    assert upload.get("if") == "always()"


def test_the_aggregate_check_needs_every_other_required_job(workflow):
    """Branch protection requires ``ci-ok`` alone, so it must depend on every job of ci.yml.

    A job left out of ``needs`` could fail while the required check stays green.
    """
    jobs = workflow["jobs"]
    gate = jobs["ci-ok"]
    assert set(gate["needs"]) == set(jobs) - {"ci-ok"}
    assert gate["if"] == "always()"  # otherwise a failed dependency skips the gate
    command = " ".join(str(step.get("run", "")) for step in gate["steps"])
    assert 'test "$result" = success' in command
    assert "needs.*.result" in str(gate["steps"])
    # A job or step that may fail without failing reports ``success``: the gate would not see it.
    for name in gate["needs"]:
        assert "continue-on-error" not in jobs[name], name
        assert all("continue-on-error" not in step for step in jobs[name]["steps"]), name


def test_superseded_runs_are_cancelled_for_pull_requests_only(workflow):
    """On main and release branches a cancelled run would leave the required check red."""
    concurrency = workflow["concurrency"]
    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
    assert "merge_group" in _triggers(workflow)
    # Not cancelling in progress is not enough: a waiting run is replaced by a newer one of the
    # same group. Outside pull requests the group is the commit, so no run waits behind another.
    assert concurrency["group"] == (
        "ci-${{ github.workflow }}-"
        "${{ github.event_name == 'pull_request' && github.ref || github.sha }}")


def test_the_required_workflow_also_runs_on_release_branches(workflow, research):
    assert "release/**" in _triggers(workflow)["push"]["branches"]
    assert "pull_request" in _triggers(workflow)
    # Research evidence still runs on every pull request (stacked ones included), but only main
    # is requalified on push: it is not a required check of a release branch.
    assert _triggers(research)["push"]["branches"] == ["main"]
    assert "pull_request" in _triggers(research)
    assert not _triggers(research)["pull_request"]
    assert not set(workflow["jobs"]) & set(research["jobs"])


def test_the_built_sdist_is_checked_before_the_suite_runs_inside_it(workflow):
    """The suite passing inside the sdist says nothing about a file that should not be there:
    with the unpublished corpus present, its tests simply run. The check on the tarball does."""
    job = workflow["jobs"]["wheel"]
    run = next(str(step["run"]) for step in job["steps"] if "build --sdist" in str(step.get("run")))
    lines = [line.strip() for line in run.splitlines()]
    build = lines.index("python -m build --sdist -o sdist .")
    assert lines[build + 1] == "python tools/release_check.py sdist sdist/*.tar.gz"
    test = workflow["jobs"]["test"]["env"]["SYMQ_TEST_REQUIRE"].split(",")
    assert "corpus_bilinear" in test  # and a checkout must really read that corpus


def test_the_coverage_job_enforces_a_floor_on_the_complete_measure(workflow):
    """The floor applies once, on the run that has every core test's contribution."""
    runs = [str(step.get("run", "")) for step in workflow["jobs"]["coverage"]["steps"]]
    measured = [run for run in runs if "--cov" in run.split()]
    assert [run for run in measured if "--cov-fail-under=" in run] == [measured[-1]]
    assert "--cov-append" in measured[-1].split()
    floor = int(measured[-1].split("--cov-fail-under=")[1].split()[0])
    assert 80 <= floor <= 100


def test_timing_tests_never_run_under_xdist_and_always_run_serially(workflow):
    """A parallel pytest run excludes ``timing``; the same job then runs those tests alone.

    Dropping the exclusion brings back load-dependent failures; dropping the serial step would
    silently stop running the real-time tests, which is worse.
    """
    for name, job in workflow["jobs"].items():
        commands = [line.strip() for step in job.get("steps", [])
                    for line in str(step.get("run", "")).splitlines() if "pytest" in line]
        parallel = [command for command in commands if "-n auto" in command]
        serial = [command for command in commands if "-n " not in command]
        for command in parallel:
            assert "not timing" in command, (name, command)
        if parallel:
            assert any(" -m timing" in command or '"timing and ' in command
                       or 'and timing"' in command for command in serial), (name, commands)


@pytest.mark.parametrize("path", ALL_WORKFLOWS, ids=lambda path: path.name)
def test_every_workflow_parses_and_restricts_its_token(path):
    document = yaml.safe_load(path.read_text())
    assert document.get("jobs"), f"{path.name} has no jobs"
    assert document.get("permissions") == {"contents": "read"}, path.name


@pytest.mark.parametrize("path", ALL_WORKFLOWS, ids=lambda path: path.name)
def test_every_action_is_pinned_to_a_full_commit_sha(path):
    """A tag such as ``@v4`` can be moved by its owner; a 40-hex commit cannot.

    The trailing ``# vX.Y.Z`` comment keeps the pin readable and lets Dependabot update it.
    """
    import re

    text = path.read_text()
    uses = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)(.*)$", text, flags=re.MULTILINE)
    jobs = yaml.safe_load(text)["jobs"].values()
    # Step-level actions and job-level reusable workflows: the text scan must miss none of them.
    assert len(uses) == sum("uses" in job for job in jobs) + sum(
        "uses" in step for job in jobs for step in job.get("steps", []))
    for reference, trailer in uses:
        if reference.startswith("./"):
            continue  # a workflow or action of this repository, at the checked-out commit
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", reference), (path.name, reference)
        assert re.fullmatch(r"\s+# v\d+(\.\d+){0,2}", trailer) or reference.startswith(
            "leanprover/"), (path.name, reference, trailer)
