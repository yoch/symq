"""Dense truth tables as Python integers: an oracle that shares no code with ANF products.

Bit ``x`` of a value is the function evaluated at assignment ``x`` (LSB-first variables).
Memory is ``2**width`` bits per wire, so the width is explicitly capped.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..anf import ANF
from ..resources import Guard, ResourceLimitExceeded
from .base import Algebra

DEFAULT_MAX_WIDTH = 18


class TruthTableAlgebra(Algebra[int]):
    name = "truthtable"

    def __init__(
        self, width: int, guard: Guard | None = None, *, max_width: int = DEFAULT_MAX_WIDTH
    ) -> None:
        super().__init__(width, guard)
        if width > max_width:
            raise ResourceLimitExceeded("width", max_width, width)
        size = 1 << width
        self._full = (1 << size) - 1
        self._vars = []
        for i in range(width):
            block = 1 << i
            period = (1 << (2 * block)) - 1
            ones = ((1 << block) - 1) << block
            self._vars.append(self._full // period * ones)

    def variable(self, index: int) -> int:
        return self._vars[self._check_variable(index)]

    def one(self) -> int:
        return self._full

    def zero(self) -> int:
        return 0

    def xor(self, left: int, right: int) -> int:
        return left ^ right

    def product(self, factors: Sequence[int]) -> int:
        self.stats.products += 1
        result = self._full
        for factor in factors:
            result &= factor
        return result

    def equal(self, left: int, right: int) -> bool:
        return left == right

    def is_zero(self, value: int) -> bool:
        return value == 0

    def terms(self, value: int) -> None:
        return None

    def _moebius(self, value: int) -> int:
        """Binary Möbius transform (an involution) between truth table and ANF coefficients."""
        for i, var in enumerate(self._vars):
            value ^= (value & (self._full ^ var)) << (1 << i)
        return value

    def to_anf(self, value: int) -> ANF:
        coefficients = self._moebius(value)
        self.guard.check_terms(coefficients.bit_count())
        out = []
        while coefficients:
            low = coefficients & -coefficients
            out.append(low.bit_length() - 1)
            coefficients ^= low
        return ANF(frozenset(out))

    def from_anf(self, anf: ANF) -> int:
        self._check_anf_width(anf)
        coefficients = 0
        for monomial in anf.terms:
            coefficients |= 1 << monomial
        return self._moebius(coefficients)
