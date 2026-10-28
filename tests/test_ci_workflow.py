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

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def test_the_workflow_parses(workflow):
    assert "jobs" in workflow and workflow["jobs"], "the workflow has no jobs"


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


def test_the_test_job_runs_the_whole_suite(workflow):
    steps = " ".join(str(step.get("run", ""))
                     for step in workflow["jobs"]["test"]["steps"])
    assert "pytest" in steps
