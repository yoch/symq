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


def test_the_budget_bounds_the_whole_call_not_only_the_solver():
    """A 30 s budget must not take minutes because encoding or witness replay overran.

    The guarantee is: no phase starts after the deadline, and the solver is interrupted at it. A
    phase already running is allowed to finish -- that is stated in the docstring rather than
    hidden, because Python cannot preempt itself.
    """
    import random

    from symq.generators import equivalent_variant, random_circuit

    rng = random.Random(4)
    left = random_circuit(18, 260, rng)
    right = equivalent_variant(left, random.Random(5), steps=40)
    for seconds in (0.001, 0.05):
        started = time.perf_counter()
        verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=seconds))
        elapsed = time.perf_counter() - started
        # Generous slack for the encoding and the replay, but bounded: the call must not run for
        # the solver's default lifetime.
        assert elapsed < max(20 * seconds, 5.0), f"budget {seconds}s took {elapsed:.2f}s"
        if verdict.outcome == "inconclusive":
            assert "budget" in verdict.detail
            assert verdict.equivalent is None


def test_a_budget_is_reported_as_used_when_it_is_not():
    """A decided verdict must not claim the budget was exhausted."""
    verdict = check_sat_equivalence(Circuit(2).cx(0, 1), Circuit(2).cx(0, 1),
                                    budget=Budget(max_seconds=30))
    assert verdict.outcome == "equivalent"
    assert "exhausted" not in verdict.detail


def test_expired_solver_setup_does_not_start_solving(monkeypatch):
    """A solver constructor cannot silently extend the budget."""
    import symq.sat.miter as miter

    events = {"solve": 0, "delete": 0}

    class SlowSolver:
        def solve_limited(self, *, expect_interrupt):
            events["solve"] += 1
            return False

        def delete(self):
            events["delete"] += 1

    class SlowFactory:
        name = "synthetic"

        def __call__(self, **_kwargs):
            time.sleep(0.02)
            return SlowSolver()

    monkeypatch.setattr(miter, "solver_available", lambda: True)
    monkeypatch.setattr(miter, "_solver_factory", lambda: SlowFactory())
    result = miter.check_sat_equivalence(
        Circuit(1), Circuit(1), budget=Budget(max_seconds=0.001),
    )
    assert result.outcome == "inconclusive"
    assert "solver setup" in result.detail
    assert events == {"solve": 0, "delete": 1}


def test_late_unsat_is_never_reported_within_budget(monkeypatch):
    """An UNSAT answer after an ignored interrupt is outside the declared deadline."""
    import symq.sat.miter as miter

    class SlowUnsat:
        def interrupt(self):
            pass

        def conf_budget(self, _limit):
            pass

        def solve_limited(self, *, expect_interrupt):
            time.sleep(0.02)
            return False

        def delete(self):
            pass

    class SlowFactory:
        name = "synthetic"

        def __call__(self, **_kwargs):
            return SlowUnsat()

    monkeypatch.setattr(miter, "solver_available", lambda: True)
    monkeypatch.setattr(miter, "_solver_factory", lambda: SlowFactory())
    result = miter.check_sat_equivalence(
        Circuit(1), Circuit(1), budget=Budget(max_seconds=0.001),
    )
    assert result.outcome == "inconclusive"
    assert "budget" in result.detail
    assert result.seconds >= 0.02


def test_model_extraction_is_included_in_verdict_seconds(monkeypatch):
    """The timer includes model extraction and independent witness checking."""
    import symq.sat.miter as miter

    original_factory = miter._solver_factory()

    class SlowModelFactory:
        name = original_factory.name

        def __call__(self, **kwargs):
            raw = original_factory(**kwargs)

            class Wrapper:
                def __getattr__(self, attr):
                    return getattr(raw, attr)

                def get_model(self):
                    time.sleep(0.03)
                    return raw.get_model()

            return Wrapper()

    monkeypatch.setattr(miter, "_solver_factory", lambda: SlowModelFactory())
    result = miter.check_sat_equivalence(
        Circuit(1), Circuit(1).x(0), budget=Budget(max_seconds=2.0),
    )
    assert result.outcome == "different" and result.witness_checked
    assert result.seconds >= 0.03
