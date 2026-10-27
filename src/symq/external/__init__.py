"""Adapters to native tools, used only as comparison baselines (optional dependencies).

Install with ``pip install -e ".[external]"``. Each adapter is imported independently: a
missing tool leaves the others usable and is recorded in ``UNAVAILABLE``.

- ``polybori``: PolyBoRi/BRiAl, the same Boolean ring natively (``Algebra``).
- ``cudd-bdd`` and ``cudd-zdd``: CUDD Boolean functions as BDDs or ZDDs (``Algebra``).
- ``qcec``: MQT QCEC equivalence checking (verdicts only, ``qcec_check``).
"""
from __future__ import annotations

from importlib import metadata
from typing import Any

from ..backends.base import Algebra

EXTERNAL_BACKENDS: dict[str, type[Algebra[Any]]] = {}
UNAVAILABLE: dict[str, str] = {}
DISTRIBUTIONS = ("passagemath-brial", "dd", "mqt.qcec", "mqt.core")

try:
    from .polybori import PolyBoRiAlgebra
except ImportError as error:
    UNAVAILABLE["polybori"] = f"{type(error).__name__}: {error}"
else:
    EXTERNAL_BACKENDS[PolyBoRiAlgebra.name] = PolyBoRiAlgebra

try:
    from .cudd import CuddBDDAlgebra, CuddZDDAlgebra
except ImportError as error:
    UNAVAILABLE["cudd-bdd"] = UNAVAILABLE["cudd-zdd"] = f"{type(error).__name__}: {error}"
else:
    EXTERNAL_BACKENDS[CuddBDDAlgebra.name] = CuddBDDAlgebra
    EXTERNAL_BACKENDS[CuddZDDAlgebra.name] = CuddZDDAlgebra

try:
    from .qcec import CONFIGURATION as QCEC_CONFIGURATION
    from .qcec import qcec_check, to_quantum_computation
except ImportError as error:
    UNAVAILABLE["qcec"] = f"{type(error).__name__}: {error}"
    QCEC_CONFIGURATION = None
    qcec_check = to_quantum_computation = None


def versions() -> dict[str, str | None]:
    """Installed versions of the native tools' distributions (``None`` if absent)."""
    found: dict[str, str | None] = {}
    for name in DISTRIBUTIONS:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = None
    return found


__all__ = [
    "EXTERNAL_BACKENDS",
    "QCEC_CONFIGURATION",
    "UNAVAILABLE",
    "qcec_check",
    "to_quantum_computation",
    "versions",
]
