"""Native monomial ZDD (C extension) with the same algebra as :mod:`symq.backends.zdd`.

The data structure, the hash-consing and the three-product recursion are the Python
implementation's; the difference is that the recursion, the unique table and the gate loop run
in C. Every guarantee is unchanged: results are exact, canonical, budgeted, and node ids are
plain integers.

The extension is optional (``Extension(optional=True)``): without a C compiler, ``._zdd`` is
absent and this module refuses to be imported, so the registered backends keep working.
"""
from __future__ import annotations

import array
import time
from collections.abc import Sequence

from ..anf import ANF
from ..circuit import Circuit
from ..resources import Guard, ResourceLimitExceeded
from . import _zdd
from ._zdd import NativeZDDManager
from .base import Algebra

ABI_VERSION = 4
"""Interface of ``_zdd`` this module expects; a stale in-place build is refused at import."""
if getattr(_zdd, "ABI_VERSION", 1) != ABI_VERSION:
    raise ImportError(
        f"stale native core {_zdd.__file__} (ABI {getattr(_zdd, 'ABI_VERSION', 1)}, "
        f"expected {ABI_VERSION}); rebuild it with 'python tools/build_native.py'"
    )

MAX_WIDTH = 64
"""``uint64_t`` monomial masks; wider algebras keep using the Python backend."""


def available() -> bool:
    return True


