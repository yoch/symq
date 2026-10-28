"""Miter over affine forms: same three verdicts, same witness obligations, different encoding.

``check_xag_equivalence`` is a drop-in alternative to ``check_sat_equivalence`` for callers that
want the affine encoding. It shares the ``Contract``, the solver choice, the wall-clock budget and
the witness replay, so a verdict from one encoder can be compared with the other term for term.

The difference is only in how the circuits reach the solver:

* the transition encoder (``miter.py``) allocates a variable per (wire, step);
* this one allocates a variable per input, plus one per nonlinearity, and represents every wire as
  an XOR of those.

Equivalence remains UNSAT-relative-to-the-encoding, and ``inconclusive`` never becomes
``equivalent``.
"""
from __future__ import annotations

import time

from symq.circuit import Circuit
from symq.equivalence import InternalInconsistency
from symq.resources import Budget

from .encoding import Contract, SatUnavailable, SatVerdict, _solver_factory, solver_available
from .encoding_xag import XagCircuit, XagEncoder, build_xag
from .miter import _Watchdog, observed_pairs, solver_name


def build_xag_miter(left: Circuit, right: Circuit, contract: Contract | None = None
                    ) -> tuple[XagEncoder, list[int], XagCircuit, XagCircuit]:
    """Encode both circuits affinely and return the encoder, the difference literals and models."""
    contract = contract or Contract()
    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError("two Circuits are required")
    left.validate()
    right.validate()
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    contract.validate(left.width)
    # Each model gets its own variable range; the two are then tied only through ``ties`` below.
    left_model = build_xag(left, reserved=0)
    right_model = build_xag(right, reserved=left_model.variables)
    # The models own variables 1..width for inputs and then one per AND; the encoder must start
    # after the larger of the two models so no variable is shared by two meanings.
    reserved = max(left_model.variables, right_model.variables)
    encoder = XagEncoder(reserved=reserved)

    # The two models have disjoint variable ranges, so the shared input assignment is imposed by
    # explicit equivalences rather than by reusing numbers.
    for wire in range(left.width):
        first, second = left_model.inputs[wire], right_model.inputs[wire]
        encoder.add(-first, second)
        encoder.add(first, -second)
    for wire, value in sorted(contract.input_constants.items()):
        encoder.add(left_model.inputs[wire] if value else -left_model.inputs[wire])

    differences: list[int] = []
    for left_wire, right_wire in observed_pairs(contract, left.width):
        first = encoder.literal(left_model.wires[left_wire], left_model)
        second = encoder.literal(right_model.wires[right_wire], right_model)
        differences.append(encoder.xor_literal(first, second))
    for wire in contract.restored_wires:
        for model in (left_model, right_model):
            final = encoder.literal(model.wires[wire], model)
            # The wire must return to its own input value on each side.
            differences.append(encoder.xor_literal(final, model.inputs[wire]))
    if not differences:
        raise ValueError("the contract observes nothing: there is nothing to check")
    return encoder, differences, left_model, right_model


def check_xag_equivalence(left: Circuit, right: Circuit, contract: Contract | None = None,
                          budget: Budget | None = None) -> SatVerdict:
    """Decide ``left ~ right`` with the affine encoding; same contract and verdicts as the SSA one."""
    if not solver_available():
        raise SatUnavailable("no SAT solver installed: pip install python-sat")
    started = time.perf_counter()
    encoder, differences, _, _ = build_xag_miter(left, right, contract)
    encoding_seconds = time.perf_counter() - started
    encoder.add(*differences) if len(differences) > 1 else encoder.add(differences[0])
    factory = _solver_factory()
    name = solver_name(factory)
    deadline = None if budget is None or budget.max_seconds is None else (
        started + float(budget.max_seconds))
    solver = factory(bootstrap_with=encoder.clauses)
    try:
        if deadline is None:
            answer = solver.solve()
            timed_out = False
            fired = False
        else:
            remaining = max(deadline - time.perf_counter(), 0.001)
            watchdog = _Watchdog(remaining, solver.interrupt)
            watchdog.start()
            try:
                answer = solver.solve_limited(expect_interrupt=True)
            finally:
                fired = watchdog.stop()
            timed_out = answer is None
        elapsed = time.perf_counter() - started
        if timed_out:
            detail = ("wall-clock budget exhausted" if fired
                      else "solver returned no answer within its budget")
            return SatVerdict("inconclusive", seconds=elapsed, clauses=len(encoder.clauses),
                              variables=encoder.next_variable - 1, detail=detail, solver=name)
        if answer is False:
            return SatVerdict("equivalent", seconds=elapsed, clauses=len(encoder.clauses),
                              variables=encoder.next_variable - 1, solver=name,
                              detail=f"encoding took {encoding_seconds * 1e3:.2f} ms")
        model = solver.get_model()
        return _checked_model(left, right, contract or Contract(), model, elapsed, encoder, name)
    finally:
        solver.delete()


def _checked_model(left: Circuit, right: Circuit, contract: Contract, model, elapsed: float,
                   encoder: XagEncoder, solver_label: str) -> SatVerdict:
    """Replay the model through ``Circuit.run``; a non-counterexample is an encoding bug."""
    positive = {literal for literal in model if literal > 0}
    value = 0
    for wire in range(left.width):
        if wire + 1 in positive:
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
            "the XAG solver returned a model that is not a counterexample; the encoding is wrong")
    for wire, expected in contract.input_constants.items():
        if ((value >> wire) & 1) != expected:
            raise InternalInconsistency("a witness violates the input contract")
    return SatVerdict("different", witness=value, witness_checked=True,
                      first_differing_output=differing, seconds=elapsed,
                      clauses=len(encoder.clauses), variables=encoder.next_variable - 1,
                      solver=solver_label)
