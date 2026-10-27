"""Degree-≤2 ANF packed into one integer (combinatorial number system), and an exact
sparse fallback. Reconstructions of the archived ``packed_only`` and ``adaptive`` policies.

Bit 0 is the constant monomial, bit ``1 + i`` is ``x_i`` and bit ``1 + n + j(j-1)/2 + i``
is ``x_i x_j`` for ``i < j``. Bit order therefore follows degree, so the lowest set bit is
a minimum-degree monomial.
"""
from __future__ import annotations

import time
from collections.abc import Sequence

from ..anf import ANF
from ..resources import Guard, ResourceLimitExceeded
from .base import Algebra
from .sparse import SparseAlgebra

MAX_DEGREE = 2


class PackedAlgebra(Algebra[int]):
    """Refuses (``ResourceLimitExceeded("degree")``) any value of degree above two."""

    name = "packed"

    def __init__(self, width: int, guard: Guard | None = None) -> None:
        super().__init__(width, guard)
        self._monomial = [0] + [1 << i for i in range(width)]
        for j in range(width):
            self._monomial.extend((1 << i) | (1 << j) for i in range(j))
        self._index = {m: k for k, m in enumerate(self._monomial)}

    def encode(self, terms: set[int] | frozenset[int]) -> int:
        out = 0
        for monomial in terms:
            index = self._index.get(monomial)
            if index is None:
                raise ResourceLimitExceeded("degree", MAX_DEGREE, monomial.bit_count())
            out |= 1 << index
        return out

    def decode(self, value: int) -> set[int]:
        out = set()
        monomial = self._monomial
        while value:
            low = value & -value
            out.add(monomial[low.bit_length() - 1])
            value ^= low
        return out

    def try_product(self, factors: Sequence[int]) -> int | None:
        """``try_product_uncounted``, counting one public product."""
        self.stats.products += 1
        return self.try_product_uncounted(factors)

    def try_product_uncounted(self, factors: Sequence[int]) -> int | None:
        """Exact product, or ``None`` if its degree exceeds two.

        The product is materialised as monomials, so its size is checked against the term
        budget *while* it is built rather than afterwards, and a product with a provably
        higher degree is refused before allocating ``2**k`` masks.
        """
        factors = [f for f in factors if f != 1]
        if not factors:
            return 1
        disjoint = self._disjoint_bounds(factors)
        if disjoint is not None:
            terms, degree = disjoint
            # The explicit intermediate is what the budget protects; report it first.
            self.guard.check_terms(terms)
            if degree > MAX_DEGREE:
                return None
        result = self._multiply(factors)
        if any(m.bit_count() > MAX_DEGREE for m in result):
            return None
        return self.encode(result)

    def _disjoint_bounds(self, factors: Sequence[int]) -> tuple[int, int] | None:
        """Exact (term count, degree) of the product when nothing can cancel.

        Products of monomials coincide only if some variable occurs on both sides, so with
        pairwise disjoint supports every product of one monomial per factor is distinct.
        The bound is then exact; a zero factor gives the zero product. ``None`` means the
        product has to be computed, and only its materialised size can be checked.
        """
        seen = 0
        terms = 1
        degree = 0
        for factor in factors:
            monomials = self.decode(factor)
            if not monomials:
                return 0, 0
            support = 0
            for monomial in monomials:
                support |= monomial
            if support & seen:
                return None
            seen |= support
            terms *= len(monomials)
            degree += max(m.bit_count() for m in monomials)
        return terms, degree

    def _multiply(self, factors: Sequence[int]) -> set[int]:
        guard = self.guard
        result = {0}
        for factor in factors:
            if factor == 1:
                continue
            terms = self.decode(factor)
            nxt: set[int] = set()
            for t in result:
                for u in terms:
                    p = t | u
                    if p in nxt:
                        nxt.remove(p)
                    else:
                        nxt.add(p)
            result = nxt
            if not result:
                break
            # Checked while building, not afterwards: this is an explicit intermediate and
            # the budget must stop it before it grows beyond the limit.
            guard.check_terms(len(result))
            guard.check_time()
        return result

    def variable(self, index: int) -> int:
        return 1 << (1 + self._check_variable(index))

    def one(self) -> int:
        return 1

    def zero(self) -> int:
        return 0

    def xor(self, left: int, right: int) -> int:
        return left ^ right

    def product(self, factors: Sequence[int]) -> int:
        self.stats.products += 1
        if any(m.bit_count() > MAX_DEGREE for f in factors for m in self.decode(f)):
            degree = max((m.bit_count() for f in factors for m in self.decode(f)), default=0)
            raise ResourceLimitExceeded("degree", MAX_DEGREE, degree)
        disjoint = self._disjoint_bounds(factors)
        if disjoint is not None:
            terms, bound = disjoint
            self.guard.check_terms(terms)
            if bound > MAX_DEGREE:
                raise ResourceLimitExceeded("degree", MAX_DEGREE, bound)
        result = self._multiply(factors)
        degree = max((m.bit_count() for m in result), default=0)
        if degree > MAX_DEGREE:
            raise ResourceLimitExceeded("degree", MAX_DEGREE, degree)
        return self.encode(result)

    def equal(self, left: int, right: int) -> bool:
        return left == right

    def is_zero(self, value: int) -> bool:
        return value == 0

    def terms(self, value: int) -> int:
        return value.bit_count()

    def to_anf(self, value: int) -> ANF:
        return ANF(frozenset(self.decode(value)))

    def from_anf(self, anf: ANF) -> int:
        self._check_anf_width(anf)
        return self.encode(anf.terms)

    def min_monomial(self, value: int) -> int | None:
        if not value:
            return None
        return self._monomial[(value & -value).bit_length() - 1]


