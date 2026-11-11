"""Interchangeable exact backends for symbolic simulation of reversible circuits."""
from __future__ import annotations

from typing import Any

from .._native_hint import native_core_hint
from ..resources import Budget
from .adaptive import AutoZDDAlgebra, MixedSparseZDD, WireAdaptiveAlgebra
from .base import Algebra, Stats, simulate
from .linear import LinearAlgebra
from .packed import PackedAlgebra, PackedFallbackAlgebra
from .reference import ReferenceAlgebra
from .sparse import SparseAlgebra, SparseCopyAlgebra
from .truthtable import TruthTableAlgebra
from .zdd import ZDDAlgebra

NATIVE_IMPORT_ERROR: str | None = None
"""Why the optional C core could not be imported (``None`` when it is available).

A stale in-place build and a missing build are different problems with different fixes, so the
original ``ImportError`` message is kept instead of being swallowed."""

try:  # the C core is optional; without it the pure-Python zdd backend is unaffected
    from .zdd_native import NativeZDDAlgebra, NativeZDDWideAlgebra
except ImportError as _error:  # pragma: no cover - depends on the toolchain
    NativeZDDAlgebra = None  # type: ignore[assignment,misc]
    NativeZDDWideAlgebra = None  # type: ignore[assignment,misc]
    NATIVE_IMPORT_ERROR = str(_error)
    del _error

_CORE: tuple[type[Algebra[Any]], ...] = (
    ReferenceAlgebra,
    SparseCopyAlgebra,
    SparseAlgebra,
    ZDDAlgebra,
    WireAdaptiveAlgebra,
    AutoZDDAlgebra,
    PackedAlgebra,
    PackedFallbackAlgebra,
    TruthTableAlgebra,
    LinearAlgebra,
)
if NativeZDDAlgebra is not None:
    _CORE += (NativeZDDAlgebra, NativeZDDWideAlgebra)

BACKENDS: dict[str, type[Algebra[Any]]] = {cls.name: cls for cls in _CORE}


def has_native() -> bool:
    """Return True if the native C backend ('zdd-native') is compiled and available."""
    return NativeZDDAlgebra is not None


def make_algebra(
    name: str | type[Algebra[Any]], width: int, budget: Budget | None = None, **options: Any
) -> Algebra[Any]:
    """Instantiate a registered backend, or an ``Algebra`` subclass passed directly (for
    example an adapter from ``symq.external``); the budget clock starts now."""
    if isinstance(name, type) and issubclass(name, Algebra):
        cls = name
    else:
        try:
            cls = BACKENDS[name]
        except KeyError:
            if name in {"zdd-native", "zdd-native-wide"}:
                reason = NATIVE_IMPORT_ERROR or "not registered in this process"
                hint = native_core_hint()
                raise ValueError(
                    f"unknown backend {name!r}: the native C extension is not installed or could "
                    f"not be loaded ({reason}). "
                    # The import error usually carries the advice already: say it once.
                    + ("" if hint in reason else f"To get it: {hint}. ")
                    + f"Available backends: {sorted(BACKENDS)}"
                ) from None
            raise ValueError(
                f"unknown backend {name!r}; choose from {sorted(BACKENDS)}"
            ) from None
    return cls(width, (budget or Budget()).start(), **options)


__all__ = [
    "BACKENDS",
    "NATIVE_IMPORT_ERROR",
    "Algebra",
    "AutoZDDAlgebra",
    "LinearAlgebra",
    "MixedSparseZDD",
    "NativeZDDAlgebra",
    "NativeZDDWideAlgebra",
    "PackedAlgebra",
    "PackedFallbackAlgebra",
    "ReferenceAlgebra",
    "SparseAlgebra",
    "SparseCopyAlgebra",
    "Stats",
    "TruthTableAlgebra",
    "WireAdaptiveAlgebra",
    "ZDDAlgebra",
    "has_native",
    "make_algebra",
    "simulate",
]
