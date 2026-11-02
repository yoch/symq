"""Small exact Kraus reference; independent of affine_phase's symbolic arithmetic."""
from __future__ import annotations

from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.phase import PhaseProgram
from symq.phase_oracle import run_program


def inputs(width: int, offset: int, columns: tuple[int, ...]) -> list[int]:
    values = []
    for z in range(1 << len(columns)):
        x = offset
        for j, column in enumerate(columns):
            if z >> j & 1:
                x ^= column
        assert 0 <= x < 1 << width
        values.append(x)
    return values


def same_channel(left: DyadicPhaseProgram, right: DyadicPhaseProgram, dephaser: PhaseProgram,
                 *, offset: int = 0, columns: tuple[int, ...] | None = None) -> bool:
    """Compare every matrix unit over Q[zeta_(2**k)], including retained ancillas."""
    left.validate()
    right.validate()
    dephaser.validate()
    assert left.width == right.width == dephaser.data
    columns = tuple(1 << i for i in range(left.width)) if columns is None else columns
    domain = inputs(left.width, offset, columns)
    k, data_mask = max(left.k, right.k), (1 << left.width) - 1
    half, modulus = 1 << (k - 1), 1 << k
    events = 1 << dephaser.measurements
    branches = {(x, m): run_program(dephaser, x, m) for x in domain for m in range(events)}

    def unit(program: DyadicPhaseProgram, x: int, y: int) -> dict:
        coefficients: dict[tuple[int, int, int], int] = {}
        for m in range(events):
            for output_x, amplitude_x in branches[x, m].items():
                for output_y, amplitude_y in branches[y, m].items():
                    a, pa = program.run(output_x & data_mask)
                    b, pb = program.run(output_y & data_mask)
                    a |= output_x & ~data_mask
                    b |= output_y & ~data_mask
                    exponent = ((pa - pb) << (k - program.k)) % modulus
                    sign = amplitude_x * amplitude_y
                    if exponent >= half:
                        exponent -= half
                        sign = -sign
                    key = a, b, exponent
                    coefficients[key] = coefficients.get(key, 0) + sign
                    if not coefficients[key]:
                        del coefficients[key]
        # The common normalization 2**(-measurements) cancels between the two sides.
        return coefficients

    return all(unit(left, x, y) == unit(right, x, y) for x in domain for y in domain)
