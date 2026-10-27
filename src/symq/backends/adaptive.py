"""Exact selection between sparse monomial sets and ZDDs, with conversion accounting.

Values are Python sets (sparse) or ZDD node ids (``int``) of one shared manager. All
decisions are exact: limits raise :class:`~symq.ResourceLimitExceeded` instead of falling
back to an approximation.
"""
from __future__ import annotations

import time
from collections.abc import Sequence

from ..anf import ANF
from ..resources import Guard
from .base import Algebra
from .sparse import SparseAlgebra
from .zdd import ZDDAlgebra

Value = set[int] | int


class MixedSparseZDD(Algebra[Value]):
    """Value operations shared by the selectors; subclasses choose representations in
    :meth:`apply_mcx`."""

    def __init__(
        self, width: int, guard: Guard | None = None, *, zdd_order: Sequence[int] | None = None
    ) -> None:
        super().__init__(width, guard)
        self.sparse = SparseAlgebra(width, self.guard)
        self.zdd = ZDDAlgebra(width, self.guard, order=zdd_order)
        self.sparse.stats = self.zdd.stats = self.stats

    def to_zdd(self, value: Value) -> int:
        if isinstance(value, int):
            return value
        started = time.perf_counter()
        node = self.zdd.from_terms(value)
        self._account(len(value), started)
        return node

    def to_sparse(self, value: Value) -> set[int]:
        if isinstance(value, set):
            return value
        started = time.perf_counter()
        terms = set(self.zdd.to_anf(value).terms)
        self._account(len(terms), started)
        return terms

    def _account(self, terms: int, started: float) -> None:
        self.stats.conversions += 1
        self.stats.conversion_terms += terms
        self.stats.conversion_seconds += time.perf_counter() - started

    @staticmethod
    def _explicit_product_exceeds(factors: Sequence[Value], bound: int) -> bool:
        estimate = 1
        for factor in factors:
            if not isinstance(factor, set):
                return True
            estimate *= len(factor)
            if estimate > bound:
                return True
        return False

    def variable(self, index: int) -> Value:
        return self.sparse.variable(index)

    def one(self) -> Value:
        return self.sparse.one()

    def zero(self) -> Value:
        return self.sparse.zero()

    def xor(self, left: Value, right: Value) -> Value:
        if isinstance(left, set) and isinstance(right, set):
            return self.sparse.xor(left, right)
        return self.zdd.xor(self.to_zdd(left), self.to_zdd(right))

    def ixor(self, left: Value, right: Value) -> Value:
        if isinstance(left, set) and isinstance(right, set):
            return self.sparse.ixor(left, right)
        return self.zdd.xor(self.to_zdd(left), self.to_zdd(right))

    def product(self, factors: Sequence[Value]) -> Value:
        if all(isinstance(f, set) for f in factors):
            return self.sparse.product(factors)
        return self.zdd.product([self.to_zdd(f) for f in factors])

    def equal(self, left: Value, right: Value) -> bool:
        if isinstance(left, set) and isinstance(right, set):
            return left == right
        return self.to_zdd(left) == self.to_zdd(right)

    def is_zero(self, value: Value) -> bool:
        return not value if isinstance(value, set) else value == 0

    def terms(self, value: Value) -> int:
        return len(value) if isinstance(value, set) else self.zdd.terms(value)

    def to_anf(self, value: Value) -> ANF:
        return self.sparse.to_anf(value) if isinstance(value, set) else self.zdd.to_anf(value)

    def from_anf(self, anf: ANF) -> Value:
        return self.sparse.from_anf(anf)

    def min_monomial(self, value: Value) -> int | None:
        if isinstance(value, set):
            return self.sparse.min_monomial(value)
        return self.zdd.min_monomial(value)


class WireAdaptiveAlgebra(MixedSparseZDD):
    """Per-wire selection.

    A gate is evaluated on ZDDs when a control is already a ZDD or when the product of the
    control term counts (an upper bound on the explicit product) exceeds
    ``product_threshold``; those controls are then promoted so each conversion is paid once.
    A sparse target is promoted once it holds more than ``promote_threshold`` terms. ZDD
    wires are never demoted, which rules out conversion thrashing.
    """

    name = "adaptive-wire"

    def __init__(
        self,
        width: int,
        guard: Guard | None = None,
        *,
        product_threshold: int = 4096,
        promote_threshold: int = 2048,
        zdd_order: Sequence[int] | None = None,
    ) -> None:
        super().__init__(width, guard, zdd_order=zdd_order)
        if product_threshold < 1 or promote_threshold < 1:
            raise ValueError("thresholds must be positive")
        self.product_threshold = product_threshold
        self.promote_threshold = promote_threshold

    def apply_mcx(self, state: list[Value], controls: Sequence[int], target: int) -> None:
        factors = [state[c] for c in controls]
        if not self._explicit_product_exceeds(factors, self.product_threshold):
            control: Value = self.sparse.product(factors) if factors else self.sparse.one()
        else:
            for c in controls:
                state[c] = self.to_zdd(state[c])
            control = self.zdd.product([state[c] for c in controls])
        current = state[target]
        if isinstance(current, set):
            if isinstance(control, int):
                if len(current) + self.zdd.terms(control) > self.promote_threshold:
                    state[target] = self.zdd.xor(self.to_zdd(current), control)
                    return
                control = self.to_sparse(control)
            updated = self.sparse.ixor(current, control)
            state[target] = (
                self.to_zdd(updated) if len(updated) > self.promote_threshold else updated
            )
        else:
            state[target] = self.zdd.xor(current, self.to_zdd(control))


class AutoZDDAlgebra(MixedSparseZDD):
    """Reconstruction of the archived ``auto_zdd`` policy (not its code).

    In-place sparse evaluation, then an irreversible switch of the *whole* state to ZDDs
    once a nonlinear gate (two or more controls) leaves at least ``switch_terms`` monomials
    on its target, or before a product whose explicit size bound exceeds ``product_bound``.
    The archived threshold 850 was tuned on the five DEV circuits only.
    """

    name = "auto-zdd"

    def __init__(
        self,
        width: int,
        guard: Guard | None = None,
        *,
        switch_terms: int = 850,
        product_bound: int = 1 << 16,
        zdd_order: Sequence[int] | None = None,
    ) -> None:
        super().__init__(width, guard, zdd_order=zdd_order)
        if switch_terms < 1 or product_bound < 1:
            raise ValueError("thresholds must be positive")
        self.switch_terms = switch_terms
        self.product_bound = product_bound
        self.switch_gate: int | None = None
        """Index (in this algebra's gate count) of the gate that triggered the last switch."""

    def _switch(self, state: list[Value]) -> None:
        self.switch_gate = self.stats.gates
        for i, value in enumerate(state):
            state[i] = self.to_zdd(value)

    def apply_mcx(self, state: list[Value], controls: Sequence[int], target: int) -> None:
        if isinstance(state[target], set):
            factors = [state[c] for c in controls]
            if not self._explicit_product_exceeds(factors, self.product_bound):
                control = self.sparse.product(factors) if factors else self.sparse.one()
                updated = self.sparse.ixor(state[target], control)
                state[target] = updated
                if len(controls) >= 2 and len(updated) >= self.switch_terms:
                    self._switch(state)
                return
            self._switch(state)
        control_node = self.zdd.product([state[c] for c in controls]) if controls else 1
        state[target] = self.zdd.xor(state[target], control_node)
