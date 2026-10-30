"""Optional QCEC proof adapter for the strictly unitary H/dyadic-phase fragment.

The dependency is imported only on use. Dynamic circuits are rejected before any
external call, and callers explicitly choose their global-phase convention.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from symq.circuit import UnsupportedOperation
from symq.resources import Budget, Guard, session_scoped

from .cyclotomic import CyclotomicProgram
from .phase import PhaseProgram, _check_engine


@dataclass(frozen=True)
class UnitaryVerdict:
    verdict: str
    equivalent: bool | None
    up_to_global: bool
    check_seconds: float
    preprocessing_seconds: float
    relation: str = "unitary"


def _validate(program) -> None:
    if type(program) not in (PhaseProgram, CyclotomicProgram):
        raise TypeError("PhaseProgram or CyclotomicProgram required")
    program.validate()
    for gate in program.gates:
        if gate.name in {"hmr", "phase_if"}:
            raise UnsupportedOperation("QCEC adapter accepts unitary circuits only")
        # QCEC's rotation parameters are doubles. Exact arbitrary dyadic turns
        # must never be silently rounded during conversion.
        if gate.name == "phase":
            raise UnsupportedOperation("QCEC exact adapter supports named Clifford+T phases only")


def _external():
    # Reuse the maintained, proof-only alternating-checker configuration.
    from symq.external import qcec
    return qcec


def _convert(program, external, guard):
    guard.check_time()
    guard.check_terms(program.width)
    qc = external.QuantumComputation(program.width)
    for gate in program.gates:
        guard.check_time()
        name, wires = gate.name, gate.wires
        if name in {"x", "h", "t", "tdg", "s", "sdg", "z"}:
            getattr(qc, name)(wires[0])
        elif name in {"cx", "cz"}:
            getattr(qc, name)(*wires)
        elif name in {"ccx", "mcx"}:
            qc.mcx(set(wires[:-1]), wires[-1])
        elif name == "ccz":
            qc.h(wires[-1])
            qc.mcx(set(wires[:-1]), wires[-1])
            qc.h(wires[-1])
        else:
            raise UnsupportedOperation(f"unsupported QCEC gate {name!r}")
    guard.check_time()
    return qc


@session_scoped
def to_quantum_computation(program, budget: Budget | None = None, *,
                           _guard: Guard | None = None):
    guard = _guard if _guard is not None else Guard(budget)
    _check_engine(guard)
    _validate(program)
    return _convert(program, _external(), guard)


@session_scoped
def check_unitary_equivalence(left, right, *, up_to_global: bool,
                              budget: Budget | None = None, timeout: float = 0.0,
                              _guard: Guard | None = None) -> UnitaryVerdict:
    if type(up_to_global) is not bool:
        raise ValueError("explicit Boolean up_to_global convention required")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("timeout must be nonnegative seconds")
    guard = _guard if _guard is not None else Guard(budget)
    _check_engine(guard)
    _validate(left)
    _validate(right)
    if left.width != right.width:
        raise ValueError("width mismatch")
    external = _external()
    a, b = _convert(left, external, guard), _convert(right, external, guard)
    remaining = guard.remaining_seconds() if hasattr(guard, "remaining_seconds") else None
    if remaining is None and guard.deadline is not None:
        import time
        guard.check_time()
        remaining = guard.deadline - time.perf_counter()
    if remaining is not None:
        timeout = min(timeout, remaining) if timeout else remaining
    guard.check_time()
    result = external.qcec_check_computations(a, b, timeout=timeout)
    guard.check_time()
    if result.verdict == "equivalent":
        equivalent = True
    elif result.verdict == "equivalent_up_to_global_phase":
        equivalent = up_to_global
    elif result.verdict == "not_equivalent":
        equivalent = False
    else:
        equivalent = None
    return UnitaryVerdict(result.verdict, equivalent, up_to_global,
                          result.check_seconds, result.preprocessing_seconds)
