"""Affine Boolean functions as bit masks: exact, linear-time and of unbounded width.

A value ``c + x_{i1} + ... + x_{ik}`` is the integer with bits ``i1..ik`` set and bit ``width`` set
when ``c = 1``. XOR is integer XOR, so a circuit of ``X`` and ``CX`` gates on any number of wires is
simulated with one machine-word operation per gate and word of width. Products that would leave
the affine space (two non-constant factors) raise ``ResourceLimitExceeded("degree")``; nothing is
approximated. Use this backend for wide linear stages (permutations, GF(2) maps, Frobenius maps),
where the diagram backends are capped at 64, 128 or 256 variables.
"""
from __future__ import annotations

import time
from collections.abc import Sequence

from ..anf import ANF
from ..circuit import Circuit
from ..resources import Guard, ResourceLimitExceeded
from .base import Algebra


class LinearAlgebra(Algebra[int]):
    """Exact algebra of affine functions; refuses degree two (``ResourceLimitExceeded``)."""

    name = "linear"

    def __init__(self, width: int, guard: Guard | None = None) -> None:
        super().__init__(width, guard)
        self._one = 1 << width
        self._variables = (1 << width) - 1

    def variable(self, index: int) -> int:
        return 1 << self._check_variable(index)

    def one(self) -> int:
        return self._one

    def zero(self) -> int:
        return 0

    def xor(self, left: int, right: int) -> int:
        return left ^ right

    def product(self, factors: Sequence[int]) -> int:
        self.stats.products += 1
        result = self._one
        for factor in factors:
            if factor == 0 or result == 0:
                return 0
            if factor == self._one or factor == result:
                continue  # 1 * f = f and f * f = f
            if result == self._one:
                result = factor
            elif factor == result ^ self._one:
                return 0  # f * (f + 1) = 0
            else:
                # Two affine functions that are neither equal nor complementary multiply to a
                # quadratic: no exact affine value exists.
                raise ResourceLimitExceeded(
                    "degree", 1, 2, hint="the linear backend represents affine functions only")
        return result

    def equal(self, left: int, right: int) -> bool:
        return left == right

    def is_zero(self, value: int) -> bool:
        return value == 0

    def terms(self, value: int) -> int:
        return value.bit_count()

    def to_anf(self, value: int) -> ANF:
        terms = {1 << i for i in range(self.width) if value >> i & 1}
        if value & self._one:
            terms.add(0)
        return ANF(frozenset(terms))

    def from_anf(self, anf: ANF) -> int:
        self._check_anf_width(anf)
        value = 0
        for monomial in anf.terms:
            if monomial == 0:
                value ^= self._one
            elif monomial & (monomial - 1):
                raise ResourceLimitExceeded("degree", 1, monomial.bit_count())
            else:
                value ^= monomial
        return value

    def min_monomial(self, value: int) -> int | None:
        if value == 0:
            return None
        if value & self._one:
            return 0  # the constant monomial: the all-zero input evaluates to 1
        return value & -value  # the lowest variable

    def simulate(self, circuit: Circuit) -> tuple[int, ...]:
        """Fused loop; a gate with two or more controls raises ``ResourceLimitExceeded``."""
        if not isinstance(circuit, Circuit):
            raise TypeError("a Circuit is required")
        circuit.validate()
        if circuit.width != self.width:
            raise ValueError("circuit and algebra widths differ")
        started = time.perf_counter()
        state = [1 << i for i in range(self.width)]
        one, check = self._one, self.guard.check_time
        for index, gate in enumerate(circuit.gates):
            if not index & 0x3FF:
                check()
            qubits = gate.qubits
            if len(qubits) == 1:
                state[qubits[0]] ^= one
            elif len(qubits) == 2:
                state[qubits[1]] ^= state[qubits[0]]
            else:
                factors = [state[q] for q in qubits[:-1]]
                state[qubits[-1]] ^= self.product(factors)
                continue
        self.stats.gates += len(circuit.gates)
        self.stats.seconds += time.perf_counter() - started
        return tuple(state)
