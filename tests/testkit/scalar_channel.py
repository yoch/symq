"""Exact density-matrix oracle for the sign-phase/HMR fragment.

Deliberately independent of ``symq.phase``: it shares no code with the ANF semantics, never forms
a polynomial, and works with exact rational arithmetic throughout.

Amplitudes are kept as integers with the per-Hadamard factor ``1/sqrt 2`` left out, so the
unnormalised Kraus operator of an outcome sequence is an integer matrix ``K~_m`` and

    E(rho) = 2^{-M} sum_m K~_m rho K~_m^dagger

because ``K_m = 2^{-M/2} K~_m``. The single ``2^{-M}`` factor is applied once, at the end.

Two properties matter for the correctness of the oracle itself, and both were wrong in the first
version (see ``PILOT_A_CORRECTIONS.md``):

* **the partial trace** keeps only entries whose row and column carry the *same* ancilla pattern,
  ``sum_a <d, a| rho |d', a>``. Dropping the ancilla bits and adding, without that condition,
  produces a non-physical matrix (on a Bell pair it gives trace 2 instead of 1);
* **basis pairs are encoded as tuples**, never as shifted integers, so no width can make two
  distinct pairs collide.
"""
from __future__ import annotations

from fractions import Fraction

from symq.phase import Op, PhaseProgram

Amplitude = Fraction
Vector = dict[int, Amplitude]
Matrix = dict[tuple[int, int], Amplitude]
PairKey = tuple[int, int, int, int]
"""``(x, y, u, v)``: input row, input column, output row, output column."""


def _add(state: Vector, basis: int, value: Amplitude) -> None:
    state[basis] = state.get(basis, Fraction(0)) + value


def _apply(state: Vector, op: Op, outcomes: int | None = None) -> Vector:
    """Apply one permutation or phase instruction exactly."""
    if op.kind == "mcz_if":
        if outcomes is None:
            raise ValueError("feed-forward needs the outcome sequence")
        if not (outcomes >> op.outcome) & 1:
            return state
        return _apply(state, Op("mcz", op.qubits, None))
    if op.kind == "mcx":
        *controls, target = op.qubits
        mask = sum(1 << c for c in controls)
        out: Vector = {}
        for basis, value in state.items():
            _add(out, basis ^ (1 << target) if basis & mask == mask else basis, value)
        return out
    if op.kind == "mcz":
        mask = sum(1 << q for q in op.qubits)
        return {basis: -value if basis & mask == mask else value
                for basis, value in state.items() if value}
    raise ValueError(op.kind)


def kraus_operator(program: PhaseProgram, outcomes: int) -> Matrix:
    """The unnormalised ``K~_m`` for the outcome sequence ``outcomes`` (row = output basis)."""
    program.validate()
    if not 0 <= outcomes < (1 << program.measurements):
        raise ValueError("outcome sequence outside the measurement count")
    operator: Matrix = {}
    for x in range(1 << program.data):
        state: Vector = {x: Fraction(1)}
        for op in program.ops:
            if op.kind != "hmr":
                state = _apply(state, op, outcomes)
                continue
            (qubit,) = op.qubits
            bit = 1 << qubit
            wanted = (outcomes >> op.outcome) & 1
            projected: Vector = {}
            for basis, value in state.items():
                sign = -1 if basis & bit else 1
                # H|b> = (|0> + (-1)^b |1>)/sqrt2, then project on the outcome and reset.
                _add(projected, basis & ~bit, value * (1 if wanted == 0 else sign))
            state = projected
        for basis, value in state.items():
            if value:
                operator[(basis, x)] = operator.get((basis, x), Fraction(0)) + value
    return operator


def dagger(matrix: Matrix) -> Matrix:
    return {(col, row): value for (row, col), value in matrix.items()}


def compose(left: Matrix, right: Matrix) -> Matrix:
    """``left . right``: ``sum_j left[i, j] right[j, k]``."""
    by_row: dict[int, dict[int, Amplitude]] = {}
    for (row, col), value in right.items():
        by_row.setdefault(row, {})[col] = value
    result: Matrix = {}
    for (row, middle), value in left.items():
        for col, entry in by_row.get(middle, {}).items():
            key = (row, col)
            result[key] = result.get(key, Fraction(0)) + value * entry
    return {k: v for k, v in result.items() if v}


