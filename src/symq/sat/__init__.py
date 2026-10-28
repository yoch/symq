"""Optional SAT decision engine for reversible-circuit equivalence.

This package is a **decision engine**, not a representation: it answers "are these two circuits
equivalent, and if not here is a checked counterexample", and it never exports an ANF. That is why
it does not implement ``Algebra``; forcing it into that interface would promise polynomial exports
it cannot deliver.

``python-sat`` is an optional dependency. Without it, :func:`available` returns ``False`` and
:func:`check_equivalence_sat` raises :class:`SatUnavailable`; the symbolic engine is untouched.
"""
from __future__ import annotations

from .encoding import Contract, Encoder, SatUnavailable, SatVerdict, solver_available
from .miter import Miter, build_miter, check_sat_equivalence, observed_pairs


def available() -> bool:
    return solver_available()


def versions() -> dict[str, str]:
    """The solver actually used, so a result can be attributed to a version."""
    try:
        import pysat
        from pysat.solvers import Cadical195
    except Exception:  # noqa: BLE001
        return {}
    del Cadical195
    return {"python-sat": getattr(pysat, "__version__", "unknown")}


check_equivalence_sat = check_sat_equivalence

__all__ = [
    "Contract",
    "Encoder",
    "Miter",
    "SatUnavailable",
    "SatVerdict",
    "available",
    "build_miter",
    "check_equivalence_sat",
    "check_sat_equivalence",
    "observed_pairs",
    "versions",
]