class NativeZDDAlgebra(Algebra[int]):
    """ZDD over monomial families, backed by :class:`NativeZDDManager`."""

    name = "zdd-native"

    def __init__(
        self,
        width: int,
        guard: Guard | None = None,
        *,
        order: Sequence[int] | None = None,
        cache_limit: int | None = None,
        collect_every: int | None = None,
    ) -> None:
        """``cache_limit`` (default ``None``) selects the operation cache.

        ``None``: lossless, entries are never evicted and the table grows with the work (the
        measured configuration). An integer ``n >= 1``: a fixed direct-mapped table of the
        largest power of two not above ``n`` entries (16 bytes each) where a store overwrites
        its slot. Results, node ids, ``node_count`` and every statistic except running time are
        identical in both modes; a small limit only bounds the cache memory and may cost
        recomputation, with no bound on how much.
        """
        super().__init__(width, guard)
        if cache_limit is not None and (
            isinstance(cache_limit, bool) or not isinstance(cache_limit, int) or cache_limit < 1
        ):
            raise ValueError("cache_limit must be a positive integer or None")
        if width > MAX_WIDTH:
            raise ResourceLimitExceeded(
                "width",
                MAX_WIDTH,
                width,
                hint=(
                    "native ZDD core uses uint64_t monomial masks; for wider circuits, "
                    "use the pure-Python 'zdd' backend or verify by wire blocks"
                ),
            )
        self.order = tuple(range(width)) if order is None else tuple(order)
        if collect_every is not None and (
            isinstance(collect_every, bool) or not isinstance(collect_every, int)
            or collect_every < 1
        ):
            raise ValueError("collect_every must be a positive integer or None")
        self.collect_every = collect_every
        self._cache_limit = cache_limit
        self.collections = 0
        self.collected_nodes = 0
        if sorted(self.order) != list(range(width)):
            raise ValueError("order must be a permutation of the variable indices")
        budget = self.guard.budget
        self.manager = NativeZDDManager(
            width,
            order=list(self.order),
            deadline=self.guard.deadline or 0.0,
            started=self.guard.started,
            max_seconds=budget.max_seconds or 0.0,
            max_nodes=budget.max_nodes or 0,
            max_terms=budget.max_terms or 0,
            cache_limit=cache_limit or 0,
        )

    @property
    def node_count(self) -> int:
        """Internal nodes ever created (no garbage collection is performed)."""
        return self.manager.node_count()

    def cache_info(self) -> dict[str, int | bool]:
        """``lossy`` (bool), ``capacity`` (entries allocated now), ``limit`` (configured ceiling
        in lossy mode, ``0`` when lossless) and ``misses`` (recursions that missed the cache)."""
        return self.manager.cache_info()

    def variable(self, index: int) -> int:
        return self.manager.variable(self._check_variable(index))

    def one(self) -> int:
        return 1

    def zero(self) -> int:
        return 0

    def xor(self, left: int, right: int) -> int:
        return self.manager.xor(left, right)

    def product(self, factors: Sequence[int]) -> int:
        self.stats.products += 1
        result = 1
        for factor in sorted(factors, key=self.terms):
            result = self.manager.product(result, factor)
            if result == 0:
                break
        return result

    def equal(self, left: int, right: int) -> bool:
        return left == right

    def is_zero(self, value: int) -> bool:
        return value == 0

    def terms(self, value: int) -> int:
        """Monomial count, saturated at ``2**63 - 1`` (a 64-variable family can exceed it)."""
        return self.manager.terms(value)

    def size(self, value: int) -> int:
        return self.manager.size(value)

    def to_anf(self, value: int) -> ANF:
        return ANF(self.manager.anf(value))

    def from_anf(self, anf: ANF) -> int:
        self._check_anf_width(anf)
        return self.from_terms(anf.terms)

    def from_terms(self, terms: frozenset[int] | set[int]) -> int:
        return self.manager.from_terms(sorted(terms))

    def min_monomial(self, value: int) -> int | None:
        return self.manager.min_monomial(value)

    def simulate(self, circuit: Circuit) -> tuple[int, ...]:
        """One C call for the whole gate list: no Python object per gate or per wire."""
        if not isinstance(circuit, Circuit):
            raise TypeError("a Circuit is required")
        circuit.validate()
        if circuit.width != self.width:
            raise ValueError("circuit and algebra width differ")
        if self.collect_every is not None:
            return self._simulate_with_collection(circuit)
        indices: list[int] = []
        offsets = [0]
        targets: list[int] = []
        for gate in circuit.gates:
            qubits = gate.qubits
            indices.extend(qubits[:-1])
            offsets.append(len(indices))
            targets.append(qubits[-1])
        c_indices = array.array("I", indices)
        c_offsets = array.array("I", offsets)
        c_targets = array.array("I", targets)
        started = time.perf_counter()
        state_list, peak, products = self.manager.simulate(
            None, c_indices, c_offsets, c_targets
        )
        self.stats.seconds += time.perf_counter() - started
        self.stats.gates += len(circuit.gates)
        self.stats.products += products
        if peak is not None:
            self.stats.observe_terms(peak)
        return tuple(state_list)

    def _simulate_slice(self, gates, roots: tuple[int, ...] | None):
        indices: list[int] = []
        offsets = [0]
        targets: list[int] = []
        for gate in gates:
            qubits = gate.qubits
            indices.extend(qubits[:-1])
            offsets.append(len(indices))
            targets.append(qubits[-1])
        state, peak, products = self.manager.simulate(
            None if roots is None else list(roots),
            array.array("I", indices), array.array("I", offsets), array.array("I", targets))
        self.stats.gates += len(gates)
        self.stats.products += products
        if peak is not None:
            self.stats.observe_terms(peak)
        return tuple(state)

    def _simulate_with_collection(self, circuit: Circuit) -> tuple[int, ...]:
        """Simulate in slices, collecting whenever the unique table passes the threshold."""
        gates = list(circuit.gates)
        if not gates:
            return tuple(self.variable(index) for index in range(self.width))
        # The slice size decides *when* the threshold can be observed, so it must be small
        # enough that one slice does not overshoot it by an order of magnitude: a fixed eight
        # slices on a 200-gate circuit creates millions of nodes between two checks, which is
        # exactly the peak the collection is supposed to bound. Start at one gate and grow the
        # slice only while the table stays far below the threshold.
        size = 1
        roots: tuple[int, ...] | None = None
        start = 0
        while start < len(gates):
            stop = min(start + size, len(gates))
            roots = self._simulate_slice(gates[start:stop], roots)
            if stop >= len(gates):
                break
            if self.manager.node_count() >= self.collect_every:
                roots = self._collect(roots)
                size = 1
            elif self.manager.node_count() * 8 < self.collect_every:
                size = min(size * 2, 64)
            else:
                size = max(1, size // 2)
            start = stop
        return roots if roots is not None else ()

    def _collect(self, roots: tuple[int, ...]) -> tuple[int, ...]:
        """Move ``roots`` into a fresh manager and adopt it; returns the new identifiers."""
        before = self.manager.node_count()
        fresh = NativeZDDAlgebra(self.width, self.guard, order=self.order,
                                 cache_limit=self._cache_limit)
        moved = tuple(fresh.from_anf(ANF(frozenset(self.manager.anf(root)))) for root in roots)
        self.manager = fresh.manager
        self.collections += 1
        self.collected_nodes += max(before - self.manager.node_count(), 0)
        return moved

    def reachable_union(self, roots) -> dict[str, int]:
        """Exact live-node count over ``roots`` (see ``NativeZDDManager.reachable_union``)."""
        return self.manager.reachable_union(list(roots))
