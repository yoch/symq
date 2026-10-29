"""Compatibility shim: the sole phase engine lives in installed symq.experimental.phase."""
from symq.experimental.phase import (
    Gate8,
    Poly8,
    Program8,
    Symbolic8,
    Verdict8,
    eval_phase,
    lift_anf,
    symbolic,
)
from symq.experimental.phase import check_equivalence as _check_equivalence

__all__ = [
    "Gate8",
    "Poly8",
    "Program8",
    "Symbolic8",
    "Verdict8",
    "check_equivalence",
    "eval_phase",
    "lift_anf",
    "symbolic",
]


def check_equivalence(left, right, budget=None):
    # Preserve research instrumentation of this module's symbolic entry point.
    return _check_equivalence(left, right, budget, _symbolic=symbolic)
