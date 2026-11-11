"""Common contract for exact Boolean-ring backends used by symbolic simulation."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

from ..anf import ANF
from ..circuit import Circuit
from ..resources import Guard

E = TypeVar("E")


@dataclass
class Stats:
    """Work counters filled during a computation.

    ``peak_terms`` is the largest monomial count observed on a wire after a gate; it is
    ``None`` for backends without a cheap term count. ``conversions`` counts changes of
    representation, with their monomial volume and wall time.
    """

    gates: int = 0
    products: int = 0
    peak_terms: int | None = None
    conversions: int = 0
    conversion_terms: int = 0
    conversion_seconds: float = 0.0
    seconds: float = 0.0
    """Wall time spent inside the backend's own evaluation (not conversions)."""

    COUNTERS: ClassVar[tuple[str, ...]] = (
        "gates", "products", "conversions", "conversion_terms", "conversion_seconds", "seconds")
    """Additive fields; ``peak_terms`` is a maximum and is merged separately."""

    def observe_terms(self, count: int | None) -> None:
        """Raise ``peak_terms`` to ``count`` if it is larger; ``None`` is ignored."""
        if count is not None and (self.peak_terms is None or count > self.peak_terms):
            self.peak_terms = count

    def merge(self, other: Stats) -> Stats:
        """Add ``other``'s counters into this record and keep the larger peak; returns ``self``."""
        for name in self.COUNTERS:
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.observe_terms(other.peak_terms)
        return self

    def items(self) -> tuple[tuple[str, int | float], ...]:
        """``(name, value)`` pairs of the additive counters, in a fixed order."""
        return tuple((name, getattr(self, name)) for name in self.COUNTERS)


class Algebra(ABC, Generic[E]):
    """Exact representation of GF(2)[x_0..x_{width-1}]/(x_i^2 - x_i).

    Values are canonical within one algebra instance: ``equal`` is exact and values from
    different instances must never be mixed. ``xor`` is pure; ``ixor`` may reuse its first
    argument, which the caller must not use afterwards. ``product`` returns a value that
    shares no mutable state with its factors.
    """

    name: ClassVar[str]
    enforces_max_bytes: ClassVar[bool] = False
    """Whether this backend measures its own memory and can honour ``Budget.max_bytes``."""
    order_option: ClassVar[str | None] = None
    """Name of the constructor option carrying a variable order, ``None`` if there is none."""
    width: int
    """Number of variables."""
    guard: Guard
    """The budget in force and its clock."""
    stats: Stats
    """Operation counters of this instance."""

    def __init__(self, width: int, guard: Guard | None = None) -> None:
        if not isinstance(width, int) or width < 1:
            raise ValueError("width must be a positive integer")
        self.width = width
        self.guard = guard if guard is not None else Guard()
        if self.guard.budget.max_bytes is not None and not self.enforces_max_bytes:
            raise ValueError(
                f"backend {self.name!r} cannot bound its memory: Budget.max_bytes is enforced "
                "only by the native ZDD backends; use an isolated subprocess for a hard limit")
        self.stats = Stats()

    def bind_guard(self, guard: Guard) -> None:
        """Run later work under ``guard``, including every algebra this one wraps.

        Composite backends hold sub-algebras that captured the guard at construction; rebinding
        only the outer object would leave them on a stale deadline.
        """
        if guard.budget.max_bytes is not None and not self.enforces_max_bytes:
            raise ValueError(f"backend {self.name!r} cannot bound its memory (Budget.max_bytes)")
        guard.check_time()
        self.guard = guard
        for value in vars(self).values():
            if isinstance(value, Algebra) and value is not self:
                value.bind_guard(guard)

    @abstractmethod
    def variable(self, index: int) -> E:
        """The value representing ``x_index``; an index outside the width raises."""

    @abstractmethod
    def one(self) -> E:
        """The constant polynomial 1."""

    @abstractmethod
    def zero(self) -> E:
        """The constant polynomial 0."""

    @abstractmethod
    def xor(self, left: E, right: E) -> E:
        """The sum of two values over GF(2), leaving both arguments unchanged."""

    @abstractmethod
    def product(self, factors: Sequence[E]) -> E:
        """The Boolean-ring product of ``factors`` (``x*x = x``); the empty product is 1."""

    @abstractmethod
    def equal(self, left: E, right: E) -> bool:
        """Whether two values of this algebra are the same polynomial (exact, not heuristic)."""

    @abstractmethod
    def is_zero(self, value: E) -> bool:
        """Whether ``value`` is the zero polynomial."""

    @abstractmethod
    def terms(self, value: E) -> int | None:
        """Number of monomials, or ``None`` if it is not cheaply available."""

    @abstractmethod
    def to_anf(self, value: E) -> ANF:
        """``value`` as an explicit :class:`~symq.ANF`; its size can be exponential."""

    @abstractmethod
    def from_anf(self, anf: ANF) -> E:
        """The value of this algebra equal to ``anf``, which must fit the algebra's width."""

    def ixor(self, left: E, right: E) -> E:
        """``xor`` that may reuse ``left``'s storage; the caller must not use ``left`` afterwards."""
        return self.xor(left, right)

    def min_monomial(self, value: E) -> int | None:
        """A monomial of minimum degree; its mask is an assignment where ``value`` is 1."""
        return min(self.to_anf(value).terms, key=lambda m: (m.bit_count(), m), default=None)

    def apply_mcx(self, state: list[E], controls: Sequence[int], target: int) -> None:
        """Apply one controlled-X to ``state`` in place: ``state[target] ^= prod(controls)``."""
        control = self.product([state[c] for c in controls]) if controls else self.one()
        state[target] = self.ixor(state[target], control)

    def simulate(self, circuit: Circuit) -> tuple[E, ...]:
        """Exact symbolic outputs of a circuit; a backend may fuse the gate loop."""
        if not isinstance(circuit, Circuit):
            raise TypeError("a Circuit is required")
        circuit.validate()
        if circuit.width != self.width:
            raise ValueError("circuit and algebra widths differ")
        started = time.perf_counter()
        converting = self.stats.conversion_seconds
        state = [self.variable(i) for i in range(self.width)]
        for gate in circuit.gates:
            self.guard.check_time()
            *controls, target = gate.qubits
            self.apply_mcx(state, controls, target)
            self.stats.gates += 1
            count = self.terms(state[target])
            self.stats.observe_terms(count)
            if count is not None:
                self.guard.check_terms(count)
        converted = self.stats.conversion_seconds - converting
        self.stats.seconds += time.perf_counter() - started - converted
        return tuple(state)

    def _check_variable(self, index: int) -> int:
        """Validate a variable index; every backend routes its ``variable`` through it.

        Without it, ``variable(-1)`` silently returned the last variable on backends that
        index a list or tuple, which makes a contract violation look like a valid result.
        """
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("variable index must be an integer")
        if not 0 <= index < self.width:
            raise ValueError(f"variable index {index} outside algebra width {self.width}")
        return index

    def _check_anf_width(self, anf: ANF) -> None:
        if any(m >> self.width for m in anf.terms):
            raise ValueError("ANF uses variables outside the algebra width")


def simulate(circuit: Circuit, algebra: Algebra[E]) -> tuple[E, ...]:
    """Exact symbolic outputs of an X/CX/CCX/MCX circuit, one polynomial per wire."""
    return algebra.simulate(circuit)
