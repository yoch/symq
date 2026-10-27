"""Unoptimized reference backend built directly on the immutable :class:`~symq.ANF`."""
from __future__ import annotations

from collections.abc import Sequence

from ..anf import ANF
from .base import Algebra


class ReferenceAlgebra(Algebra[ANF]):
    name = "reference"

    def variable(self, index: int) -> ANF:
        return ANF.variable(self._check_variable(index))

    def one(self) -> ANF:
        return ANF.constant(1)

    def zero(self) -> ANF:
        return ANF()

    def xor(self, left: ANF, right: ANF) -> ANF:
        result = left ^ right
        self.guard.check_terms(len(result.terms))
        return result

    def product(self, factors: Sequence[ANF]) -> ANF:
        self.stats.products += 1
        result = self.one()
        for factor in factors:
            self.guard.check_time()
            result = result * factor
            self.guard.check_terms(len(result.terms))
        return result

    def equal(self, left: ANF, right: ANF) -> bool:
        return left == right

    def is_zero(self, value: ANF) -> bool:
        return not value.terms

    def terms(self, value: ANF) -> int:
        return len(value.terms)

    def to_anf(self, value: ANF) -> ANF:
        return value

    def from_anf(self, anf: ANF) -> ANF:
        self._check_anf_width(anf)
        return anf
