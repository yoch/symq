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

import time
from collections.abc import Callable
from dataclasses import dataclass

from symq.circuit import Circuit
from symq.errors import InternalInconsistency
from symq.resources import Budget, Guard

from ._solve import _Watchdog, solve_with_deadline  # noqa: F401 - _Watchdog re-exported
from .encoding import (
    Contract,
    Encoder,
    SatUnavailable,
    SatVerdict,
    _encode_validated,
    _solver_factory,
    solver_available,
    solver_name,
)


@dataclass
class Miter:
    """A built miter: the clauses, the literals to satisfy, and the input variables."""

    encoder: Encoder
    difference: list[int]
    inputs: list[int]
    """``inputs[wire]`` is the variable holding the shared input value of that wire."""


def build_miter(left: Circuit, right: Circuit, contract: Contract | None = None, *,
                encoder: Encoder | None = None,
                checkpoint: Callable[[], None] | None = None) -> Miter:
    """Encode a shared-input miter, optionally using a research-only bounded encoder.

    Default callers build the same unbounded Encoder as before. A caller that
    supplies ``encoder`` can enforce allocation caps, and ``checkpoint``
    makes long gate loops cooperative even when simplification creates no clauses.
    """
    contract = contract or Contract()
    if checkpoint is not None:
        checkpoint()
    _validate_miter_inputs(left, right, contract)
    if checkpoint is not None:
        checkpoint()
    encoder = Encoder() if encoder is None else encoder
    if not isinstance(encoder, Encoder):
        raise TypeError("encoder must be an Encoder")
    return _encode_miter(left, right, contract, encoder, checkpoint)


def _validate_miter_inputs(left: Circuit, right: Circuit, contract: Contract) -> None:
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


def _encode_miter(left: Circuit, right: Circuit, contract: Contract, encoder: Encoder,
                  checkpoint: Callable[[], None] | None) -> Miter:
    """Encode inputs that ``_validate_miter_inputs`` accepted earlier in the same call.

    ``checkpoint`` is polled every 64 gates and after each circuit. The circuits are not
    validated a second time, so both callers validate immediately before calling this.
    """
    left_steps = _encode_validated(encoder, left, None, checkpoint)
    # Both circuits read the same input variables: no tying clauses, and every common
    # sub-circuit is encoded once thanks to the encoder's structural hashing.
    right_steps = _encode_validated(encoder, right, left_steps.inputs, checkpoint)
    initial_left = left_steps.inputs
    final_left, final_right = left_steps.outputs, right_steps.outputs

    for wire, value in sorted(contract.input_constants.items()):
        encoder.add(initial_left[wire] if value else -initial_left[wire])
    if contract.assumption is not None:
        from .assumptions import tseitin

        encoder.add(tseitin(contract.assumption, encoder,
                            lambda name: initial_left[int(name[2:])]))

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


class _DeadlineReached(Exception):
    """Private signal: the deadline passed while a miter was being encoded."""


_CLAUSE_CHUNK = 50_000
"""Clauses handed to the solver between two deadline checks when a deadline is set."""


def check_sat_equivalence(left: Circuit, right: Circuit, contract: Contract | None = None,
                          budget: Budget | None = None) -> SatVerdict:
    """Decide classical equivalence with a cooperative whole-call deadline.

    Every phase shares the entry-time deadline, which also respects an enclosing
    ``VerificationSession``. With a deadline, the encoding polls it every 64 gates and the clauses
    are handed to the solver in chunks, so a large instance stops shortly after the deadline
    instead of being encoded and loaded in full first; a deadline that passes in any phase gives
    ``inconclusive``. Inputs are validated completely before the first poll: an invalid circuit or
    contract raises whatever the budget.

    This remains a soft deadline, not a hard wall-clock limit: a Python/C step already running
    cannot be preempted, and memory is not bounded. A decisive answer completed after the deadline
    is returned as inconclusive instead of "within budget". Strict limits require a separately
    killable worker process.

    Only max_seconds applies to SAT; max_nodes/max_terms/max_bytes describe symbolic resources.
    Without a deadline the encoding and the solver setup are exactly those of ``build_miter``.
    """
    started = time.perf_counter()
    deadline = Guard(budget).deadline
    if not solver_available():
        raise SatUnavailable("no interruptible SAT solver installed: pip install python-sat")
    contract = contract if contract is not None else Contract()

    def expired() -> bool:
        return deadline is not None and time.perf_counter() >= deadline

    def poll() -> None:
        if expired():
            raise _DeadlineReached

    _validate_miter_inputs(left, right, contract)
    factory = _solver_factory()
    if factory is None:
        raise SatUnavailable("no interruptible SAT solver installed: pip install python-sat")
    name = solver_name(factory)
    encoder = Encoder()

    def verdict(outcome: str, detail: str = "") -> SatVerdict:
        return SatVerdict(
            outcome, clauses=len(encoder.clauses),
            variables=encoder.next_variable - 1, detail=detail, solver=name,
        )

    def finish(result: SatVerdict) -> SatVerdict:
        result.seconds = time.perf_counter() - started
        return result

    try:
        miter = _encode_miter(left, right, contract, encoder,
                              None if deadline is None else poll)
    except _DeadlineReached:
        # The counts are those of the partial encoding: what was built before the deadline.
        return finish(verdict("inconclusive", "wall-clock budget exhausted during encoding"))
    encoder.add(*miter.difference)

    if expired():
        return finish(verdict("inconclusive", "wall-clock budget exhausted during encoding"))
    clauses = encoder.clauses
    chunked = deadline is not None and len(clauses) > _CLAUSE_CHUNK
    solver = factory(bootstrap_with=clauses[:_CLAUSE_CHUNK] if chunked else clauses)
    try:
        # ``loaded`` is the only thing that authorizes solving: a solver holding part of the
        # clauses decides a different, weaker formula, whatever a later clock reading says.
        loaded = _CLAUSE_CHUNK if chunked else len(clauses)
        while loaded < len(clauses) and not expired():
            solver.append_formula(clauses[loaded:loaded + _CLAUSE_CHUNK], no_return=True)
            loaded += _CLAUSE_CHUNK
        if loaded < len(clauses) or expired():
            return finish(verdict("inconclusive", "wall-clock budget exhausted during solver setup"))
        answer, timed_out = solve_with_deadline(solver, deadline)
        if timed_out:
            result = verdict("inconclusive", "wall-clock budget exhausted")
        elif answer is None:
            result = verdict("inconclusive", "solver returned no answer within its conflict budget")
        elif answer is False:
            result = verdict("equivalent", "within budget")
        elif answer is True:
            model = solver.get_model()
            if expired():
                result = verdict("inconclusive", "wall-clock budget exhausted during model extraction")
            else:
                result = _checked_model(left, right, contract, model, miter.inputs, encoder, name)
                if expired():
                    result = verdict("inconclusive", "wall-clock budget exhausted during witness replay")
        else:
            result = verdict("inconclusive", "unexpected SAT solver response")
    finally:
        solver.delete()
    if expired() and result.outcome != "inconclusive":
        result = verdict("inconclusive", "wall-clock budget exhausted during solver cleanup")
    return finish(result)


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
    if contract.assumption is not None:
        from .assumptions import evaluate

        bits = {f"x.{wire}": (value >> wire) & 1 for wire in range(left.width)}
        if not evaluate(contract.assumption, bits):
            raise InternalInconsistency("a witness violates the contract's assumption")
    return SatVerdict("different", witness=value, witness_checked=True,
                      first_differing_output=differing,
                      clauses=len(encoder.clauses), variables=encoder.next_variable - 1,
                      solver=solver_label)
