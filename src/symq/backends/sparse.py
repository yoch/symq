"""Mutable sparse ANF: Python sets of monomial masks with in-place XOR and fast paths."""
from __future__ import annotations

from collections.abc import Sequence

from ..anf import ANF
from .base import Algebra


def _support(terms: set[int]) -> int:
    mask = 0
    for term in terms:
        mask |= term
    return mask


class SparseAlgebra(Algebra[set[int]]):
    """Explicit monomial sets.

    Products multiply the smallest factors first and avoid parity bookkeeping when the
    factors have disjoint supports, where ``t | u`` is injective and cannot cancel.
    """

    name = "sparse"

    def variable(self, index: int) -> set[int]:
        return {1 << self._check_variable(index)}

    def one(self) -> set[int]:
        return {0}

    def zero(self) -> set[int]:
        return set()

    def xor(self, left: set[int], right: set[int]) -> set[int]:
        result = left ^ right
        self.guard.check_terms(len(result))
        return result

    def ixor(self, left: set[int], right: set[int]) -> set[int]:
        left ^= right
        self.guard.check_terms(len(left))
        return left

    def product(self, factors: Sequence[set[int]]) -> set[int]:
        self.stats.products += 1
        return self.product_uncounted(factors)

    def product_uncounted(self, factors: Sequence[set[int]]) -> set[int]:
        """The product without touching ``Stats.products`` (for callers that count their
        own public operation, such as :class:`PackedFallbackAlgebra`)."""
        if not factors:
            return {0}
        ordered = sorted(factors, key=len)
        if not ordered[0]:
            return set()
        result = set(ordered[0])
        for factor in ordered[1:]:
            result = self._multiply(result, factor)
            if not result:
                break
        return result

    def _multiply(self, left: set[int], right: set[int]) -> set[int]:
        guard = self.guard
        guard.check_time()
        if len(left) > len(right):
            left, right = right, left
        if not _support(left) & _support(right):
            guard.check_terms(len(left) * len(right))
            return {t | u for t in left for u in right}
        result: set[int] = set()
        add, remove = result.add, result.remove
        for t in left:
            for u in right:
                p = t | u
                if p in result:
                    remove(p)
                else:
                    add(p)
            guard.check_terms(len(result))
            guard.check_time()
        return result

    def equal(self, left: set[int], right: set[int]) -> bool:
        return left == right

    def is_zero(self, value: set[int]) -> bool:
        return not value

    def terms(self, value: set[int]) -> int:
        return len(value)

    def to_anf(self, value: set[int]) -> ANF:
        return ANF(frozenset(value))

    def from_anf(self, anf: ANF) -> set[int]:
        self._check_anf_width(anf)
        return set(anf.terms)

    def min_monomial(self, value: set[int]) -> int | None:
        return min(value, key=lambda m: (m.bit_count(), m), default=None)


class SparseCopyAlgebra(SparseAlgebra):
    """Ablation of :class:`SparseAlgebra` that copies on every XOR instead of updating."""

    name = "sparse-copy"

    def ixor(self, left: set[int], right: set[int]) -> set[int]:
        return self.xor(left, right)