def channel(program: PhaseProgram, rho: Matrix) -> Matrix:
    """``E(rho) = 2^{-M} sum_m K~_m rho K~_m^dagger``, exact, ancillas **not** traced out."""
    total: Matrix = {}
    for outcomes in range(1 << program.measurements):
        operator = kraus_operator(program, outcomes)
        part = compose(compose(operator, rho), dagger(operator))
        for key, value in part.items():
            total[key] = total.get(key, Fraction(0)) + value
    scale = Fraction(1, 2 ** program.measurements)
    scaled = {k: v * scale for k, v in total.items()}
    return {k: v for k, v in scaled.items() if v}


def partial_trace(program: PhaseProgram, matrix: Matrix) -> Matrix:
    """Trace out the ancillas: ``rho'[d, d'] = sum_a rho[(d, a), (d', a)]``.

    The ancilla configuration must be the **same** on the row and the column; without that
    condition the result is not the partial trace (and not even a physical matrix).
    """
    data_mask = (1 << program.data) - 1
    result: Matrix = {}
    for (row, col), value in matrix.items():
        if (row >> program.data) != (col >> program.data):
            continue
        key = (row & data_mask, col & data_mask)
        result[key] = result.get(key, Fraction(0)) + value
    return {k: v for k, v in result.items() if v}


def trace(matrix: Matrix) -> Fraction:
    return sum((value for (row, col), value in matrix.items() if row == col), Fraction(0))


def is_physical(program: PhaseProgram, matrix: Matrix, *, tolerance: Fraction | None = None
                ) -> bool:
    """Hermiticity and unit trace, checked exactly (or within ``tolerance``)."""
    limit = Fraction(0) if tolerance is None else tolerance
    for (row, col), value in matrix.items():
        other = matrix.get((col, row), Fraction(0))
        if abs(value - other) > limit:
            return False
    return abs(trace(matrix) - 1) <= limit


def channel_matrix(program: PhaseProgram, *, trace_ancillas: bool = False) -> dict[PairKey,
                                                                                  Amplitude]:
    """The complete channel as ``{(x, y, u, v): amplitude}``.

    ``x, y`` are data-wire basis states (every ancilla starts in ``|0>``); ``u, v`` are full
    basis states unless ``trace_ancillas`` is set. Tuples, not packed integers, so no pair can
    collide at any width.
    """
    result: dict[PairKey, Amplitude] = {}
    for x in range(1 << program.data):
        for y in range(1 << program.data):
            image = channel(program, {(x, y): Fraction(1)})
            if trace_ancillas:
                image = partial_trace(program, image)
            for (u, v), value in image.items():
                result[(x, y, u, v)] = value
    return result


def same_channel(left: PhaseProgram, right: PhaseProgram, *, trace_ancillas: bool = False
                 ) -> bool:
    """Exact equality of the two channels on ``(data + ancilla)``, or on the data wires only.

    The full comparison is the faithful one for programs of equal width: an ancilla left
    entangled with the data changes the channel even when the data outputs agree.
    """
    if left.data != right.data:
        raise ValueError("programs must have the same number of data wires")
    if left.width != right.width:
        raise ValueError("programs must have the same number of ancillas to compare channels")
    return (channel_matrix(left, trace_ancillas=trace_ancillas)
            == channel_matrix(right, trace_ancillas=trace_ancillas))


def coherence_image(program: PhaseProgram, x: int, y: int, *, trace_ancillas: bool = True
                    ) -> Matrix:
    """``E(|x><y|)``: ``{(u, v): amplitude}``, ancillas traced out by default."""
    image = channel(program, {(x, y): Fraction(1)})
    return partial_trace(program, image) if trace_ancillas else image


def is_trace_preserving(program: PhaseProgram) -> bool:
    """``sum_m K_m^dagger K_m = I`` on the data wires, checked exactly."""
    total: Matrix = {}
    for outcomes in range(1 << program.measurements):
        operator = kraus_operator(program, outcomes)
        for key, value in compose(dagger(operator), operator).items():
            total[key] = total.get(key, Fraction(0)) + value
    scale = Fraction(1, 2 ** program.measurements)
    scaled = {k: v * scale for k, v in total.items() if v}
    identity = {(x, x): Fraction(1) for x in range(1 << program.data)}
    return scaled == identity
