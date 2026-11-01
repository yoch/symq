"""Independent exact Kraus-trajectory oracle for tiny hybrid programs.

This oracle deliberately does not use the library's density-matrix evolution,
channel-composition leaf implementation or memoized branches. It enumerates
Kraus trajectories over *basis kets* (not density operators), then builds the
full matrix-unit channel by outer products of the two ket images.

The supported domain here is basis permutations, diagonal signs, X- and
Z-basis measurement, reset and deterministic classical feed-forward. It is a
small experimental qualification, not a general quantum simulation package.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product

from symq.experimental.hybrid import HybridProgram


def _condition(name: str | None, memory: dict[str, int]) -> bool:
    if name is None:
        return True
    if name.startswith("!"):
        return not bool(memory[name[1:]])
    return bool(memory[name])


def _ket_kraus_image(
    program: HybridProgram, basis: int, choices: tuple[int, ...],
    observed: tuple[str, ...],
) -> tuple[int, int, tuple[int, ...]] | None:
    """Apply a *fixed* sequence of Kraus outcomes to one computational ket.

    The total amplitude is sign / (sqrt(2) ** number_of_HMR_events); every
    admissible branch has that same denominator. Squaring the amplitude via
    an outer product yields exact rational channel coefficients.
    """
    state, phase = basis, 1
    classical: dict[str, int] = {}
    position = 0
    for op in program.ops:
        kind, qs = op.kind, op.wires
        if kind in {"hmr", "measure_z", "reset"}:
            outcome = choices[position]
            position += 1
            q = qs[0]
            bit = state >> q & 1
            if kind == "hmr":
                if outcome and bit:
                    phase = -phase
                state &= ~(1 << q)
                classical[op.slot] = outcome
            else:
                # Z measurement and reset use projectors |b><b|;
                # reset additionally maps the selected state to |0>.
                if bit != outcome:
                    return None
                if kind == "reset":
                    state &= ~(1 << q)
                else:
                    classical[op.slot] = outcome
            continue
        if kind == "store":
            classical[op.slot] = op.value
            continue
        if kind == "invert":
            classical[op.slot] ^= int(_condition(op.condition, classical))
            continue
        if kind == "oxor":
            classical[op.slot] ^= classical[op.source]
            continue
        if not _condition(op.condition, classical):
            continue
        if kind in {"x", "cx", "ccx", "mcx"}:
            *controls, target = qs
            if all((state >> q) & 1 for q in controls):
                state ^= 1 << target
        elif kind in {"swap", "cswap"}:
            if kind == "swap":
                a, b = qs
                enabled = True
            else:
                ctrl, a, b = qs
                enabled = bool(state >> ctrl & 1)
            if enabled and ((state >> a) & 1) != ((state >> b) & 1):
                state ^= (1 << a) | (1 << b)
        elif kind in {"z", "cz", "ccz", "neg"}:
            if kind == "neg" or all((state >> q) & 1 for q in qs):
                phase = -phase
        else:
            raise AssertionError(f"unqualified operation {kind!r}")
    return state, phase, tuple(classical[s] for s in observed)


def independent_kraus(
    program: HybridProgram, x: int, y: int, observed: tuple[str, ...] = (),
) -> dict[tuple[int, ...], dict[tuple[int, int], Fraction]]:
    """Construct E(|x><y|) by summing outer products of all matched Kraus paths."""
    program.validate()
    assert 0 <= x < 1 << program.data and 0 <= y < 1 << program.data
    count = sum(op.kind in {"hmr", "measure_z", "reset"} for op in program.ops)
    measurements = sum(op.kind == "hmr" for op in program.ops)
    assert count <= 8 and program.width <= 6
    factor = 1 << measurements
    images: dict[tuple[int, ...], dict[tuple[int, int], Fraction]] = {}
    for outcomes in product((0, 1), repeat=count):
        a = _ket_kraus_image(program, x, outcomes, observed)
        b = _ket_kraus_image(program, y, outcomes, observed)
        if a is None or b is None:
            continue
        assert a[2] == b[2]
        record = a[2]
        matrix = images.setdefault(record, {})
        key = (a[0], b[0])
        coefficient = matrix.get(key, Fraction(0)) + Fraction(a[1] * b[1], factor)
        if coefficient:
            matrix[key] = coefficient
        else:
            matrix.pop(key, None)
    return {record: image for record, image in images.items() if image}




def coherence_images(program: HybridProgram, observed: tuple[str, ...] = ()) -> dict:
    """``(x, y) -> image`` for every pair of data basis states."""
    from itertools import product as _product

    return {(x, y): independent_kraus(program, x, y, observed=observed)
            for x, y in _product(range(1 << program.data), repeat=2)}
