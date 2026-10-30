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
from ..resources import Guard, ResourceLimitExceeded, current_session
from . import _zdd
from ._zdd import NativeZDDManager
from .base import Algebra

ABI_VERSION = 5
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
    max_width = MAX_WIDTH

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

        ``collect_every`` (optional) enables memory-limited reconstruction during
        an *owned*, one-shot simulation. Because native node handles are plain integers,
        no values may have been exposed before collection and this algebra cannot
        simulate a second circuit after returning handles. For equivalence, use
        ``check_equivalence(..., backend_options={"collect_every": n})``, which
        pins the first circuit's outputs while simulating the second.
        """
        super().__init__(width, guard)
        if cache_limit is not None and (
            isinstance(cache_limit, bool) or not isinstance(cache_limit, int) or cache_limit < 1
        ):
            raise ValueError("cache_limit must be a positive integer or None")
        if width > self.max_width:
            raise ResourceLimitExceeded(
                "width",
                self.max_width,
                width,
                hint=(
                    f"this native backend supports at most {self.max_width} variables; for wider circuits, "
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
        self.collection_seconds = 0.0
        self.collection_transfer_roots = 0
        # Collection remaps plain integer IDs. Only a pristine, one-shot simulation or
        # an internally owned circuit pair may collect; no public handles can survive it.
        self._collected_run_used = False
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
        """Internal nodes in the current manager; collection replaces this manager."""
        return self.manager.node_count()

    def cache_info(self) -> dict[str, int | bool]:
        """``lossy`` (bool), ``capacity`` (entries allocated now), ``limit`` (configured ceiling
        in lossy mode, ``0`` when lossless) and ``misses`` (recursions that missed the cache)."""
        return self.manager.cache_info()

    def memory_info(self) -> dict[str, int | float]:
        """Allocated native arrays, excluding temporary buffers and allocator overhead.

        These are current capacities, not RSS or a process peak. ``reachable_union``
        separately measures which nodes are live from a particular root set.
        """
        return {
            **self.manager.memory_info(),
            "collections": self.collections,
            "collected_nodes": self.collected_nodes,
            "collection_seconds": self.collection_seconds,
            "collection_transfer_roots": self.collection_transfer_roots,
        }

    def bind_guard(self, guard: Guard) -> None:
        """Bind this verification's budget while retaining manager-owned roots."""
        guard.check_time()
        budget = guard.budget
        self.manager.bind_budget(
            guard.deadline or 0.0, guard.started, budget.max_seconds or 0.0,
            budget.max_nodes or 0, budget.max_terms or 0,
        )
        self.guard = guard

    def rename_many(self, roots: Sequence[int], mapping: Sequence[int]) -> tuple[int, ...]:
        """Rename levels with a shared memo; admissibility is checked per root."""
        return tuple(self.manager.rename_many(roots, mapping))

    def simulate_hmr(self, program, offset: int = 0) -> tuple[tuple[int, ...], int, tuple[int, ...]]:
        """Fuse the strict sign/HMR grammar, retaining all physical output wires.

        Ancillas start at zero. The manager's variable width is independent of
        ``program.width``; input data use variables ``offset..offset+data``.
        Returned IDs belong to this manager, like ordinary algebra values.
        """
        from ..phase import PhaseProgram

        if type(program) is not PhaseProgram:
            raise TypeError("a PhaseProgram is required")
        program.validate()
        if type(offset) is not int or offset < 0 or offset + program.data > self.width:
            raise ValueError("HMR data variables outside algebra width")
        codes = {"mcx": 0, "mcz": 1, "hmr": 2, "mcz_if": 3}
        opcodes, indices, outcomes = [], [], []
        offsets = [0]
        ops = tuple(program.ops)
        for op in ops:
            opcodes.append(codes[op.kind])
            indices.extend(op.qubits)
            offsets.append(len(indices))
            outcomes.append(0xFFFFFFFF if op.outcome is None else op.outcome)
        state = [self.variable(offset + q) if q < program.data else 0
                 for q in range(program.width)]
        started = time.perf_counter()
        try:
            state, phase, coefficients, peak, products = self.manager.simulate_hmr(
                state, 0, [], *(array.array("I", values) for values in
                              (opcodes, indices, offsets, outcomes)),
            )
        finally:
            self.stats.seconds += time.perf_counter() - started
        self.stats.gates += len(ops)
        self.stats.products += products
        self.stats.observe_terms(peak)
        return tuple(state), phase, tuple(coefficients)

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
            self._begin_collected_run()
            started = time.perf_counter()
            try:
                outputs, _ = self._simulate_with_collection(circuit)
                return outputs
            finally:
                self.stats.seconds += time.perf_counter() - started
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

    def _begin_collected_run(self) -> None:
        """Enforce the ID-lifetime contract before replacing any manager.

        Node IDs are plain integers, not generation-tagged handles. Collection cannot
        preserve IDs already handed to a caller, even when an old ID happens to be in
        range in the new manager (it could denote a *different* polynomial).
        """
        if self._collected_run_used or self.manager.node_count() != 0:
            raise RuntimeError(
                "collect_every requires a fresh, one-shot NativeZDDAlgebra; "
                "existing node IDs would be invalidated by collection"
            )
        self._collected_run_used = True

    def simulate_pair(self, left: Circuit, right: Circuit) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Simulate a circuit pair while keeping both outputs valid in one manager.

        During the second simulation, the first circuit's outputs are pinned as live
        roots and remapped at every collection. This is the safe entry point for an
        exact equivalence checker: *both* output tuples refer to the final manager.
        """
        for circuit in (left, right):
            if not isinstance(circuit, Circuit):
                raise TypeError("a Circuit is required")
            circuit.validate()
            if circuit.width != self.width:
                raise ValueError("circuit and algebra width differ")
        if self.collect_every is None:
            return self.simulate(left), self.simulate(right)
        self._begin_collected_run()
        started = time.perf_counter()
        try:
            left_roots, _ = self._simulate_with_collection(left)
            right_roots, left_roots = self._simulate_with_collection(right, left_roots)
            return left_roots, right_roots
        finally:
            self.stats.seconds += time.perf_counter() - started

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

    def _simulate_with_collection(
        self, circuit: Circuit, preserved: tuple[int, ...] = ()
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Simulate in slices, collecting both active and pinned roots when needed."""
        assert self.collect_every is not None
        gates = list(circuit.gates)
        if not gates:
            return tuple(self.manager.variable(index) for index in range(self.width)), preserved
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
                roots, preserved = self._collect(roots, preserved)
                size = 1
            elif self.manager.node_count() * 8 < self.collect_every:
                size = min(size * 2, 64)
            else:
                size = max(1, size // 2)
            start = stop
        return (roots if roots is not None else ()), preserved

    def _collect(
        self, roots: tuple[int, ...], preserved: tuple[int, ...] = ()
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Rebuild every live root, including pinned outputs of a prior circuit.

        This method is private: only a one-shot simulation or an owned pair may
        call it. Public IDs must never be used across a manager replacement.
        """
        transferred = self.collect_roots((*roots, *preserved))
        return tuple(transferred[:len(roots)]), tuple(transferred[len(roots):])

    def collect_roots(self, roots: Sequence[int]) -> tuple[int, ...]:
        """Replace an owned manager by the live DAG without enumerating monomials.

        Every live root must be supplied, including previously computed states or
        cached references. All old integer handles become invalid for this algebra.
        On failure the original manager remains installed.
        """
        roots = tuple(roots)
        before = self.manager.node_count()
        old_manager = self.manager
        session = current_session()
        prior_reservation = None
        if session is not None:
            live = old_manager.reachable_union(list(roots))["live"]
            prior_reservation = session.reservation(old_manager)
            # Both native tables coexist during transfer. The fresh table's
            # capacities cannot exceed the source's; memo/ID buffers are extra.
            resident_bytes = (2 * old_manager.memory_info()["manager_bytes"]
                              + (before + 2) * 4 + len(roots) * 8)
            session.reserve(old_manager, nodes=before + live, bytes_=resident_bytes)
        started = time.perf_counter()
        try:
            fresh, transferred = old_manager.clone_roots(roots)
            if session is not None:
                if prior_reservation is not None:
                    session.restore_reservation(old_manager, prior_reservation)
                    session.reserve(fresh, nodes=fresh.node_count(),
                                    bytes_=fresh.memory_info()["manager_bytes"])
                session.release(old_manager)
        except BaseException:
            if session is not None:
                session.restore_reservation(old_manager, prior_reservation)
            raise
        self.collection_seconds += time.perf_counter() - started
        self.manager = fresh
        self.collections += 1
        self.collection_transfer_roots += len(transferred)
        self.collected_nodes += max(before - self.manager.node_count(), 0)
        return tuple(transferred)

    def reachable_union(self, roots) -> dict[str, int]:
        """Exact live-node count over ``roots`` (see ``NativeZDDManager.reachable_union``)."""
        return self.manager.reachable_union(list(roots))


class NativeZDDWideAlgebra(NativeZDDAlgebra):
    """Explicit experimental native backend for up to 128 variables.

    Diagram operations share the 64-bit backend's core. A second mask word is
    allocated only when import/export or witnesses require it above width 64.
    """

    name = "zdd-native-wide"
    max_width = 128
