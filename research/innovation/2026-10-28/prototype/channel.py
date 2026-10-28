"""Exact density-matrix oracle for the sign-phase/HMR fragment.

Deliberately independent of ``symq.phase``: it shares no code with the ANF semantics, never
forms a polynomial, and works with exact rational arithmetic throughout.

Amplitudes are kept as integers with the per-Hadamard factor ``1/sqrt 2`` left out, so the
unnormalised Kraus operator of an outcome sequence is an integer matrix ``K~_m`` and

    E(rho) = 2^{-M} sum_m K~_m rho K~_m^dagger

because ``K_m = 2^{-M/2} K~_m``. The single ``2^{-M}`` factor is applied once, at the end, so
every intermediate value is exact and no square root is ever approximated.
"""
from __future__ import annotations

from fractions import Fraction

from symq.phase import Op, PhaseProgram

Amplitude = Fraction
Vector = dict[int, Amplitude]
Matrix = dict[tuple[int, int], Amplitude]


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
    """The unnormalised ``K~_m`` for the outcome sequence ``outcomes``.

    Bit ``j`` of ``outcomes`` is the outcome of measurement ``j``. Column ``x`` is the state
    reached from ``|x>|0>_anc`` conditioned on those outcomes, with the Hadamards unnormalised.
    """
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
                # H|b> = (|0> + (-1)^b |1>)/sqrt2, then project and reset the wire to |0>.
                _add(projected, basis & ~bit, value * (1 if wanted == 0 else sign))
            state = projected
        for basis, value in state.items():
            if value:
                operator[(basis, x)] = operator.get((basis, x), Fraction(0)) + value
    return operator


def dagger(matrix: Matrix) -> Matrix:
    return {(col, row): value for (row, col), value in matrix.items()}


def compose(left: Matrix, right: Matrix) -> Matrix:
    """``left . right`` for matrices given as ``{(row, col): amplitude}``.

    ``(left . right)[i, k] = sum_j left[i, j] right[j, k]``, so ``right`` is indexed by its
    **row** ``j``: an entry of ``right`` with row ``j`` contributes to every product that reads
    column ``j`` of ``left``.
    """
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


def trace_out_ancillas(program: PhaseProgram, matrix: Matrix) -> Matrix:
    mask = (1 << program.data) - 1
    result: Matrix = {}
    for (row, col), value in matrix.items():
        key = (row & mask, col & mask)
        result[key] = result.get(key, Fraction(0)) + value
    return {k: v for k, v in result.items() if v}


def channel_matrix(program: PhaseProgram, *, trace_ancillas: bool = False) -> Matrix:
    """The complete channel, as ``{(input pair, output pair): amplitude}``.

    Input pairs are ``(x, y)`` on the data wires, with every ancilla started in ``|0>``; output
    pairs are full ``data + ancilla`` basis states unless ``trace_ancillas`` is set. Every input
    coherence ``|x><y|`` is propagated separately, so off-diagonal coherences are measured, not
    assumed. Pairs are encoded as ``x * 2**n + y`` with ``n = program.width``.
    """
    result: Matrix = {}
    for x in range(1 << program.data):
        for y in range(1 << program.data):
            image = channel(program, {(x, y): Fraction(1)})
            if trace_ancillas:
                image = trace_out_ancillas(program, image)
            source = (x << 16) | y
            for (u, v), value in image.items():
                result[(source, (u << 16) | v)] = value
    return result


def same_channel(left: PhaseProgram, right: PhaseProgram, *, trace_ancillas: bool = False
                 ) -> bool:
    """Exact equality of the two channels on ``(data + ancilla)``, or on data only.

    The full comparison is the faithful one for programs of equal width: an ancilla left
    entangled with the data changes the channel even when the data outputs agree.
    """
    if left.data != right.data:
        raise ValueError("programs must have the same number of data wires")
    if left.width != right.width:
        raise ValueError("programs must have the same number of ancillas to compare channels")
    return (channel_matrix(left, trace_ancillas=trace_ancillas)
            == channel_matrix(right, trace_ancillas=trace_ancillas))


def coherence_image(program: PhaseProgram, x: int, y: int) -> Matrix:
    """``E(|x><y|)`` on the data wires, ancillas traced out: ``{(u, v): amplitude}``."""
    return trace_out_ancillas(program, channel(program, {(x, y): Fraction(1)}))


def is_trace_preserving(program: PhaseProgram) -> bool:
    """``sum_m K_m^dagger K_m = I`` on data+ancillas, checked exactly."""
    total: Matrix = {}
    for outcomes in range(1 << program.measurements):
        operator = kraus_operator(program, outcomes)
        part = compose(dagger(operator), operator)
        for key, value in part.items():
            total[key] = total.get(key, Fraction(0)) + value
    scale = Fraction(1, 2 ** program.measurements)
    scaled = {k: v * scale for k, v in total.items()}
    scaled = {k: v for k, v in scaled.items() if v}
    # ``K~_m`` maps data basis states to full basis states, so ``K_m^dagger K_m`` acts on the
    # data wires alone; the ancillas start in |0> and are not part of the input space.
    identity = {(x, x): Fraction(1) for x in range(1 << program.data)}
    return scaled == identity
