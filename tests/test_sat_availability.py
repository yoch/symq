"""The SAT tests must actually run in CI, not be skipped.

The first submission of the SAT engine had 52 tests and a green CI, and none of them executed:
`python-sat` was not installed, so the whole module was skipped. A green tick that covers nothing
is worse than a red one, so this file fails loudly when the solver is missing in an environment
that is supposed to have it.

It is deliberately *not* skipped: if the dependency disappears, this test is the alarm.
"""
from __future__ import annotations

import os

import pytest

import symq.sat as sat


def test_the_solver_is_available_where_the_suite_is_supposed_to_have_it():
    """CI installs ``python-sat`` through the ``dev`` extra; a silent skip would hide a gap."""
    if os.environ.get("SYMQ_ALLOW_MISSING_SAT") == "1":
        pytest.skip("this environment declares that the SAT solver is intentionally absent")
    assert sat.available(), (
        "python-sat is missing: the SAT engine's tests are being skipped, which is exactly the "
        "failure this test exists to prevent. Install it with 'pip install -e .[sat]'.")


@pytest.mark.skipif(not sat.available(), reason="python-sat is not installed")
def test_the_version_is_reported_for_attribution():
    versions = sat.versions()
    assert "python-sat" in versions and versions["python-sat"]


@pytest.mark.skipif(not sat.available(), reason="python-sat is not installed")
def test_a_verdict_carries_the_solver_name():
    from symq import Circuit

    verdict = sat.check_sat_equivalence(Circuit(2).cx(0, 1), Circuit(2).cx(0, 1))
    assert verdict.outcome == "equivalent"
    assert verdict.solver, "a verdict must name the solver that produced it"
