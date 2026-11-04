"""The optional Qiskit pilot workflow is hardened like the main CI (#207 audit)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/qiskit-transpiler-pilot.yml"


def _workflow():
    document = yaml.safe_load(WORKFLOW.read_text())
    # PyYAML reads the bare key `on` as boolean True.
    return document, document.get("on", document.get(True))


def test_pilot_workflow_is_read_only_and_cancels_superseded_runs():
    document, _ = _workflow()
    assert document["permissions"] == {"contents": "read"}
    assert document["concurrency"]["cancel-in-progress"] is True


def test_pilot_workflow_triggers_on_any_symq_source_and_the_skip_policy():
    _, triggers = _workflow()
    paths = triggers["pull_request"]["paths"]
    assert "src/symq/**" in paths and "tests/conftest.py" in paths


def test_pilot_workflow_requires_sat_and_pins_qiskit():
    document, _ = _workflow()
    job = document["jobs"]["transpiler"]
    assert job["env"]["SYMQ_TEST_REQUIRE"] == "sat"
    assert "qiskit==2.6.1" in WORKFLOW.read_text()


def test_benchmark_children_have_a_per_trial_timeout():
    source = (ROOT / "benchmarks/qiskit_rewrite_benchmark.py").read_text()
    assert "timeout=120" in source
