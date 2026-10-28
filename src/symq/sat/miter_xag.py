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
from symq.resources import Budget

from .encoding import Contract, SatUnavailable, SatVerdict, solver_available
from .encoding_xag import XagCircuit, XagEncoder, build_xag
from .miter import observed_pairs


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
    """Decide ``left ~ right`` with the affine encoding, sharing the SSA engine's whole protocol.

    The budget, the solver choice, the deadline discipline and the witness replay are **the ones of
    ``check_sat_equivalence``**: this function only replaces how the clauses are produced. Writing a
    second copy of the timing logic is how the two encoders would drift apart, and the review of #75
    found exactly that in the first version -- the XAG path started its clock after encoding, never
    checked the deadline before solving, and left model extraction and cleanup outside the budget.

    The affine encoder is used only to *build* the CNF; the shared driver does the rest, so
    ``inconclusive`` is never confused with a decided verdict, and a late UNSAT is never reported
    as "within budget".
    """
    if not solver_available():
        raise SatUnavailable("no SAT solver installed: pip install python-sat")
    contract = contract or Contract()
    started = time.perf_counter()
    miter = AffineMiter(left, right, contract)
    # The clause that makes a model a counterexample must be added *before* the driver reads the
    # clause list; the driver asserts nothing by itself.
    encoder = miter.encoder
    encoder.add(*miter.difference) if len(miter.difference) > 1 else encoder.add(
        miter.difference[0])
    miter.clauses = encoder.clauses
    return _run_shared_driver(left, right, contract, miter, budget, started=started)


class AffineMiter:
    """The affine CNF of a pair, exposed in the shape the shared driver expects."""

    def __init__(self, left: Circuit, right: Circuit, contract: Contract) -> None:
        self.encoder, self.difference, self.left_model, self.right_model = build_xag_miter(
            left, right, contract)
        self.inputs = list(self.left_model.inputs)
        self.clauses: list[list[int]] = self.encoder.clauses
        self.variable_count = lambda: self.encoder.next_variable - 1


def _run_shared_driver(left: Circuit, right: Circuit, contract: Contract, miter: AffineMiter,
                       budget: Budget | None, *, started: float) -> SatVerdict:
    from .miter import drive_solver

    return drive_solver(left, right, contract, miter, budget, started=started)
