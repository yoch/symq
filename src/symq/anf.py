"""Exact algebraic normal forms over the Boolean ring GF(2)[x]/(x²-x)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ANF:
    """Set of monomial masks; the empty set is zero and mask 0 is one.

    Variables are indexed from 0. Multiplication uses idempotence (x_i²=x_i);
    coefficients are reduced modulo two.
    """

    terms: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.terms, frozenset):
            # ``frozen=True`` only blocks attribute assignment: a plain set would stay
            # mutable and break canonicity, so it is coerced here.
            object.__setattr__(self, "terms", frozenset(self.terms))
        if any(not isinstance(m, int) or isinstance(m, bool) or m < 0 for m in self.terms):
            raise ValueError("monomial masks must be nonnegative integers")

    @classmethod
    def from_terms(cls, terms: Iterable[int]) -> ANF:
        """Construct from a stream with parity cancellation of duplicates."""
        out: set[int] = set()
        for mask in terms:
            if not isinstance(mask, int) or mask < 0:
                raise ValueError("monomial masks must be nonnegative integers")
            if mask in out:
                out.remove(mask)
            else:
                out.add(mask)
        return cls(frozenset(out))

    @classmethod
    def constant(cls, value: int | bool) -> ANF:
        if value not in (0, 1):
            raise ValueError("Boolean constant required")
        return cls(frozenset({0}) if value else frozenset())

    @classmethod
    def variable(cls, index: int) -> ANF:
        if not isinstance(index, int) or index < 0:
            raise ValueError("variable index must be a nonnegative integer")
        return cls(frozenset({1 << index}))

    def __xor__(self, other: ANF) -> ANF:
        if not isinstance(other, ANF):
            return NotImplemented
        return ANF(self.terms ^ other.terms)

    def __add__(self, other: ANF) -> ANF:
        return self ^ other

    def __mul__(self, other: ANF) -> ANF:
        if not isinstance(other, ANF):
            return NotImplemented
        result: set[int] = set()
        for left in self.terms:
            for right in other.terms:
                product = left | right
                if product in result:
                    result.remove(product)
                else:
                    result.add(product)
        return ANF(frozenset(result))

    def evaluate(self, assignment: int) -> int:
        if not isinstance(assignment, int) or assignment < 0:
            raise ValueError("assignment must be a nonnegative integer bitmask")
        parity = 0
        for monomial in self.terms:
            parity ^= int((monomial & assignment) == monomial)
        return parity

    @property
    def degree(self) -> int:
        return max((m.bit_count() for m in self.terms), default=0)

    @property
    def support(self) -> frozenset[int]:
        return frozenset(i for m in self.terms for i in range(m.bit_length()) if m & (1 << i))
