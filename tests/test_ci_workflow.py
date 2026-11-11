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

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
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
    import subprocess

    broken = []
    for document in (workflow, research):
        for name, job in document["jobs"].items():
            for step in job.get("steps", []):
                command = step.get("run")
                if not command:
                    continue
                result = subprocess.run(["bash", "-n"], input=command, text=True,
                                        capture_output=True, check=False)
                if result.returncode != 0:
                    broken.append((name, command.splitlines()[0][:60], result.stderr.strip()))
    assert not broken, f"invalid shell in {broken}"


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


def test_the_required_workflow_also_runs_on_release_branches(workflow, research):
    assert "release/**" in _triggers(workflow)["push"]["branches"]
    assert "pull_request" in _triggers(workflow)
    # Research evidence still runs on every pull request (stacked ones included), but only main
    # is requalified on push: it is not a required check of a release branch.
    assert _triggers(research)["push"]["branches"] == ["main"]
    assert "pull_request" in _triggers(research)
    assert not _triggers(research)["pull_request"]
    assert not set(workflow["jobs"]) & set(research["jobs"])


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