class PackedFallbackAlgebra(Algebra[int | set[int]]):
    """Packed degree-≤2 wires (``int``) with an exact per-gate sparse fallback (``set``).

    A gate whose product exceeds degree two is evaluated sparsely and the target wire turns
    sparse; any sparse target whose degree drops back to two is demoted to packed again.
    These round trips are counted as conversions.
    """

    name = "packed-fallback"

    def __init__(self, width: int, guard: Guard | None = None) -> None:
        super().__init__(width, guard)
        self.packed = PackedAlgebra(width, self.guard)
        self.sparse = SparseAlgebra(width, self.guard)
        self.packed.stats = self.sparse.stats = self.stats

    def to_sparse(self, value: int | set[int]) -> set[int]:
        if isinstance(value, set):
            return value
        started = time.perf_counter()
        terms = self.packed.decode(value)
        self._account(len(terms), started)
        return terms

    def _maybe_pack(self, value: set[int]) -> int | set[int]:
        if any(m.bit_count() > MAX_DEGREE for m in value):
            return value
        started = time.perf_counter()
        packed = self.packed.encode(value)
        self._account(len(value), started)
        return packed

    def _account(self, terms: int, started: float) -> None:
        self.stats.conversions += 1
        self.stats.conversion_terms += terms
        self.stats.conversion_seconds += time.perf_counter() - started

    def apply_mcx(
        self, state: list[int | set[int]], controls: Sequence[int], target: int
    ) -> None:
        factors = [state[c] for c in controls]
        current = state[target]
        # Count the gate's product exactly once: the packed and sparse helpers below are
        # recursive sub-operations and must not increment the shared counter.
        if all(isinstance(f, int) for f in factors):
            self.stats.products += 1
            control = self.packed.try_product_uncounted(factors)
            if control is not None and isinstance(current, int):
                state[target] = current ^ control
                return
        else:
            control = None
        if control is None:
            control = self.sparse.product_uncounted([self.to_sparse(f) for f in factors])
        updated = self.sparse.ixor(self.to_sparse(current), self.to_sparse(control))
        state[target] = self._maybe_pack(updated)

    def variable(self, index: int) -> int:
        return self.packed.variable(index)

    def one(self) -> int:
        return 1

    def zero(self) -> int:
        return 0

    def xor(self, left: int | set[int], right: int | set[int]) -> int | set[int]:
        if isinstance(left, int) and isinstance(right, int):
            return left ^ right
        return self._maybe_pack(self.sparse.xor(self.to_sparse(left), self.to_sparse(right)))

    def product(self, factors: Sequence[int | set[int]]) -> int | set[int]:
        self.stats.products += 1
        if all(isinstance(f, int) for f in factors):
            result = self.packed.try_product_uncounted(factors)
            if result is not None:
                return result
        sparse = self.sparse.product_uncounted([self.to_sparse(f) for f in factors])
        return self._maybe_pack(sparse)

    def equal(self, left: int | set[int], right: int | set[int]) -> bool:
        if isinstance(left, int) and isinstance(right, int):
            return left == right
        return self.to_sparse(left) == self.to_sparse(right)

    def is_zero(self, value: int | set[int]) -> bool:
        return not value

    def terms(self, value: int | set[int]) -> int:
        return value.bit_count() if isinstance(value, int) else len(value)

    def to_anf(self, value: int | set[int]) -> ANF:
        return ANF(frozenset(value if isinstance(value, set) else self.packed.decode(value)))

    def from_anf(self, anf: ANF) -> int | set[int]:
        self._check_anf_width(anf)
        return self._maybe_pack(set(anf.terms))

    def min_monomial(self, value: int | set[int]) -> int | None:
        if isinstance(value, int):
            return self.packed.min_monomial(value)
        return self.sparse.min_monomial(value)
