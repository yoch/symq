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

    def observe_terms(self, count: int | None) -> None:
        if count is not None and (self.peak_terms is None or count > self.peak_terms):
            self.peak_terms = count


class Algebra(ABC, Generic[E]):
    """Exact representation of GF(2)[x_0..x_{width-1}]/(x_i^2 - x_i).

    Values are canonical within one algebra instance: ``equal`` is exact and values from
    different instances must never be mixed. ``xor`` is pure; ``ixor`` may reuse its first
    argument, which the caller must not use afterwards. ``product`` returns a value that
    shares no mutable state with its factors.
    """

    name: ClassVar[str]

    def __init__(self, width: int, guard: Guard | None = None) -> None:
        if not isinstance(width, int) or width < 1:
            raise ValueError("width must be a positive integer")
        self.width = width
        self.guard = guard if guard is not None else Guard()
        self.stats = Stats()

    @abstractmethod
    def variable(self, index: int) -> E: ...
    @abstractmethod
    def one(self) -> E: ...

    @abstractmethod
    def zero(self) -> E: ...

    @abstractmethod
    def xor(self, left: E, right: E) -> E: ...

    @abstractmethod
    def product(self, factors: Sequence[E]) -> E: ...

    @abstractmethod
    def equal(self, left: E, right: E) -> bool: ...

    @abstractmethod
    def is_zero(self, value: E) -> bool: ...

    @abstractmethod
    def terms(self, value: E) -> int | None:
        """Number of monomials, or ``None`` if it is not cheaply available."""

    @abstractmethod
    def to_anf(self, value: E) -> ANF: ...

    @abstractmethod
    def from_anf(self, anf: ANF) -> E: ...

    def ixor(self, left: E, right: E) -> E:
        return self.xor(left, right)

    def min_monomial(self, value: E) -> int | None:
        """A monomial of minimum degree; its mask is an assignment where ``value`` is 1."""
        return min(self.to_anf(value).terms, key=lambda m: (m.bit_count(), m), default=None)

    def apply_mcx(self, state: list[E], controls: Sequence[int], target: int) -> None:
        control = self.product([state[c] for c in controls]) if controls else self.one()
        state[target] = self.ixor(state[target], control)

    def simulate(self, circuit: Circuit) -> tuple[E, ...]:
        """Exact symbolic outputs of a circuit; a backend may fuse the gate loop."""
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
            self.stats.observe_terms(self.terms(state[target]))
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
