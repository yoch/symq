"""The SAT deadline is polled while the miter is encoded and loaded, not only around those phases.

Before this, ``check_sat_equivalence`` compared the clock with the deadline before and after
``build_miter``: a large instance was encoded in full, and its clauses handed to the solver in one
call, before an already expired budget was noticed (issue #193 measured 0.95 s and 175 MB for a
0.05 s budget). The encoding now polls every 64 gates and the clauses are loaded in chunks.

These tests are deterministic: the clock is a variable advanced by the code under test (a counted
encoder call, a fake solver), never the wall clock. They state the properties that matter:

* an expired deadline is never answered with ``equivalent`` or ``different``;
* at most 64 gates are encoded after the deadline;
* invalid inputs raise whatever the budget;
* without a deadline nothing changes: same clauses, same variables, one solver construction.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from symq import Budget, Circuit
from symq.sat import Contract, build_miter, check_sat_equivalence
from symq.sat import miter as miter_module
from symq.sat.encoding import Encoder

POLL_INTERVAL = 64
"""Gates between two polls in ``symq.sat.encoding._poll_gates``."""


class RecordingSolver:
    """A stand-in solver that records what it is given and answers UNSAT."""

    def __init__(self, events: dict, bootstrap_with) -> None:
        self.events = events
        events["bootstrap"] = [list(clause) for clause in bootstrap_with]
        events["create"] += 1

    def append_formula(self, formula, no_return=True) -> None:
        assert no_return is True
        self.events["appended"].append([list(clause) for clause in formula])
        self.events["after_append"](self.events)

    def interrupt(self) -> None:
        self.events["interrupt"] += 1

    def conf_budget(self, _limit) -> None:
        pass

    def solve(self):
        self.events["solve"] += 1
        return False

    def solve_limited(self, *, expect_interrupt):
        self.events["solve"] += 1
        return False

    def delete(self) -> None:
        self.events["delete"] += 1


def install_fake_solver(monkeypatch) -> dict:
    events = {"create": 0, "solve": 0, "delete": 0, "interrupt": 0, "appended": [],
              "bootstrap": None, "after_append": lambda _events: None}

    class Factory:
        name = "synthetic"

        def __call__(self, *, bootstrap_with):
            return RecordingSolver(events, bootstrap_with)

    monkeypatch.setattr(miter_module, "solver_available", lambda: True)
    monkeypatch.setattr(miter_module, "_solver_factory", lambda: Factory())
    return events


def install_clock(monkeypatch) -> list[float]:
    now = [0.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    return now


def chain(gates: int, width: int = 4) -> Circuit:
    circuit = Circuit(width)
    for index in range(gates):
        circuit.ccx(index % width, (index + 1) % width, (index + 2) % width)
    return circuit


def count_encoded_gates(monkeypatch, on_gate) -> list[int]:
    """Count gates as they are encoded: ``encode_circuit`` calls ``xor_gate`` once per gate."""
    encoded = [0]
    original = Encoder.xor_gate

    def counted(self, left, right):
        encoded[0] += 1
        on_gate(encoded[0])
        return original(self, left, right)

    monkeypatch.setattr(Encoder, "xor_gate", counted)
    return encoded


def test_a_deadline_already_passed_stops_before_the_first_gate(monkeypatch):
    events = install_fake_solver(monkeypatch)
    now = install_clock(monkeypatch)
    encoded = count_encoded_gates(monkeypatch, lambda _count: None)
    # The guard is created inside the call, at time 0, so its deadline is 1; validating the
    # inputs takes the clock to 2, and the first poll of the encoding must notice it.
    validate = miter_module._validate_miter_inputs

    def validate_then_expire(*arguments):
        validate(*arguments)
        now[0] = 2.0

    monkeypatch.setattr(miter_module, "_validate_miter_inputs", validate_then_expire)
    verdict = check_sat_equivalence(chain(500), chain(500), budget=Budget(max_seconds=1.0))
    assert verdict.outcome == "inconclusive"
    assert verdict.equivalent is None
    assert verdict.detail == "wall-clock budget exhausted during encoding"
    assert encoded == [0]
    assert verdict.clauses == 0 and verdict.variables == 4  # only the shared inputs exist
    assert verdict.seconds == 2.0
    assert events["create"] == 0 and events["solve"] == 0


@pytest.mark.parametrize("expire_after", [1, 63, 64, 65, 300, 999])
def test_at_most_one_poll_interval_is_encoded_after_the_deadline(monkeypatch, expire_after):
    events = install_fake_solver(monkeypatch)
    now = install_clock(monkeypatch)

    def on_gate(count: int) -> None:
        if count == expire_after:
            now[0] = 5.0

    encoded = count_encoded_gates(monkeypatch, on_gate)
    verdict = check_sat_equivalence(chain(1000), chain(1000), budget=Budget(max_seconds=1.0))
    assert verdict.outcome == "inconclusive"
    assert verdict.detail == "wall-clock budget exhausted during encoding"
    assert expire_after <= encoded[0] <= expire_after + POLL_INTERVAL
    assert encoded[0] < 2000  # two circuits of 1000 gates were never encoded in full
    assert events["create"] == 0 and events["solve"] == 0
    # The reported size is that of the partial encoding, not zero and not the full instance.
    assert 0 < verdict.clauses and verdict.variables > 4


def test_a_deadline_passing_on_the_last_gate_is_still_noticed(monkeypatch):
    """The poll after the last gate of each circuit covers a gate count below the interval."""
    events = install_fake_solver(monkeypatch)
    now = install_clock(monkeypatch)

    def on_gate(count: int) -> None:
        if count == 10:  # the last gate of the left circuit
            now[0] = 5.0

    encoded = count_encoded_gates(monkeypatch, on_gate)
    verdict = check_sat_equivalence(chain(10), chain(10), budget=Budget(max_seconds=1.0))
    assert verdict.outcome == "inconclusive"
    assert "during encoding" in verdict.detail
    assert encoded == [10]  # the right circuit was not started
    assert events["create"] == 0


@pytest.mark.parametrize("budget", [None, Budget(), Budget(max_terms=5)])
def test_without_a_deadline_the_encoding_and_setup_are_unchanged(monkeypatch, budget):
    events = install_fake_solver(monkeypatch)
    monkeypatch.setattr(miter_module, "_CLAUSE_CHUNK", 8)  # must not matter without a deadline
    polls = []
    monkeypatch.setattr(miter_module, "_encode_miter", _spy(miter_module._encode_miter, polls))
    left, right = chain(200), chain(200, width=4).cx(0, 1).cx(0, 1)
    contract = Contract(observed_outputs=(0, 1, 2))

    verdict = check_sat_equivalence(left, right, contract, budget=budget)
    assert polls == [None]  # no checkpoint was installed

    reference = build_miter(left, right, contract)
    reference.encoder.add(*reference.difference)
    assert events["bootstrap"] == reference.encoder.clauses
    assert events["appended"] == []
    assert events["create"] == 1 and events["solve"] == 1 and events["delete"] == 1
    assert verdict.outcome == "equivalent"
    assert (verdict.clauses, verdict.variables) == (
        len(reference.encoder.clauses), reference.encoder.next_variable - 1)


def _spy(function, calls: list):
    def wrapper(left, right, contract, encoder, checkpoint):
        calls.append(checkpoint)
        return function(left, right, contract, encoder, checkpoint)

    return wrapper


def test_a_deadline_does_not_change_the_clauses_only_how_they_are_loaded(monkeypatch):
    events = install_fake_solver(monkeypatch)
    install_clock(monkeypatch)  # frozen at 0: the deadline never passes
    monkeypatch.setattr(miter_module, "_CLAUSE_CHUNK", 8)
    left, right = chain(40), chain(40).x(3).x(3)

    verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=1.0))

    reference = build_miter(left, right)
    reference.encoder.add(*reference.difference)
    expected = reference.encoder.clauses
    assert len(expected) > 8
    loaded = events["bootstrap"] + [clause for chunk in events["appended"] for clause in chunk]
    assert loaded == expected  # same clauses, same order, none lost or duplicated
    assert len(events["bootstrap"]) == 8
    assert all(len(chunk) <= 8 for chunk in events["appended"])
    assert verdict.outcome == "equivalent" and verdict.clauses == len(expected)


def test_a_small_instance_is_loaded_in_one_call_even_with_a_deadline(monkeypatch):
    events = install_fake_solver(monkeypatch)
    install_clock(monkeypatch)
    verdict = check_sat_equivalence(chain(40), chain(40), budget=Budget(max_seconds=1.0))
    assert verdict.clauses < miter_module._CLAUSE_CHUNK
    assert len(events["bootstrap"]) == verdict.clauses and events["appended"] == []
    assert verdict.outcome == "equivalent"


def test_a_deadline_passing_while_clauses_are_loaded_stops_the_loading(monkeypatch):
    events = install_fake_solver(monkeypatch)
    now = install_clock(monkeypatch)
    monkeypatch.setattr(miter_module, "_CLAUSE_CHUNK", 8)

    def expire_after_two_chunks(recorded: dict) -> None:
        if len(recorded["appended"]) == 2:
            now[0] = 5.0

    events["after_append"] = expire_after_two_chunks
    verdict = check_sat_equivalence(chain(40), chain(40).x(3), budget=Budget(max_seconds=1.0))
    assert verdict.outcome == "inconclusive"
    assert verdict.equivalent is None
    assert verdict.detail == "wall-clock budget exhausted during solver setup"
    assert len(events["appended"]) == 2  # no chunk was handed over after the deadline
    assert events["solve"] == 0 and events["delete"] == 1
    assert verdict.clauses > 8 * 3  # the size of the full encoding is still reported


def test_a_partially_loaded_solver_is_never_asked_even_if_the_clock_goes_back(monkeypatch):
    """Solving is authorized by the count of loaded clauses, not by a second clock reading."""
    events = install_fake_solver(monkeypatch)
    now = install_clock(monkeypatch)
    monkeypatch.setattr(miter_module, "_CLAUSE_CHUNK", 8)
    readings = iter([5.0, 0.0])  # expired when the loading loop looks, "not expired" afterwards

    def flicker(recorded: dict) -> None:
        if len(recorded["appended"]) == 1:
            monkeypatch.setattr(time, "perf_counter", lambda: next(readings, 0.0))

    events["after_append"] = flicker
    verdict = check_sat_equivalence(chain(40), chain(40).x(3), budget=Budget(max_seconds=1.0))
    assert now == [0.0]
    assert len(events["appended"]) == 1
    assert verdict.outcome == "inconclusive"
    assert "solver setup" in verdict.detail
    assert events["solve"] == 0 and events["delete"] == 1


@pytest.mark.parametrize("left, right, contract, error", [
    ("not a circuit", Circuit(2), None, TypeError),
    (Circuit(2), Circuit(3), None, ValueError),
    (Circuit(2), Circuit(2), Contract(observed_outputs=(5,)), ValueError),
])
def test_invalid_inputs_raise_whatever_the_budget(monkeypatch, left, right, contract, error):
    """Validation completes before the first poll: its outcome cannot depend on timing."""
    events = install_fake_solver(monkeypatch)
    now = install_clock(monkeypatch)
    budget = Budget(absolute_deadline=-1.0)  # already passed when the call starts
    assert now[0] > -1.0
    with pytest.raises(error):
        check_sat_equivalence(left, right, contract, budget=budget)
    assert events["create"] == 0


def test_an_invalid_gate_raises_even_with_an_expired_budget(monkeypatch):
    install_fake_solver(monkeypatch)
    install_clock(monkeypatch)
    broken = Circuit(2).cx(0, 1)
    # ``Gate`` refuses an unknown name, but the gate list itself is public and mutable.
    broken.gates.append(SimpleNamespace(name="z", qubits=(0,)))
    with pytest.raises((TypeError, ValueError)):
        check_sat_equivalence(broken, Circuit(2), budget=Budget(absolute_deadline=-1.0))


def test_the_public_build_miter_keeps_its_entry_and_gate_polls():
    """``build_miter(checkpoint=...)`` is used by research code with its own refusal rules."""
    calls = []
    built = build_miter(chain(130), chain(130), checkpoint=lambda: calls.append(1))
    # Entry, after validation, then per circuit: gates 0, 64, 128 and the final poll.
    assert len(calls) == 2 + 2 * 4
    plain = build_miter(chain(130), chain(130))
    assert built.encoder.clauses == plain.encoder.clauses
    assert built.difference == plain.difference and built.inputs == plain.inputs

    def refuse():
        raise RuntimeError("refused on entry")

    with pytest.raises(RuntimeError, match="refused on entry"):
        build_miter("not a circuit", Circuit(1), checkpoint=refuse)


@pytest.mark.sat
@pytest.mark.parametrize("mutated", [False, True])
def test_chunked_loading_gives_the_same_verdict_with_a_real_solver(monkeypatch, mutated):
    monkeypatch.setattr(miter_module, "_CLAUSE_CHUNK", 16)
    left = chain(120, width=6)
    right = chain(120, width=6)
    if mutated:
        right.cx(0, 5)
    unbounded = check_sat_equivalence(left, right)
    bounded = check_sat_equivalence(left, right, budget=Budget(max_seconds=60))
    assert unbounded.clauses == bounded.clauses > 16 * 4
    assert unbounded.variables == bounded.variables
    assert bounded.outcome == unbounded.outcome == ("different" if mutated else "equivalent")
    if mutated:
        assert bounded.witness_checked is True
        assert left.run(bounded.witness) != right.run(bounded.witness)
