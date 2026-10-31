"""The SAT tests must actually run in CI, not be skipped.

The first submission of the SAT engine had 52 tests and a green CI, and none of them executed:
`python-sat` was not installed, so the whole module was skipped. A green tick that covers nothing
is worse than a red one.

SAT-dependent tests carry the ``sat`` marker. A run that is supposed to have the solver declares
``SYMQ_TEST_REQUIRE=sat`` (every CI job does); ``tests/conftest.py`` then turns any skip of a
``sat`` test into a usage error, and the check below fails loudly as well.
"""
from __future__ import annotations

import os

import pytest

from symq import sat


def _required() -> set[str]:
    return {part.strip() for part in os.environ.get("SYMQ_TEST_REQUIRE", "").split(",")}


def test_the_solver_is_available_where_the_suite_is_supposed_to_have_it():
    """A run declaring ``SYMQ_TEST_REQUIRE=sat`` must have an importable, interruptible solver."""
    if "sat" not in _required():
        pytest.skip("this run does not declare SYMQ_TEST_REQUIRE=sat")
    assert sat.available(), (
        "python-sat is missing although SYMQ_TEST_REQUIRE=sat: install it with "
        "'pip install -e .[sat]'.")


@pytest.mark.sat
def test_the_version_is_reported_for_attribution():
    versions = sat.versions()
    assert versions.get("python-sat")


@pytest.mark.sat
def test_a_verdict_carries_the_solver_name():
    from symq import Circuit

    verdict = sat.check_sat_equivalence(Circuit(2).cx(0, 1), Circuit(2).cx(0, 1))
    assert verdict.outcome == "equivalent"
    assert verdict.solver, "a verdict must name the solver that produced it"
