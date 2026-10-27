"""Native monomial ZDD (C extension) with the same algebra as :mod:`symq.backends.zdd`.

The data structure, the hash-consing and the three-product recursion are the Python
implementation's; the difference is that the recursion, the unique table and the gate loop run
in C. Every guarantee is unchanged: results are exact, canonical, budgeted, and node ids are
plain integers.

The extension is optional (``Extension(optional=True)``): without a C compiler, ``._zdd`` is
absent and this module refuses to be imported, so the registered backends keep working.
"""
from __future__ import annotations

import time
from collections.abc import Sequence

from ..anf import ANF
from ..circuit import Circuit
from ..resources import Guard, ResourceLimitExceeded
from . import _zdd
from ._zdd import NativeZDDManager
from .base import Algebra

ABI_VERSION = 2
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
    ) -> None:
        super().__init__(width, guard)
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
        )

    @property
    def node_count(self) -> int:
        """Internal nodes ever created (no garbage collection is performed)."""
        return self.manager.node_count()

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
        if circuit.width != self.width:
            raise ValueError("circuit and algebra width differ")
        indices: list[int] = []
        offsets = [0]
        targets: list[int] = []
        for gate in circuit.gates:
            *controls, target = gate.qubits
            indices.extend(controls)
            offsets.append(len(indices))
            targets.append(target)
        started = time.perf_counter()
        state_list, peak = self.manager.simulate(
            [self.variable(i) for i in range(self.width)], indices, offsets, targets
        )
        self.stats.seconds += time.perf_counter() - started
        self.stats.gates += len(circuit.gates)
        self.stats.products += sum(1 for gate in circuit.gates if len(gate.qubits) > 1)
        if peak is not None:
            self.stats.observe_terms(peak)
        return tuple(state_list)
