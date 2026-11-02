"""Public constructed nonlinear dephasing and phase-source fixtures."""
from __future__ import annotations

from fractions import Fraction

from symq.labs import affine_phase as core
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.phase import PhaseProgram


def candidate(values, k=2):
    planes = []
    for bit in range(k):
        coefficients = [(v >> bit) & 1 for v in values]
        for j in range(2):
            for mask in range(4):
                if mask >> j & 1:
                    coefficients[mask] ^= coefficients[mask ^ (1 << j)]
        planes.append(tuple(m for m, c in enumerate(coefficients) if c))
    return tuple(planes)


def fixture(values=(0, 1, 2, 3)):
    dephaser = PhaseProgram(4, 1).ccx(0, 1, 4)
    dephaser.hmr(4)
    dephaser.ccx(1, 2, 4)
    dephaser.hmr(4)
    support = core.AffineSupport(4, 0, (1, 2, 4))
    c0, c1, c2, c3 = (values[0], (values[1] - values[0]) % 4,
                       (values[2] - values[0]) % 4,
                       (values[3] - values[2] - values[1] + values[0]) % 4)
    left, right = DyadicPhaseProgram(4, k=2), DyadicPhaseProgram(4, k=2)
    if c0:
        left.x(3).phase(3, Fraction(c0, 4)).x(3)
    for c, wires in zip((c1, c2, c3), ((0, 1), (1, 2), (0, 1, 2))):
        if c:
            left.mcx(*wires, 3).phase(3, Fraction(c, 4)).mcx(*wires, 3)
    return left, right, dephaser, support
