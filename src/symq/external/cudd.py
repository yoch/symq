"""CUDD adapters through ``dd``: Boolean functions as BDDs or as (function) ZDDs.

These managers represent the same Boolean functions as symq's ANF, so XOR (``apply("xor")``),
products (conjunction) and canonical equality match. They store Shannon cofactors, not
monomials: the monomial count is not available, and ``to_anf`` performs a Reed–Muller
transform that is only meant for verification and witnesses.

CUDD's monomial-family operations (``Cudd_zddProduct`` and related) are unate products of
covers without parity cancellation, so CUDD offers no native ANF ring.
Requires ``dd`` built with CUDD.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from dd import cudd, cudd_zdd

from ..anf import ANF
from ..backends.base import Algebra
from ..resources import Guard

Node = Any


class _CuddAlgebra(Algebra[Node]):
    manager_class: ClassVar[type]

    def __init__(self, width: int, guard: Guard | None = None, *, reordering: bool = True) -> None:
        super().__init__(width, guard)
        self.manager = self.manager_class()
        self._names = [f"x{i}" for i in range(width)]
        self.manager.declare(*self._names)
        self.manager.configure(reordering=reordering)
        self.reordering = reordering
        self._index = {name: i for i, name in enumerate(self._names)}

    def variable(self, index: int) -> Node:
        return self.manager.var(self._names[index])

    def one(self) -> Node:
        return self.manager.true

    def zero(self) -> Node:
        return self.manager.false

    def xor(self, left: Node, right: Node) -> Node:
        return self.manager.apply("xor", left, right)

    def product(self, factors: Sequence[Node]) -> Node:
        self.stats.products += 1
        result = self.manager.true
        for factor in factors:
            result = result & factor
            if result == self.manager.false:
                break
        self.guard.check_nodes(len(self.manager))
        return result

    def equal(self, left: Node, right: Node) -> bool:
        return left == right

    def is_zero(self, value: Node) -> bool:
        return value == self.manager.false

    def terms(self, value: Node) -> None:
        return None

    def to_anf(self, value: Node) -> ANF:
        """Reed–Muller transform f = f|x=0 + x (f|x=0 + f|x=1), memoised per node."""
        manager, false = self.manager, self.manager.false
        memo: dict[int, frozenset[int]] = {}

        def transform(node: Node) -> frozenset[int]:
            if node == false:
                return frozenset()
            key = int(node)
            cached = memo.get(key)
            if cached is None:
                self.guard.check_time()
                # dd.cudd_zdd may return a TRUE that differs from ``manager.true`` after a
                # partial ``let``, and ``node.var`` need not be in the support: expand on the
                # support instead.
                support = manager.support(node)
                if not support:
                    return frozenset({0})
                name = min(support, key=self._index.__getitem__)
                low = transform(manager.let({name: False}, node))
                high = transform(manager.let({name: True}, node))
                bit = 1 << self._index[name]
                cached = low ^ frozenset(m | bit for m in low ^ high)
                self.guard.check_terms(len(cached))
                memo[key] = cached
            return cached

        manager.configure(reordering=False)
        try:
            return ANF(transform(value))
        finally:
            manager.configure(reordering=self.reordering)

    def from_anf(self, anf: ANF) -> Node:
        self._check_anf_width(anf)
        result = self.manager.false
        for mask in anf.terms:
            monomial = self.manager.true
            for index in range(mask.bit_length()):
                if mask >> index & 1:
                    monomial = monomial & self.variable(index)
            result = self.xor(result, monomial)
        return result

    def native_nodes(self, values: Sequence[Node]) -> int:
        """Sum of the DAG sizes of ``values`` (shared nodes counted per value)."""
        return sum(value.dag_size for value in values)


class CuddBDDAlgebra(_CuddAlgebra):
    """CUDD BDD (``dd.cudd``), dynamic reordering enabled by default as in CUDD."""

    name = "cudd-bdd"
    manager_class = cudd.BDD


class CuddZDDAlgebra(_CuddAlgebra):
    """CUDD ZDD of the family of satisfying assignments (``dd.cudd_zdd``), not of monomials."""

    name = "cudd-zdd"
    manager_class = cudd_zdd.ZDD

    def to_anf(self, value: Node) -> ANF:
        """Möbius transform of the satisfying-assignment family, read from ``succ``.

        A skipped level means the variable is 0, which multiplies the transform by (1 + y).
        ``let`` is avoided: after a partial ``let``, dd.cudd_zdd can return constants that
        differ from ``manager.true``/``manager.false``.
        """
        manager, false = self.manager, self.manager.false
        bottom = self.width
        memo: dict[int, frozenset[int]] = {}

        def level_of(node: Node) -> int:
            level = manager.succ(node)[0]
            return min(level, bottom)

        def lift(terms: frozenset[int], start: int, stop: int) -> frozenset[int]:
            for level in range(start, stop):
                bit = 1 << self._index[manager.var_at_level(level)]
                terms = terms | frozenset(m | bit for m in terms)
            self.guard.check_terms(len(terms))
            return terms

        def transform(node: Node) -> frozenset[int]:
            if node == false:
                return frozenset()
            key = int(node)
            cached = memo.get(key)
            if cached is None:
                self.guard.check_time()
                level, low, high = manager.succ(node)
                if level >= bottom:
                    cached = frozenset({0})
                else:
                    low_terms = lift(transform(low), level + 1, level_of(low))
                    high_terms = lift(transform(high), level + 1, level_of(high))
                    bit = 1 << self._index[manager.var_at_level(level)]
                    cached = low_terms | frozenset(m | bit for m in low_terms ^ high_terms)
                    self.guard.check_terms(len(cached))
                memo[key] = cached
            return cached

        manager.configure(reordering=False)
        try:
            if value == false:
                return ANF()
            return ANF(lift(transform(value), 0, level_of(value)))
        finally:
            manager.configure(reordering=self.reordering)
