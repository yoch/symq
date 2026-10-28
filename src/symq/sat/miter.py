"""Miter query: decide equivalence of two circuits with SAT, and check every witness concretely.

``check_sat_equivalence`` builds the Tseitin encoding of both circuits, ties their inputs together,
adds the clause "some observed output differs", and asks the solver. The three outcomes are
distinguished sharply, because a checker must never blur them:

* ``different`` -- the solver returned a model, and that model was replayed through ``Circuit.run``
  and really does differ on an observed output. If it does not, this raises
  :class:`~symq.equivalence.InternalInconsistency`: a model that is not a counterexample means the
  encoding is wrong, which is a bug, not a verdict.
* ``equivalent`` -- the solver proved the miter unsatisfiable. That is a claim relative to the
  encoding and the declared contract, which is what the caller asked for.
* ``inconclusive`` -- no solver, a timeout, a solver error, or a witness that fails its replay.
  Never an equivalence proof.

The solver is optional: without ``python-sat`` the module reports that it is unavailable and the
rest of SymQ is unaffected.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from symq.circuit import Circuit
from symq.equivalence import InternalInconsistency
from symq.resources import Budget

from .encoding import (
    Contract,
    Encoder,
    SatUnavailable,
    SatVerdict,
    _solver_factory,
    encode_circuit,
    solver_available,
)


class _Watchdog:
    """Interrupt a solver that outlives its wall-clock budget.

    ``pysat`` exposes ``interrupt()`` rather than a deadline, so the only honest way to enforce
    seconds is to call it from another thread. ``threading.Timer`` would work too; this keeps the
    fired-flag explicit so the caller can distinguish a real timeout from a solver that answered
    ``None`` for another reason.
    """

    def __init__(self, seconds: float, interrupt) -> None:
        self._seconds = float(seconds)
        self._interrupt = interrupt
        self._timer: threading.Timer | None = None
        self.fired = False

    def _fire(self) -> None:
        self.fired = True
        self._interrupt()

    def start(self) -> None:
        self._timer = threading.Timer(self._seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> bool:
        if self._timer is not None:
            self._timer.cancel()
            self._timer.join(timeout=1.0)
        return self.fired


@dataclass
class Miter:
    """A built miter: the clauses, the literals to satisfy, and the input variables."""

    encoder: Encoder
    difference: list[int]
    inputs: list[int]
    """``inputs[wire]`` is the variable holding the shared input value of that wire."""


def build_miter(left: Circuit, right: Circuit, contract: Contract | None = None) -> Miter:
    """Encode ``left`` and ``right`` with a shared input, ready for the "some output differs" clause."""
    contract = contract or Contract()
    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError("two Circuits are required")
    # The gate list is public and mutable, so the IR is validated here as well: an encoder that
    # reads `gate.qubits` without checking `gate.name` would silently treat an unknown operation
    # as a flip. Both circuits are validated before a single clause is emitted.
    left.validate()
    right.validate()
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    contract.validate(left.width)
    encoder = Encoder()
    left_steps = encode_circuit(encoder, left)
    right_steps = encode_circuit(encoder, right)
    initial_left, initial_right = left_steps.inputs, right_steps.inputs
    final_left, final_right = left_steps.outputs, right_steps.outputs

    for wire in range(left.width):
        encoder.equiv(initial_left[wire], initial_right[wire])
    for wire, value in sorted(contract.input_constants.items()):
        encoder.add(initial_left[wire] if value else -initial_left[wire])

    differences: list[int] = []
    for left_wire, right_wire in observed_pairs(contract, left.width):
        differences.append(encoder.xor_gate(final_left[left_wire], final_right[right_wire]))
    for wire in contract.restored_wires:
        for steps in (left_steps, right_steps):
            differences.append(encoder.xor_gate(steps.outputs[wire], steps.inputs[wire]))
    if not differences:
        raise ValueError("the contract observes nothing: there is nothing to check")
    return Miter(encoder, differences, list(initial_left))


def observed_pairs(contract: Contract, width: int) -> list[tuple[int, int]]:
    if contract.output_map:
        return sorted(contract.output_map.items())
    if contract.observed_outputs is not None:
        return [(wire, wire) for wire in contract.observed_outputs]
    return [(wire, wire) for wire in range(width)]


def check_sat_equivalence(left: Circuit, right: Circuit, contract: Contract | None = None,
                          budget: Budget | None = None) -> SatVerdict:
    """Decide ``left ~ right`` under ``contract`` with a SAT solver, checking any witness."""
    if not solver_available():
        raise SatUnavailable("no SAT solver installed: pip install python-sat")
    contract = contract or Contract()
    budget = budget or Budget()
    miter = build_miter(left, right, contract)
    encoder = miter.encoder
    encoder.add(*miter.difference) if len(miter.difference) > 1 else encoder.add(
        miter.difference[0])
    factory = _solver_factory()
    started = time.perf_counter()
    solver = factory(bootstrap_with=encoder.clauses)
    try:
        if budget.max_seconds is not None:
            # ``conf_budget`` counts *conflicts*, not seconds: turning seconds into a conflict
            # count is a guess, and a wrong one (the audit caught exactly this). The wall-clock
            # limit is enforced by a watchdog thread calling ``interrupt()``; the conflict budget
            # is kept only as a secondary bound so a pathological instance cannot spin forever
            # after the interrupt is raised.
            watchdog = _Watchdog(budget.max_seconds, solver.interrupt)
            watchdog.start()
            try:
                solver.conf_budget(max(1, int(budget.max_seconds * 10_000)))
                answer = solver.solve_limited()
            finally:
                fired = watchdog.stop()
            timed_out = answer is None
            out_of_time = fired
        else:
            answer = solver.solve()
            timed_out = False
            out_of_time = False
        elapsed = time.perf_counter() - started
        if timed_out:
            detail = ("wall-clock budget exhausted" if out_of_time
                      else "solver returned no answer within its conflict budget")
            return SatVerdict("inconclusive", seconds=elapsed, clauses=len(encoder.clauses),
                              variables=encoder.next_variable - 1, detail=detail,
                              solver=factory.__name__)
        if answer is False:
            return SatVerdict("equivalent", seconds=elapsed, clauses=len(encoder.clauses),
                              variables=encoder.next_variable - 1, solver=factory.__name__)
        return _checked_model(left, right, contract, solver.get_model(), elapsed, encoder,
                              factory)
    finally:
        solver.delete()


def _checked_model(left: Circuit, right: Circuit, contract: Contract, model, elapsed: float,
                   encoder: Encoder, factory) -> SatVerdict:
    positive = {literal for literal in model if literal > 0}
    miter = build_miter(left, right, contract)
    value = 0
    for wire, variable in enumerate(miter.inputs):
        if variable in positive:
            value |= 1 << wire
    left_out, right_out = left.run(value), right.run(value)
    differing = next((left_wire for left_wire, right_wire in observed_pairs(contract, left.width)
                      if ((left_out >> left_wire) & 1) != ((right_out >> right_wire) & 1)), None)
    if differing is None:
        for wire in contract.restored_wires:
            initial = (value >> wire) & 1
            if ((left_out >> wire) & 1) != initial or ((right_out >> wire) & 1) != initial:
                differing = wire
                break
    if differing is None:
        raise InternalInconsistency(
            "the SAT solver returned a model that is not a counterexample; the encoding is wrong")
    for wire, expected in contract.input_constants.items():
        if ((value >> wire) & 1) != expected:
            raise InternalInconsistency("a witness violates the input contract")
    return SatVerdict("different", witness=value, witness_checked=True,
                      first_differing_output=differing, seconds=elapsed,
                      clauses=len(encoder.clauses), variables=encoder.next_variable - 1,
                      solver=factory.__name__)
