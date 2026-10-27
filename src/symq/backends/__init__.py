"""Interchangeable exact backends for symbolic simulation of reversible circuits."""
from __future__ import annotations

from typing import Any

from ..resources import Budget
from .adaptive import AutoZDDAlgebra, MixedSparseZDD, WireAdaptiveAlgebra
from .base import Algebra, Stats, simulate
from .packed import PackedAlgebra, PackedFallbackAlgebra
from .reference import ReferenceAlgebra
from .sparse import SparseAlgebra, SparseCopyAlgebra
from .truthtable import TruthTableAlgebra
from .zdd import ZDDAlgebra

BACKENDS: dict[str, type[Algebra[Any]]] = {
    cls.name: cls
    for cls in (
        ReferenceAlgebra,
        SparseCopyAlgebra,
        SparseAlgebra,
        ZDDAlgebra,
        WireAdaptiveAlgebra,
        AutoZDDAlgebra,
        PackedAlgebra,
        PackedFallbackAlgebra,
        TruthTableAlgebra,
    )
}


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
            raise ValueError(
                f"unknown backend {name!r}; choose from {sorted(BACKENDS)}"
            ) from None
    return cls(width, (budget or Budget()).start(), **options)


__all__ = [
    "BACKENDS",
    "Algebra",
    "AutoZDDAlgebra",
    "MixedSparseZDD",
    "PackedAlgebra",
    "PackedFallbackAlgebra",
    "ReferenceAlgebra",
    "SparseAlgebra",
    "SparseCopyAlgebra",
    "Stats",
    "TruthTableAlgebra",
    "WireAdaptiveAlgebra",
    "ZDDAlgebra",
    "make_algebra",
    "simulate",
]
