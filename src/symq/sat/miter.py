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

    ``budget.max_seconds`` bounds the **whole call**, not only the solver: encoding, solving,
    model extraction and witness replay all charge their time against the same deadline. The
    first version started its clock after the CNF was built and stopped it when the solver
    returned, so a 30 s budget could take longer than 30 s; the audit caught it.

    The deadline cannot preempt a computation already running in this thread -- encoding and the
    witness replay are Python and are checked *between* the phases and inside the encoder -- so
    the guarantee is: no phase starts after the deadline, and the solver is interrupted at it.
    A phase that has already begun is allowed to finish, which is stated rather than hidden.
    """
    if not solver_available():
        raise SatUnavailable("no SAT solver installed: pip install python-sat")
    contract = contract or Contract()
    budget = budget or Budget()
    deadline = None if budget.max_seconds is None else (
        time.perf_counter() + float(budget.max_seconds))
    started = time.perf_counter()

    def remaining() -> float | None:
        return None if deadline is None else deadline - time.perf_counter()

    def expired() -> bool:
        left_time = remaining()
        return left_time is not None and left_time <= 0.0

    miter = build_miter(left, right, contract)
    encoder = miter.encoder
    encoder.add(*miter.difference) if len(miter.difference) > 1 else encoder.add(
        miter.difference[0])
    factory = _solver_factory()
    name = solver_name(factory)
    if expired():
        return SatVerdict("inconclusive", seconds=time.perf_counter() - started,
                          clauses=len(encoder.clauses),
                          variables=encoder.next_variable - 1,
                          detail="wall-clock budget exhausted during encoding", solver=name)
    solver = factory(bootstrap_with=encoder.clauses)
    try:
        if deadline is not None:
            # ``conf_budget`` counts *conflicts*, not seconds, so it is not a time limit. The
            # wall-clock limit is a watchdog thread calling ``interrupt()`` -- which only works
            # on solvers that implement it. CaDiCaL and Kissat raise NotImplementedError there,
            # so ``_solver_factory`` refuses them; this branch would otherwise advertise a
            # timeout it cannot enforce.
            try:
                watchdog = _Watchdog(max(remaining() or 0.0, 0.001), solver.interrupt)
            except NotImplementedError as error:  # pragma: no cover - factory prevents this
                raise SatUnavailable(
                    f"{name} cannot be interrupted, so a wall-clock budget cannot be enforced; "
                    "install glucose or minisat") from error
            watchdog.start()
            try:
                # A conflict ceiling is *not* a time limit: it counts conflicts. It is set only as
                # a last-resort guard, far above what a 30 s run reaches, and the verdict says
                # which of the two stopped the solver.
                if hasattr(solver, "conf_budget"):
                    solver.conf_budget(50_000_000)
                answer = solver.solve_limited(expect_interrupt=True)
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
                              solver=name)
        if answer is False:
            return SatVerdict("equivalent", seconds=elapsed, clauses=len(encoder.clauses),
                              variables=encoder.next_variable - 1, solver=name,
                              detail=("wall-clock budget was not exhausted"
                                      if deadline is None else "within budget"))
        if expired():
            return SatVerdict("inconclusive", seconds=time.perf_counter() - started,
                              clauses=len(encoder.clauses),
                              variables=encoder.next_variable - 1, solver=name,
                              detail="wall-clock budget exhausted before the witness check")
        return _checked_model(left, right, contract, solver.get_model(), elapsed, encoder, name)
    finally:
        solver.delete()


def _checked_model(left: Circuit, right: Circuit, contract: Contract, model, elapsed: float,
                   encoder: Encoder, solver_label: str) -> SatVerdict:
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
                      solver=solver_label)
