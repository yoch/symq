"""Native C/ZDD outcome-factored full-channel theorem for the narrow HMR grammar.

Experimental and opt-in. All symbolic variables are *data input bits*, never
measurement indices. Both input-coherence halves share one exact algebra owner.
No general reset, conditional value gate, H, S/T, or general hybrid program.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from symq.backends import make_algebra
from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard, ResourceLimitExceeded


@dataclass(frozen=True)
class ChannelDecision:
    equivalent: bool
    backend: str
    theorem: str
    reason: str
    left_sha256: str
    right_sha256: str
    checked_events: int
    witness_kind: str | None = None
    witness: tuple[int, int] | None = None


@dataclass(frozen=True)
class _State:
    outputs: tuple[Any, ...]
    phase0: Any
    outcome_coefficients: tuple[Any, ...]


def _sha(program: PhaseProgram) -> str:
    program.validate()
    body = {
        "grammar": "sign-hmr/affine-outcomes/full-channel/v1",
        "data": program.data,
        "ancillas": program.ancillas,
        "ops": [[op.kind, list(op.qubits), op.outcome] for op in program.ops],
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _symbolic(
    program: PhaseProgram, algebra: Any, offset: int, guard: Guard
) -> _State:
    """One coherent symbolic branch family, with zero-initialized ancillas.

    The strict PhaseProgram grammar guarantees output values do not depend on
    outcomes and its phase is affine in distinct measurement-event symbols.
    This is NOT a semantics for classically conditioned X or arbitrary reset.
    """
    data = program.data
    state = [algebra.variable(offset + q) if q < data else algebra.zero()
             for q in range(program.width)]
    phi0 = algebra.zero()
    coefficients: list[Any] = []
    for op in program.ops:
        guard.check_time()
        if op.kind == "mcx":
            *controls, target = op.qubits
            product = algebra.product([state[q] for q in controls])
            state[target] = algebra.xor(state[target], product)
        elif op.kind == "mcz":
            sign = algebra.product([state[q] for q in op.qubits])
            phi0 = algebra.xor(phi0, sign)
        elif op.kind == "hmr":
            if op.outcome != len(coefficients):
                raise UnsupportedOperation("non-fresh HMR event")
            coefficients.append(state[op.qubits[0]])
            state[op.qubits[0]] = algebra.zero()
        elif op.kind == "mcz_if":
            if op.outcome is None or op.outcome >= len(coefficients):
                raise UnsupportedOperation("uninitialized HMR feedback")
            sign = algebra.product([state[q] for q in op.qubits])
            coefficients[op.outcome] = algebra.xor(coefficients[op.outcome], sign)
        else:
            raise UnsupportedOperation(f"outside sign/HMR grammar: {op.kind!r}")
        guard.check_time()
    return _State(tuple(state), phi0, tuple(coefficients))


def _kernel(algebra: Any, x: _State, y: _State, guard: Guard) -> Any:
    """Exact coherences retained by an outcome-forgotten Kraus channel."""
    if len(x.outcome_coefficients) != len(y.outcome_coefficients):
        raise RuntimeError("the two input-coherence halves lost event identity")
    kernel = algebra.one()
    for g_x, g_y in zip(x.outcome_coefficients, y.outcome_coefficients):
        guard.check_time()
        delta = algebra.xor(g_x, g_y)
        equality = algebra.xor(algebra.one(), delta)
        kernel = algebra.product((kernel, equality))
    return kernel


def _scalar(program: PhaseProgram, assignment: int) -> tuple[int, int, tuple[int, ...]]:
    """Independent integer basis-state/event-coefficient interpreter for witnesses.

    Crucially, it computes sign debt coefficients without constructing ANFs or
    consulting the C/ZDD engine. It never enumerates measurement outcomes.
    """
    program.validate()
    if type(assignment) is not int or not 0 <= assignment < (1 << program.data):
        raise ValueError("data assignment outside declared width")
    bits = assignment  # ancillas are |0>
    phase = 0
    coefficients: list[int] = []
    for op in program.ops:
        if op.kind == "mcx":
            *controls, target = op.qubits
            if all(bits >> q & 1 for q in controls):
                bits ^= 1 << target
        elif op.kind == "mcz":
            phase ^= int(all(bits >> q & 1 for q in op.qubits))
        elif op.kind == "hmr":
            q = op.qubits[0]
            coefficients.append(bits >> q & 1)
            bits &= ~(1 << q)
        elif op.kind == "mcz_if":
            coefficients[op.outcome] ^= int(all(bits >> q & 1 for q in op.qubits))
        else:
            raise UnsupportedOperation(op.kind)
    return bits, phase, tuple(coefficients)


def _scalar_kernel(program: PhaseProgram, x: int, y: int) -> bool:
    gx = _scalar(program, x)[2]
    gy = _scalar(program, y)[2]
    return gx == gy


def check_full_channel(
    left: PhaseProgram, right: PhaseProgram, *, backend: str = "zdd-native",
    budget: Budget | None = None, max_events: int = 10000,
    max_ops: int = 100000,
) -> ChannelDecision:
    """Exact full data+ancilla quantum channel equality on all coherent inputs.

    The theorem uses K_m|x> = 2^(-M/2) (-1)^phi(x,m) |F(x)> for the
    *existing restricted sign/HMR grammar*. For all (x,y), the outcome
    summation is a Boolean kernel:
      E(|x><y|) = (-1)^(phi0(x)+phi0(y)) [g(x)=g(y)]
                  |F(x)><F(y)|.
    This uses 2*data ZDD variables, independent of M; none correspond to
    ancillas or measurement events. The native path runs the C/ZDD ring
    operations, not a Python-only emulation. Full channel retains *every*
    quantum ancilla wire; it does NOT compare measured classical records.
    """
    guard = Guard(budget)
    if type(left) is not PhaseProgram or type(right) is not PhaseProgram:
        raise TypeError("two PhaseProgram instances required")
    if type(backend) is not str or backend not in {"zdd-native", "zdd"}:
        raise ValueError("explicit 'zdd-native' or 'zdd' backend required")
    if (type(max_events) is not int or max_events < 1 or
            type(max_ops) is not int or max_ops < 1):
        raise ValueError("positive event and gate limits required")
    left.validate()
    right.validate()
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("data and ancilla widths must match for full-channel equality")
    if any(len(p.ops) > max_ops for p in (left, right)):
        raise ResourceLimitExceeded("ops", max_ops, max(len(left.ops), len(right.ops)))
    if any(p.measurements > max_events for p in (left, right)):
        raise ResourceLimitExceeded(
            "events", max_events, max(left.measurements, right.measurements)
        )
    if backend == "zdd-native" and 2 * left.data > 64:
        raise ResourceLimitExceeded("native pair variables", 64, 2 * left.data)
    left_sha, right_sha = _sha(left), _sha(right)
    guard.check_time()
    # One algebra owns all four symbolic states and their live ZDD handles.
    # No collection is permitted while externally held handles exist.
    algebra = make_algebra(backend, 2 * left.data, budget)
    lx = _symbolic(left, algebra, 0, guard)
    rx = _symbolic(right, algebra, 0, guard)

    def different(reason: str, kind: str, xy: tuple[int, int]) -> ChannelDecision:
        guard.check_time()
        if _sha(left) != left_sha or _sha(right) != right_sha:
            raise RuntimeError("mutable input programs changed during verification")
        return ChannelDecision(
            False, backend, "full_quantum_channel", reason,
            left_sha, right_sha, left.measurements + right.measurements, kind, xy,
        )

    # Diagonal (x=x) input coherences imply equality of basis output maps.
    for wire, (a, b) in enumerate(zip(lx.outputs, rx.outputs)):
        guard.check_time()
        difference = algebra.xor(a, b)
        if not algebra.is_zero(difference):
            witness = algebra.min_monomial(difference)
            if witness is None:
                raise RuntimeError("nonzero output difference has no witness")
            x = witness & ((1 << left.data) - 1)
            if (_scalar(left, x)[0] >> wire & 1) == (_scalar(right, x)[0] >> wire & 1):
                raise RuntimeError("native output witness fails independent integer replay")
            return different(f"full output wire {wire} differs", "input", (x, x))

    ly = _symbolic(left, algebra, left.data, guard)
    ry = _symbolic(right, algebra, right.data, guard)
    kl = _kernel(algebra, lx, ly, guard)
    kr = _kernel(algebra, rx, ry, guard)
    kernel_mismatch = algebra.xor(kl, kr)
    if not algebra.is_zero(kernel_mismatch):
        witness = algebra.min_monomial(kernel_mismatch)
        if witness is None:
            raise RuntimeError("nonzero channel-kernel difference has no witness")
        mask = (1 << left.data) - 1
        x, y = witness & mask, (witness >> left.data) & mask
        if _scalar_kernel(left, x, y) == _scalar_kernel(right, x, y):
            raise RuntimeError("native kernel witness fails independent scalar replay")
        return different("outcome-dephasing kernels differ", "coherence", (x, y))

    # Sign differences are relevant only on surviving coherences; global
    # outcome-only signs and global data signs are correctly unobservable.
    phase_x = algebra.xor(lx.phase0, rx.phase0)
    phase_y = algebra.xor(ly.phase0, ry.phase0)
    mismatch = algebra.product((kl, algebra.xor(phase_x, phase_y)))
    if not algebra.is_zero(mismatch):
        witness = algebra.min_monomial(mismatch)
        if witness is None:
            raise RuntimeError("nonzero relative-phase difference has no witness")
        mask = (1 << left.data) - 1
        x, y = witness & mask, (witness >> left.data) & mask
        a = _scalar(left, x)[1] ^ _scalar(right, x)[1]
        b = _scalar(left, y)[1] ^ _scalar(right, y)[1]
        if (a == b or not _scalar_kernel(left, x, y) or
                not _scalar_kernel(right, x, y)):
            raise RuntimeError("native phase witness fails independent integer replay")
        return different("relative phase differs on retained coherence",
                         "coherence", (x, y))
    guard.check_time()
    if _sha(left) != left_sha or _sha(right) != right_sha:
        raise RuntimeError("mutable input programs changed during verification")
    return ChannelDecision(
        True, backend, "full_quantum_channel", "all basis coherences match",
        left_sha, right_sha, left.measurements + right.measurements,
    )
