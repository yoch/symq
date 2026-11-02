"""Original, generated development fixtures; no external circuit corpus or holdout."""
from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction

from symq.labs.affine_phase import AffineSupport
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.phase import PhaseProgram


@dataclass
class Case:
    left: DyadicPhaseProgram
    right: DyadicPhaseProgram
    dephaser: PhaseProgram
    support: AffineSupport
    expected: str
    description: dict


def dephase(width, rows):
    source = PhaseProgram(width, int(bool(rows)))
    for row in rows:
        for q in range(width):
            if row >> q & 1:
                source.cx(q, width)
        source.hmr(width)
    return source


def _forms(n, presentation):
    if presentation == "cycle":
        p = [(i,) for i in range(n) if i % 3 != 1]
        q = [(i,) for i in range(n) if i % 3 != 0]
    elif presentation == "partition":
        p = [(i,) for i in range(n // 2)]
        q = [(i,) for i in range(n // 2, n)]
    elif presentation == "almost_equal":
        p, q = [(i,) for i in range(n)], [(i,) for i in range(1, n)]
    elif presentation == "nonlinear":
        p = sorted({tuple(sorted((i, (i + 1) % n))) for i in range(n) if i % 3 != 1})
        q = sorted({tuple(sorted((i, (i + 2) % n))) for i in range(n) if i % 3 != 0})
    else:
        raise ValueError("unknown presentation")
    return p, q


def _compute(program, terms, target, reverse=False):
    for controls in reversed(terms) if reverse else terms:
        program.mcx(*controls, target)


def make_case(family="identity", n=9, k=3, presentation="cycle", seed=0,
              mixed_support=False, scale=1):
    """``scale`` multiplies every dyadic phase; it keeps the default fixtures unchanged."""
    if type(n) is not int or n < 3 or n > 80:
        raise ValueError("n must be an integer in 3..80")
    if type(scale) is not int or scale < 1:
        raise ValueError("scale must be a positive integer")
    width, a, b, t = n + 3, n, n + 1, n + 2
    left, right = DyadicPhaseProgram(width, k=k), DyadicPhaseProgram(width, k=k)
    p, q = _forms(n, presentation)
    if family in ("identity", "perturbed", "dephased_identity", "singleton", "output_negative"):
        _compute(right, p, a)
        _compute(right, q, b)
        right.phase(a, Fraction(scale, 1 << k)).phase(b, Fraction(scale, 1 << k))
        right.cx(a, b).phase(b, Fraction(-scale, 1 << k)).cx(a, b)
        coefficient = -1 if family == "perturbed" else -2
        right.ccx(a, b, t).phase(t, Fraction(scale * coefficient, 1 << k)).ccx(a, b, t)
        _compute(right, q, b, reverse=True)
        _compute(right, p, a, reverse=True)
        if family == "output_negative":
            right.x(t)
    elif family in ("single_dense", "invariant_dense", "grouped_zero", "near_invariant_dense"):
        dense = [(i,) for i in range(n)]
        _compute(right, dense, a)
        right.phase(a, Fraction(scale, 1 << k))
        if family == "grouped_zero":
            right.phase(a, Fraction(-scale, 1 << k))
        _compute(right, dense, a, reverse=True)
    else:
        raise ValueError("unknown family")
    rows = ()
    if family == "singleton":
        rows = tuple(1 << i for i in range(n))
    elif family == "dephased_identity":
        rows = (sum(1 << controls[0] for controls in p if len(controls) == 1),)
    elif family == "invariant_dense":
        rows = ((1 << n) - 1,)
    elif family == "near_invariant_dense":
        # The dense predicate is invariant along every kernel direction but the last.
        rows = ((1 << (n - 1)) - 1,)
    columns = [1 << i for i in range(n)]
    offset = 0
    if mixed_support:
        rng = random.Random(seed)
        for _ in range(3 * n):
            i, j = rng.sample(range(n), 2)
            columns[i] ^= columns[j]
        rng.shuffle(columns)
        offset = rng.randrange(1 << n)
    domain = AffineSupport(width, offset, tuple(columns))
    expected = ("not_proved" if family in ("perturbed", "single_dense", "output_negative",
                                           "near_invariant_dense") else "equivalent")
    return Case(left, right, dephase(width, rows), domain, expected,
                {"family": family, "n": n, "k": k, "presentation": presentation,
                 "seed": seed, "mixed_support": mixed_support, "scale": scale})


def source_document(case):
    def dyadic(program):
        return {"width": program.width, "k": program.k,
                "gates": [[gate.name, list(gate.wires), None if gate.angle is None else
                           [Fraction(gate.angle).numerator, Fraction(gate.angle).denominator]]
                          for gate in program.gates]}
    return {"left": dyadic(case.left), "right": dyadic(case.right),
            "dephaser": [case.dephaser.data, case.dephaser.ancillas,
                         [[op.kind, list(op.qubits), op.outcome] for op in case.dephaser.ops]],
            "support": [case.support.width, case.support.offset, list(case.support.columns)]}
