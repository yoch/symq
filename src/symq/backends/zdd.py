"""Zero-suppressed decision diagrams for monomial families (ANF as a ZDD).

Node 0 is the empty family (the zero polynomial) and node 1 is ``{∅}`` (the constant one).
Nodes store levels: by default variable ``i`` is level ``i`` (smallest index at the root);
``order`` lists the variables from root to leaves instead. The order changes sizes by
orders of magnitude on real circuits but never results. Hash-consing makes every
polynomial a unique node id within one :class:`ZDDAlgebra`, so equality is ``==``.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..anf import ANF
from ..resources import Guard, ResourceLimitExceeded
from .base import Algebra

_TICK_MASK = 0xFFF
# Recursion depth grows linearly with the number of variables.
MAX_WIDTH = 256


class ZDDAlgebra(Algebra[int]):
    name = "zdd"

    def __init__(
        self,
        width: int,
        guard: Guard | None = None,
        *,
        order: Sequence[int] | None = None,
        cache_limit: int = 1 << 20,
    ) -> None:
        super().__init__(width, guard)
        if width > MAX_WIDTH:
            raise ResourceLimitExceeded("width", MAX_WIDTH, width)
        if cache_limit < 1:
            raise ValueError("cache_limit must be positive")
        self.cache_limit = cache_limit
        self.order = tuple(range(width)) if order is None else tuple(order)
        if sorted(self.order) != list(range(width)):
            raise ValueError("order must be a permutation of the variable indices")
        self._level_of = [0] * width
        for level, variable in enumerate(self.order):
            self._level_of[variable] = level
        self._identity_order = self.order == tuple(range(width))
        self._var = [width, width]
        self._lo = [0, 0]
        self._hi = [0, 0]
        self._unique: dict[tuple[int, int, int], int] = {}
        self._xor_cache: dict[tuple[int, int], int] = {}
        self._mul_cache: dict[tuple[int, int], int] = {}
        self._count: dict[int, int] = {0: 0, 1: 1}
        self._ticks = 0

    @property
    def node_count(self) -> int:
        """Internal nodes ever created (no garbage collection is performed)."""
        return len(self._unique)

    def _tick(self) -> None:
        self._ticks += 1
        if not self._ticks & _TICK_MASK:
            self.guard.check_time()

    def _mk(self, var: int, lo: int, hi: int) -> int:
        if hi == 0:
            return lo
        key = (var, lo, hi)
        node = self._unique.get(key)
        if node is None:
            self.guard.check_nodes(len(self._unique) + 1)
            node = len(self._var)
            self._var.append(var)
            self._lo.append(lo)
            self._hi.append(hi)
            self._unique[key] = node
        return node

    def _remember(self, cache: dict[tuple[int, int], int], key: tuple[int, int], value: int) -> int:
        if len(cache) >= self.cache_limit:
            cache.clear()
        cache[key] = value
        return value

    def _levels(self, mask: int) -> int:
        if self._identity_order:
            return mask
        out = 0
        while mask:
            low = mask & -mask
            out |= 1 << self._level_of[low.bit_length() - 1]
            mask ^= low
        return out

    def _variables(self, levels: int) -> int:
        if self._identity_order:
            return levels
        out = 0
        while levels:
            low = levels & -levels
            out |= 1 << self.order[low.bit_length() - 1]
            levels ^= low
        return out

    def variable(self, index: int) -> int:
        return self._mk(self._level_of[self._check_variable(index)], 0, 1)

    def one(self) -> int:
        return 1

    def zero(self) -> int:
        return 0

    def xor(self, left: int, right: int) -> int:
        if left == 0:
            return right
        if right == 0:
            return left
        if left == right:
            return 0
        if left > right:
            left, right = right, left
        key = (left, right)
        cached = self._xor_cache.get(key)
        if cached is not None:
            return cached
        self._tick()
        var, lo, hi = self._var, self._lo, self._hi
        vl, vr = var[left], var[right]
        if vl == vr:
            result = self._mk(vl, self.xor(lo[left], lo[right]), self.xor(hi[left], hi[right]))
        elif vl < vr:
            result = self._mk(vl, self.xor(lo[left], right), hi[left])
        else:
            result = self._mk(vr, self.xor(left, lo[right]), hi[right])
        return self._remember(self._xor_cache, key, result)

    def multiply(self, left: int, right: int) -> int:
        """Boolean-ring product: with P = P0 + vP1 and Q = Q0 + vQ1, v² = v gives
        PQ = P0Q0 + v(P0Q1 + P1Q0 + P1Q1).

        The alternative recurrence with two recursive products,
        P0Q0 + v((P0 + P1)(Q0 + Q1) + P0Q0), builds the larger cofactor sums and allocated
        238 615 nodes instead of 1 436 on ``rd84_313`` (reversed order). Its high part alone,
        v((P0 + P1)(Q0 + Q1) + P0Q0), is not the product: it drops P0Q0."""
        if left == 0 or right == 0:
            return 0
        if left == 1:
            return right
        if right == 1 or left == right:
            return left
        if left > right:
            left, right = right, left
        key = (left, right)
        cached = self._mul_cache.get(key)
        if cached is not None:
            return cached
        self._tick()
        var, lo, hi = self._var, self._lo, self._hi
        v = min(var[left], var[right])
        l0, l1 = (lo[left], hi[left]) if var[left] == v else (left, 0)
        r0, r1 = (lo[right], hi[right]) if var[right] == v else (right, 0)
        low = self.multiply(l0, r0)
        high = self.xor(
            self.xor(self.multiply(l0, r1), self.multiply(l1, r0)), self.multiply(l1, r1)
        )
        return self._remember(self._mul_cache, key, self._mk(v, low, high))

    def product(self, factors: Sequence[int]) -> int:
        self.stats.products += 1
        result = 1
        for factor in sorted(factors, key=self.terms):
            result = self.multiply(result, factor)
            if result == 0:
                break
        return result

    def equal(self, left: int, right: int) -> bool:
        return left == right

    def is_zero(self, value: int) -> bool:
        return value == 0

    def terms(self, value: int) -> int:
        count = self._count.get(value)
        if count is None:
            count = self.terms(self._lo[value]) + self.terms(self._hi[value])
            self._count[value] = count
        return count

    def size(self, value: int) -> int:
        """Number of internal nodes reachable from ``value``."""
        seen: set[int] = set()
        stack = [value]
        while stack:
            node = stack.pop()
            if node > 1 and node not in seen:
                seen.add(node)
                stack.append(self._lo[node])
                stack.append(self._hi[node])
        return len(seen)

    def reachable_union(self, roots) -> dict[str, int]:
        """Exact live-node count over several roots, marking the identifiers reached.

        ``size`` sums the per-root DAG sizes, which counts a shared node once per root and is
        therefore an **upper** bound on the number of distinct live nodes; the diagram of the
        union of the families is a different diagram and cannot be used at all. This walks the
        DAGs and counts each distinct internal node once.
        """
        seen: set[int] = set()
        stack = list(roots)
        edges = 0
        while stack:
            node = stack.pop()
            if node > 1 and node not in seen:
                seen.add(node)
                edges += 2
                stack.append(self._lo[node])
                stack.append(self._hi[node])
        return {"live": len(seen), "edges": edges, "created": len(self._unique),
                "roots": len(list(roots))}

    def to_anf(self, value: int) -> ANF:
        self.guard.check_terms(self.terms(value))
        out: list[int] = []
        stack = [(value, 0)]
        var, lo, hi = self._var, self._lo, self._hi
        while stack:
            node, mask = stack.pop()
            if node == 1:
                out.append(self._variables(mask))
            elif node > 1:
                stack.append((lo[node], mask))
                stack.append((hi[node], mask | (1 << var[node])))
        return ANF(frozenset(out))

    def from_anf(self, anf: ANF) -> int:
        self._check_anf_width(anf)
        return self.from_terms(anf.terms)

    def from_terms(self, terms: frozenset[int] | set[int]) -> int:
        """Build from distinct monomial masks."""
        return self._build([self._levels(t) for t in terms])

    def _build(self, terms: list[int]) -> int:
        if not terms:
            return 0
        support = 0
        for term in terms:
            support |= term
        if not support:
            return 1
        bit = support & -support
        lower = [t for t in terms if not t & bit]
        upper = [t ^ bit for t in terms if t & bit]
        return self._mk(bit.bit_length() - 1, self._build(lower), self._build(upper))

    def min_monomial(self, value: int) -> int | None:
        if value == 0:
            return None
        best: dict[int, tuple[int, int]] = {1: (0, 0)}

        def visit(node: int) -> tuple[int, int]:
            found = best.get(node)
            if found is None:
                degree, mask = visit(self._hi[node])
                found = (degree + 1, mask | (1 << self._var[node]))
                if self._lo[node] != 0:
                    found = min(found, visit(self._lo[node]))
                best[node] = found
            return found

        return self._variables(visit(value)[1])
