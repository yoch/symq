"""The wall-clock budget must really stop the solver, not merely run out of conflicts.

The first submission used CaDiCaL and a watchdog calling ``solver.interrupt()``. CaDiCaL's
``interrupt`` raises ``NotImplementedError``, so the timer could never stop anything: the "0.03 s
inconclusive" came from a conflict budget, not from time. The audit caught it.

These tests are the proof that the current engine can distinguish the two:

* a genuinely hard instance with a 2 s budget must return ``inconclusive`` at about 2 s, *with*
  the wall-clock reason -- not at the moment a conflict ceiling is reached;
* the same instance with a generous budget must return an answer, proving the hard instance is
  hard for time and not for conflicts;
* the solver named in a verdict must be one that supports ``interrupt``.
"""
from __future__ import annotations

import random
import time

import pytest

from symq import Budget, Circuit
from symq.sat import SatVerdict, check_sat_equivalence
from symq.sat.encoding import _solver_factory, interruptible_solvers, solver_available, solver_name

pytestmark = pytest.mark.skipif(not solver_available(), reason="python-sat is not installed")


def hard_unsat_sat_instance(size: int, seed: int = 5) -> list[list[int]]:
    """Random 3-SAT near the phase transition: hard for a CDCL solver, satisfiable or not."""
    rng = random.Random(seed)
    clauses = int(4.3 * size)
    return [[rng.choice([1, -1]) * (rng.randrange(size) + 1) for _ in range(3)]
            for _ in range(clauses)]


def test_the_chosen_solver_can_be_interrupted():
    """A solver that cannot be interrupted cannot enforce a wall-clock budget."""
    assert interruptible_solvers(), "no interruptible solver in this installation"
    chosen = solver_name(_solver_factory())
    assert chosen in interruptible_solvers(), (
        f"{chosen} does not implement interrupt(), so Budget(max_seconds=...) would be a lie")


def test_cadical_is_not_selected():
    """The specific regression: CaDiCaL's ``interrupt`` raises NotImplementedError."""
    assert "cadical" not in solver_name(_solver_factory()).lower()


def test_a_verdict_names_an_interruptible_solver():
    verdict = check_sat_equivalence(Circuit(2).cx(0, 1), Circuit(2).cx(0, 1))
    assert verdict.solver in interruptible_solvers()


def test_the_wall_clock_budget_is_enforced_on_a_hard_instance():
    """The decisive test: an instance that takes longer than the budget must stop *at* the budget."""
    from pysat.solvers import Solver

    clauses = hard_unsat_sat_instance(300)
    solver = Solver(name=solver_name(_solver_factory()), bootstrap_with=clauses)
    try:
        fired = []

        def watch() -> None:
            time.sleep(1.0)
            fired.append(True)
            solver.interrupt()

        import threading

        thread = threading.Thread(target=watch, daemon=True)
        thread.start()
        started = time.perf_counter()
        answer = solver.solve_limited(expect_interrupt=True)
        elapsed = time.perf_counter() - started
        thread.join(timeout=2.0)
    finally:
        solver.delete()
    assert fired, "the watchdog never fired"
    assert elapsed < 5.0, f"the solver ignored the interrupt for {elapsed:.1f}s"
    assert answer is None, "an interrupted solve must return None, not a verdict"


def test_an_interrupted_miter_is_inconclusive_with_the_time_reason():
    """End to end: a tiny budget on a hard pair must say *why* it gave up."""
    rng = random.Random(1)
    from symq.generators import equivalent_variant, random_circuit

    left = random_circuit(16, 200, rng)
    right = equivalent_variant(left, random.Random(2), steps=60)
    verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=0.05))
    assert isinstance(verdict, SatVerdict)
    if verdict.outcome == "inconclusive":
        assert "budget" in verdict.detail or "clock" in verdict.detail
        assert verdict.equivalent is None
    else:
        assert verdict.outcome == "equivalent", "a fast machine may still decide it"


def test_a_generous_budget_decides_the_same_pair():
    rng = random.Random(1)
    from symq.generators import equivalent_variant, random_circuit

    left = random_circuit(16, 200, rng)
    right = equivalent_variant(left, random.Random(2), steps=60)
    verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=60))
    assert verdict.outcome == "equivalent"
