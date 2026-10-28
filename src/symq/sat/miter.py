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
* ``inconclusive`` -- a timeout, a conflict ceiling, or unknown solver response.
  Never an equivalence proof. Unavailability raises SatUnavailable, and invalid witnesses
  raise InternalInconsistency instead of being silently accepted.

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
    solver_name,
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
    """Decide ``left ~ right`` under ``contract`` with a SAT solver, checking any witness.

    Encoding, solving and witness replay all share one entry-time deadline; see
    :func:`drive_solver` for the exact guarantee.
    """
    if not solver_available():
        raise SatUnavailable("no SAT solver installed: pip install python-sat")
    contract = contract or Contract()
    miter = build_miter(left, right, contract)
    encoder = miter.encoder
    encoder.add(*miter.difference)
    return drive_solver(left, right, contract, _DrivenMiter(miter, encoder), budget)


class _DrivenMiter:
    """A built miter in the shape :func:`drive_solver` expects."""

    def __init__(self, miter, encoder) -> None:
        self.inputs = list(miter.inputs)
        self.clauses = encoder.clauses
        self._encoder = encoder

    def variable_count(self) -> int:
        return self._encoder.next_variable - 1


def drive_solver(left: Circuit, right: Circuit, contract: Contract, miter,
                 budget: Budget | None) -> SatVerdict:
    """Run the solver over an already-built miter with a cooperative whole-call deadline.

    ``miter`` must expose ``clauses``, ``inputs`` and ``variable_count()``. Both encoders go
    through this single driver, so the budget discipline cannot drift between them: the deadline is
    taken at entry, checked after the encoding and after solver setup, the solver is interrupted at
    the deadline, and model extraction, witness replay and cleanup all charge their time to it.

    The deadline is cooperative, not a hard preemption: a Python phase already running finishes,
    and the verdict says which phase exhausted the budget.
    """
    budget = budget if budget is not None else Budget()
    started = time.perf_counter()
    deadline = None if budget.max_seconds is None else started + budget.max_seconds

    def expired() -> bool:
        return deadline is not None and time.perf_counter() >= deadline

    factory = _solver_factory()
    name = solver_name(factory)

    def verdict(outcome: str, detail: str = "") -> SatVerdict:
        return SatVerdict(outcome, clauses=len(miter.clauses),
                          variables=miter.variable_count(), detail=detail, solver=name)

    if expired():
        result = verdict("inconclusive", "wall-clock budget exhausted during encoding")
        result.seconds = time.perf_counter() - started
        return result

    solver = factory(bootstrap_with=miter.clauses)
    answer = None
    result = verdict("inconclusive", "not yet classified")
    try:
        if expired():
            result = verdict("inconclusive", "wall-clock budget exhausted during solver setup")
        elif deadline is not None:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                result = verdict("inconclusive", "wall-clock budget exhausted before solving")
            else:
                watchdog = _Watchdog(remaining, solver.interrupt)
                watchdog.start()
                try:
                    if hasattr(solver, "conf_budget"):
                        solver.conf_budget(50_000_000)
                    answer = solver.solve_limited(expect_interrupt=True)
                finally:
                    fired = watchdog.stop()
                if answer is None:
                    reason = ("wall-clock budget exhausted" if fired or expired()
                              else "solver returned no answer within its conflict budget")
                    result = verdict("inconclusive", reason)
        else:
            answer = solver.solve()

        if result.detail == "not yet classified":
            if expired():
                result = verdict("inconclusive", "wall-clock budget exhausted after solving")
            elif answer is False:
                result = verdict("equivalent", "within budget")
            elif answer is True:
                model = solver.get_model()
                if expired():
                    result = verdict("inconclusive",
                                     "wall-clock budget exhausted during model extraction")
                else:
                    result = _checked_model(left, right, contract, model, miter.inputs,
                                            miter, name)
                    if expired():
                        result = verdict("inconclusive",
                                         "wall-clock budget exhausted during witness replay")
            else:
                result = verdict("inconclusive", "unexpected SAT solver response")
    finally:
        solver.delete()
    if expired() and result.outcome != "inconclusive":
        result = verdict("inconclusive", "wall-clock budget exhausted during solver cleanup")
    result.seconds = time.perf_counter() - started
    return result


def _checked_model(left: Circuit, right: Circuit, contract: Contract, model,
                   input_variables: list[int], encoder: Encoder, solver_label: str) -> SatVerdict:
    """Check the model against the original miter's input variables, without re-encoding."""
    if model is None:
        raise InternalInconsistency("SAT returned a model-free satisfiable result")
    positive = {literal for literal in model if literal > 0}
    value = 0
    for wire, variable in enumerate(input_variables):
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
                      first_differing_output=differing,
                      clauses=len(encoder.clauses), variables=encoder.variable_count(),
                      solver=solver_label)
