"""Opt-in exact degree-k bitset ANF for the restricted sign/HMR fragment.

No truncation, implicit sparse fallback, or general quantum-channel theorem.
Python integer XOR/bit_count use CPython's native big-integer operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import comb

from symq.anf import ANF
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard, ResourceLimitExceeded


@dataclass(frozen=True)
class Space:
    variables: int
    degree: int
    offsets: tuple[int, ...]
    capacity: int

    @classmethod
    def create(cls, variables: int, degree: int, *, max_capacity_bits: int = 1_000_000) -> Space:
        if (type(variables) is not int or variables < 1 or
                type(degree) is not int or not 0 <= degree <= 4 or
                type(max_capacity_bits) is not int or max_capacity_bits < 1):
            raise ValueError("positive width/capacity and degree 0..4 required")
        degree = min(degree, variables)
        offsets = tuple(sum(comb(variables, j) for j in range(d)) for d in range(degree+1))
        capacity = offsets[-1] + comb(variables, degree)
        if capacity > max_capacity_bits:
            raise ResourceLimitExceeded("bitset capacity", max_capacity_bits, capacity)
        return cls(variables, degree, offsets, capacity)

    def index(self, mask: int) -> int:
        if type(mask) is not int or mask < 0 or mask >> self.variables:
            raise ValueError("invalid monomial mask")
        n = mask.bit_count()
        if n > self.degree:
            raise ResourceLimitExceeded("degree", self.degree, n)
        rank, order = 0, 1
        while mask:
            low = mask & -mask
            bit = low.bit_length() - 1
            rank += comb(bit, order)
            order += 1
            mask ^= low
        return self.offsets[n] + rank

    @lru_cache(maxsize=65536)
    def mask(self, index: int) -> int:
        if type(index) is not int or not 0 <= index < self.capacity:
            raise ValueError("colex index outside space")
        degree = 0
        for d in range(self.degree + 1):
            if self.offsets[d] <= index:
                degree = d
        rank = index - self.offsets[degree]
        high = self.variables - 1
        result = 0
        for k in range(degree, 0, -1):
            lo, hi = k-1, high
            while lo < hi:
                mid = (lo + hi + 1)//2
                if comb(mid, k) <= rank:
                    lo = mid
                else:
                    hi = mid-1
            rank -= comb(lo, k)
            result |= 1 << lo
            high = lo-1
        if rank != 0:
            raise RuntimeError("invalid combinadic index")
        return result


@dataclass(frozen=True)
class Polynomial:
    space: Space
    bits: int

    def __post_init__(self) -> None:
        if (type(self.bits) is not int or self.bits < 0 or
                self.bits.bit_length() > self.space.capacity):
            raise ValueError("polynomial outside packed monomial space")

    @classmethod
    def from_masks(cls, space: Space, masks) -> Polynomial:
        bits = 0
        for mask in masks:
            bits ^= 1 << space.index(mask)
        return cls(space, bits)

    @classmethod
    def variable(cls, space: Space, index: int) -> Polynomial:
        if type(index) is not int or not 0 <= index < space.variables:
            raise ValueError("variable outside input space")
        return cls.from_masks(space, (1 << index,))

    @classmethod
    def zero(cls, space: Space) -> Polynomial:
        return cls(space, 0)

    @classmethod
    def one(cls, space: Space) -> Polynomial:
        return cls(space, 1)

    def _check(self, other: Polynomial) -> None:
        if type(other) is not Polynomial or self.space != other.space:
            raise ValueError("incompatible polynomial spaces")

    def xor(self, other: Polynomial, guard: Guard) -> Polynomial:
        self._check(other)
        guard.check_time()
        bits = self.bits ^ other.bits
        guard.check_terms(bits.bit_count())
        return Polynomial(self.space, bits)

    def masks(self):
        bits = self.bits
        while bits:
            low = bits & -bits
            yield self.space.mask(low.bit_length()-1)
            bits ^= low

    def multiply(self, other: Polynomial, guard: Guard) -> Polynomial:
        self._check(other)
        guard.check_time()
        if not self.bits or not other.bits:
            return Polynomial.zero(self.space)
        if self.bits == 1:
            return other
        if other.bits == 1:
            return self
        # Exact Boolean ring identity, not high-degree truncation.
        if self.bits == other.bits:
            return self
        left = tuple(self.masks())
        right = tuple(other.masks())
        bits = 0
        for i, a in enumerate(left):
            guard.check_time()
            for b in right:
                m = a | b  # x_i^2 = x_i
                bits ^= 1 << self.space.index(m)
                guard.check_terms(bits.bit_count())
        return Polynomial(self.space, bits)

    def to_anf(self) -> ANF:
        return ANF(frozenset(self.masks()))

    def evaluate(self, assignment: int) -> int:
        if type(assignment) is not int or assignment < 0 or assignment >> self.space.variables:
            raise ValueError("assignment outside space")
        return sum((assignment & m) == m for m in self.masks()) & 1


@dataclass(frozen=True)
class PackedPhase:
    outputs: tuple[Polynomial, ...]
    phase: Polynomial
    data: int
    measurements: int

    def violations(self) -> tuple[str, ...]:
        result = [f"O1: dirty ancilla {i}" for i in range(self.data, len(self.outputs))
                  if self.outputs[i].bits]
        mask = ((1 << self.measurements)-1) << self.data
        if any(m & mask for m in self.phase.masks()):
            result.append("O2: phase depends on measurement outcomes")
        return tuple(result)


def evaluate_phase(program: PhaseProgram, *, degree: int = 3,
                   budget: Budget | None = None, max_capacity_bits: int = 1_000_000
                   ) -> PackedPhase:
    """Exact strict PhaseProgram reference evaluation with fresh outcome symbols.

    Does not decide a general CPTP channel or accept dynamic value feed-forward.
    """
    if type(program) is not PhaseProgram:
        raise TypeError("PhaseProgram required")
    guard = Guard(budget)
    if budget is not None and budget.max_nodes is not None:
        raise ValueError("max_nodes is unsupported for this integer-bitset pilot")
    program.validate()
    space = Space.create(program.data + program.measurements, degree,
                         max_capacity_bits=max_capacity_bits)
    state = [Polynomial.variable(space, q) if q < program.data else Polynomial.zero(space)
             for q in range(program.width)]
    phase = Polynomial.zero(space)
    for op in program.ops:
        guard.check_time()
        if op.kind in ("mcx", "mcz", "mcz_if"):
            factor = Polynomial.one(space)
            qs = op.qubits[:-1] if op.kind == "mcx" else op.qubits
            for q in qs:
                factor = factor.multiply(state[q], guard)
            if op.kind == "mcx":
                target = op.qubits[-1]
                state[target] = state[target].xor(factor, guard)
            else:
                if op.kind == "mcz_if":
                    factor = factor.multiply(
                        Polynomial.variable(space, program.data + op.outcome), guard
                    )
                phase = phase.xor(factor, guard)
        elif op.kind == "hmr":
            (q,) = op.qubits
            phase = phase.xor(state[q].multiply(
                Polynomial.variable(space, program.data + op.outcome), guard
            ), guard)
            state[q] = Polynomial.zero(space)
        else:
            raise ValueError("unsupported instruction")
    guard.check_time()
    return PackedPhase(tuple(state), phase, program.data, program.measurements)
