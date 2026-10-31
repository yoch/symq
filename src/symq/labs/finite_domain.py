"""Exact finite legal-domain coefficients with symbolic HMR event variables.

This is a restricted sign-phase branch certificate; it does not accept arbitrary
reset, value feed-forward, rotations, or claim general CPTP equivalence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from symq.phase import PhaseProgram
from symq.resources import Budget, Guard, ResourceLimitExceeded


@dataclass(frozen=True)
class Domain:
    data: int
    ancillas: int
    points: tuple[int, ...]

    def __post_init__(self) -> None:
        if (type(self.data) is not int or self.data < 1 or
                type(self.ancillas) is not int or self.ancillas < 0 or
                type(self.points) is not tuple or not self.points):
            raise ValueError("nonempty explicit legal input tuple and dimensions required")
        if any(type(x) is not int or x < 0 or x >= 1 << self.data
               for x in self.points):
            raise ValueError("legal point outside data width")
        if len(set(self.points)) != len(self.points):
            raise ValueError("duplicate input points are not allowed")

    @property
    def sha256(self) -> str:
        contract = {"data": self.data, "ancillas_zero": self.ancillas,
                    "legal_points": self.points}
        return hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @property
    def full(self) -> int:
        return (1 << len(self.points)) - 1


@dataclass(frozen=True)
class OutcomePoly:
    """Canonical polynomial m_mask -> finite-domain bitset coefficient."""

    full: int
    terms: tuple[tuple[int, int], ...]

    @classmethod
    def build(cls, full: int, items) -> OutcomePoly:
        if type(full) is not int or full < 1:
            raise ValueError("nonempty domain mask required")
        accum: dict[int, int] = {}
        for mask, coeff in items:
            if (type(mask) is not int or mask < 0 or type(coeff) is not int
                    or coeff < 0 or coeff & ~full):
                raise ValueError("invalid outcome coefficient or event monomial")
            accum[mask] = accum.get(mask, 0) ^ coeff
        return cls(full, tuple(sorted((m, v) for m, v in accum.items() if v)))

    @classmethod
    def zero(cls, full: int) -> OutcomePoly:
        return cls(full, ())

    @classmethod
    def one(cls, full: int) -> OutcomePoly:
        return cls(full, ((0, full),))

    @classmethod
    def event(cls, full: int, number: int) -> OutcomePoly:
        if type(number) is not int or number < 0:
            raise ValueError("fresh measurement event required")
        return cls(full, ((1 << number, full),))

    def _compatible(self, other: OutcomePoly) -> None:
        if type(other) is not OutcomePoly or self.full != other.full:
            raise ValueError("mismatched domains for symbolic coefficients")

    def xor(self, other: OutcomePoly, guard: Guard) -> OutcomePoly:
        self._compatible(other)
        guard.check_time()
        result = OutcomePoly.build(self.full, (*self.terms, *other.terms))
        guard.check_terms(len(result.terms))
        return result

    def multiply(self, other: OutcomePoly, guard: Guard,
                 max_event_degree: int = 2) -> OutcomePoly:
        self._compatible(other)
        guard.check_time()
        accum: dict[int, int] = {}
        for a, ca in self.terms:
            guard.check_time()
            for b, cb in other.terms:
                mask = a | b
                if mask.bit_count() > max_event_degree:
                    raise ResourceLimitExceeded("event degree", max_event_degree,
                                                mask.bit_count())
                value = ca & cb  # vectorized AND on all finite inputs
                accum[mask] = accum.get(mask, 0) ^ value
                guard.check_terms(len(accum))
        return OutcomePoly.build(self.full, accum.items())

    def evaluate(self, point_index: int, outcome_bits: int) -> int:
        if (type(point_index) is not int or point_index < 0 or
                point_index >= self.full.bit_length() or
                type(outcome_bits) is not int or outcome_bits < 0):
            raise ValueError("invalid point or event assignment")
        return sum((outcome_bits & m) == m and bool(c >> point_index & 1)
                   for m, c in self.terms) & 1


@dataclass(frozen=True)
class Evidence:
    domain: Domain
    events: int
    outputs: tuple[OutcomePoly, ...]
    phase: OutcomePoly

    def same_branches(self, other: Evidence) -> bool:
        if type(other) is not Evidence or self.domain != other.domain:
            raise ValueError("same explicit legal domain and initial ancillas required")
        if self.events != other.events or len(self.outputs) != len(other.outputs):
            raise ValueError("event and output frames differ")
        return self.outputs == other.outputs and self.phase == other.phase


def evaluate_finite(program: PhaseProgram, domain: Domain, *, budget: Budget | None = None,
                    max_points: int = 8192, max_events: int = 256,
                    max_event_degree: int = 2) -> Evidence:
    """Propagate finite bitset coefficients without enumerating HMR outcomes."""
    guard = Guard(budget)
    if type(program) is not PhaseProgram or type(domain) is not Domain:
        raise TypeError("validated PhaseProgram and Domain required")
    if (type(max_points) is not int or max_points < 1 or
            type(max_events) is not int or max_events < 1 or
            type(max_event_degree) is not int or max_event_degree < 1):
        raise ValueError("positive finite symbolic caps required")
    if budget is not None and budget.max_nodes is not None:
        raise ValueError("max_nodes is not an event-coefficient bitset budget")
    program.validate()
    if (program.data, program.ancillas) != (domain.data, domain.ancillas):
        raise ValueError("initial quantum data/zero-ancilla contract mismatch")
    if len(domain.points) > max_points:
        raise ResourceLimitExceeded("domain points", max_points, len(domain.points))
    if program.measurements > max_events:
        raise ResourceLimitExceeded("events", max_events, program.measurements)
    full = domain.full
    state = []
    for wire in range(program.width):
        bits = (sum(1 << j for j, x in enumerate(domain.points) if x >> wire & 1)
                if wire < domain.data else 0)
        state.append(OutcomePoly.build(full, ((0, bits),)))
    phase = OutcomePoly.zero(full)
    for op in program.ops:
        guard.check_time()
        if op.kind in {"mcx", "mcz", "mcz_if"}:
            product = OutcomePoly.one(full)
            wires = op.qubits[:-1] if op.kind == "mcx" else op.qubits
            for q in wires:
                product = product.multiply(state[q], guard, max_event_degree)
            if op.kind == "mcx":
                state[op.qubits[-1]] = state[op.qubits[-1]].xor(product, guard)
            else:
                if op.kind == "mcz_if":
                    product = product.multiply(OutcomePoly.event(full, op.outcome),
                                               guard, max_event_degree)
                phase = phase.xor(product, guard)
        elif op.kind == "hmr":
            (q,) = op.qubits
            phase = phase.xor(
                state[q].multiply(OutcomePoly.event(full, op.outcome),
                                  guard, max_event_degree), guard
            )
            state[q] = OutcomePoly.zero(full)
        else:
            raise ValueError("unsupported instruction in restricted phase grammar")
    guard.check_time()
    return Evidence(domain, program.measurements, tuple(state), phase)
