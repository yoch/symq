"""PolyBoRi (BRiAl) adapter: the same Boolean ring as symq, implemented natively with ZDDs.

``BooleanPolynomialRing`` is exactly GF(2)[x_0..x_{n-1}]/(x_i^2 - x_i), so values, XOR,
products and equality match symq's ANF one to one. Requires ``passagemath-brial``.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sage.all__sagemath_brial import BooleanPolynomialRing

from ..anf import ANF
from ..backends.base import Algebra
from ..resources import Guard

Poly = Any


class PolyBoRiAlgebra(Algebra[Poly]):
    """Values are ``BooleanPolynomial``; the monomial order is ``lp`` (lexicographic)."""

    name = "polybori"

    def __init__(self, width: int, guard: Guard | None = None) -> None:
        super().__init__(width, guard)
        self.ring = BooleanPolynomialRing(width, "x", order="lp")
        self._gens = self.ring.gens()

    def variable(self, index: int) -> Poly:
        return self._gens[index]

    def one(self) -> Poly:
        return self.ring.one()

    def zero(self) -> Poly:
        return self.ring.zero()

    def xor(self, left: Poly, right: Poly) -> Poly:
        return left + right

    def product(self, factors: Sequence[Poly]) -> Poly:
        self.stats.products += 1
        result = self.ring.one()
        for factor in factors:
            result = result * factor
            if result.is_zero():
                break
        self.guard.check_terms(len(result))
        return result

    def equal(self, left: Poly, right: Poly) -> bool:
        return left == right

    def is_zero(self, value: Poly) -> bool:
        return value.is_zero()

    def terms(self, value: Poly) -> int:
        return len(value)

    def to_anf(self, value: Poly) -> ANF:
        self.guard.check_terms(len(value))
        return ANF(frozenset(
            sum(1 << index for index in monomial.iterindex()) for monomial in value.terms()
        ))

    def from_anf(self, anf: ANF) -> Poly:
        self._check_anf_width(anf)
        result = self.ring.zero()
        for mask in anf.terms:
            monomial = self.ring.one()
            for index in range(mask.bit_length()):
                if mask >> index & 1:
                    monomial = monomial * self._gens[index]
            result = result + monomial
        return result

    def native_nodes(self, values: Sequence[Poly]) -> int:
        """Sum of the ZDD node counts of ``values`` (shared nodes counted per value)."""
        return sum(value.n_nodes() for value in values)
