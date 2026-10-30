"""Closed coherent input domains, represented without listing their basis states.

A domain denotes the span of its computational basis states.  Its symbolic
parameterisation is injective, so checking every pair of parameters checks
every matrix unit of that subspace, including its off-diagonal coherences.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from symq.circuit import Circuit, Gate
from symq.resources import Guard
from symq.sat.assumptions import And, Const, Eq, Expr, Not, Var, Xor, evaluate, validate


def _dimension(data: int) -> None:
    if type(data) is not int or data < 1:
        raise ValueError("domain data width must be a positive integer")


def _assignment(value: int, width: int) -> int:
    if type(value) is not int or value < 0 or value >> width:
        raise ValueError("assignment outside domain width")
    return value


def _space(algebra: Any, offset: int, parameters: int) -> None:
    if type(offset) is not int or offset < 0 or offset + parameters > algebra.width:
        raise ValueError("domain parameters outside algebra width")


def _keys(value: Any, expected: set[str], description: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{description} requires exactly {sorted(expected)}")
    return value


class _Domain:
    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()


@dataclass(frozen=True)
class FullCube(_Domain):
    data: int

    def __post_init__(self) -> None:
        _dimension(self.data)

    @property
    def parameters(self) -> int:
        return self.data

    def symbolic(self, algebra: Any, offset: int, guard: Guard) -> tuple[tuple, Any]:
        _space(algebra, offset, self.parameters)
        guard.check_time()
        return tuple(algebra.variable(offset + q) for q in range(self.data)), algebra.one()

    def decode(self, value: int) -> int:
        return _assignment(value, self.data)

    def contains(self, value: int) -> bool:
        return type(value) is int and value >= 0 and not value >> self.data

    def to_dict(self) -> dict:
        return {"kind": "full_cube", "data": self.data}


@dataclass(frozen=True)
class AffineDomain(_Domain):
    data: int
    offset: int
    basis: tuple[int, ...]

    def __post_init__(self) -> None:
        _dimension(self.data)
        _assignment(self.offset, self.data)
        if type(self.basis) is not tuple:
            raise TypeError("affine basis must be an immutable tuple")
        pivots: dict[int, int] = {}
        for column in self.basis:
            value = _assignment(column, self.data)
            while value:
                pivot = value.bit_length() - 1
                if pivot not in pivots:
                    pivots[pivot] = value
                    break
                value ^= pivots[pivot]
            if not value:
                raise ValueError("affine basis must have full column rank")

    @property
    def parameters(self) -> int:
        return len(self.basis)

    def symbolic(self, algebra: Any, offset: int, guard: Guard) -> tuple[tuple, Any]:
        _space(algebra, offset, self.parameters)
        parameters = tuple(algebra.variable(offset + q) for q in range(self.parameters))
        state = []
        for wire in range(self.data):
            guard.check_time()
            value = algebra.one() if self.offset >> wire & 1 else algebra.zero()
            for column, parameter in zip(self.basis, parameters):
                if column >> wire & 1:
                    value = algebra.xor(value, parameter)
            state.append(value)
        return tuple(state), algebra.one()

    def decode(self, value: int) -> int:
        _assignment(value, self.parameters)
        result = self.offset
        for index, column in enumerate(self.basis):
            if value >> index & 1:
                result ^= column
        return result

    def contains(self, value: int) -> bool:
        if type(value) is not int or value < 0 or value >> self.data:
            return False
        pivots: dict[int, int] = {}
        for column in self.basis:
            while column:
                pivot = column.bit_length() - 1
                if pivot not in pivots:
                    pivots[pivot] = column
                    break
                column ^= pivots[pivot]
        remaining = value ^ self.offset
        while remaining:
            pivot = remaining.bit_length() - 1
            if pivot not in pivots:
                return False
            remaining ^= pivots[pivot]
        return True

    def to_dict(self) -> dict:
        return {"kind": "affine", "data": self.data, "offset": self.offset,
                "basis": list(self.basis)}


@dataclass(frozen=True, init=False)
class PreparedDomain(_Domain):
    data: int
    gates: tuple[Gate, ...]
    free_wires: tuple[int, ...]

    def __init__(self, preparation: Circuit, free_wires: tuple[int, ...]) -> None:
        if type(preparation) is not Circuit:
            raise TypeError("preparation must be a reversible Circuit")
        preparation.validate()
        if (type(free_wires) is not tuple or
                any(type(q) is not int or not 0 <= q < preparation.width for q in free_wires)
                or len(set(free_wires)) != len(free_wires)):
            raise ValueError("free_wires must be distinct valid wire indices")
        object.__setattr__(self, "data", preparation.width)
        object.__setattr__(self, "gates", tuple(preparation.gates))
        object.__setattr__(self, "free_wires", free_wires)

    @property
    def preparation(self) -> Circuit:
        """A detached copy; mutating it cannot alter the domain or its digest."""
        return Circuit(self.data, list(self.gates))

    @property
    def parameters(self) -> int:
        return len(self.free_wires)

    def symbolic(self, algebra: Any, offset: int, guard: Guard) -> tuple[tuple, Any]:
        _space(algebra, offset, self.parameters)
        state = [algebra.zero() for _ in range(self.data)]
        for index, wire in enumerate(self.free_wires):
            state[wire] = algebra.variable(offset + index)
        for gate in self.gates:
            guard.check_time()
            value = algebra.product(tuple(state[q] for q in gate.controls))
            state[gate.target] = algebra.xor(state[gate.target], value)
        guard.check_time()
        return tuple(state), algebra.one()

    def decode(self, value: int) -> int:
        _assignment(value, self.parameters)
        initial = sum(((value >> index) & 1) << wire
                      for index, wire in enumerate(self.free_wires))
        return self.preparation.run(initial)

    def contains(self, value: int) -> bool:
        if type(value) is not int or value < 0 or value >> self.data:
            return False
        initial = self.preparation.inverse().run(value)
        allowed = sum(1 << wire for wire in self.free_wires)
        return not initial & ~allowed

    def to_dict(self) -> dict:
        return {"kind": "prepared", "data": self.data,
                "gates": [{"name": g.name, "qubits": list(g.qubits)} for g in self.gates],
                "free_wires": list(self.free_wires)}


def expression_to_dict(expression: Expr) -> dict:
    # validate first, including the depth limit and nested grammar closure.
    from symq.sat.assumptions import variables
    validate(expression, variables(expression))
    if type(expression) is Const:
        return {"kind": "const", "value": expression.value}
    if type(expression) is Var:
        return {"kind": "var", "name": expression.name}
    if type(expression) is Not:
        return {"kind": "not", "operand": expression_to_dict(expression.operand)}
    kinds = {Xor: "xor", And: "and", Eq: "eq"}
    if type(expression) not in kinds:
        raise ValueError("unsupported expression node")
    return {"kind": kinds[type(expression)], "left": expression_to_dict(expression.left),
            "right": expression_to_dict(expression.right)}


def expression_from_dict(value: Any, *, _depth: int = 0) -> Expr:
    from symq.sat.assumptions import MAX_DEPTH
    if _depth > MAX_DEPTH:
        raise ValueError("predicate exceeds expression depth limit")
    if type(value) is not dict:
        raise ValueError("predicate expression must be an object")
    kind = value.get("kind")
    if kind == "const":
        _keys(value, {"kind", "value"}, "constant")
        return Const(value["value"])
    if kind == "var":
        _keys(value, {"kind", "name"}, "variable")
        return Var(value["name"])
    if kind == "not":
        _keys(value, {"kind", "operand"}, "negation")
        return Not(expression_from_dict(value["operand"], _depth=_depth + 1))
    constructors = {"xor": Xor, "and": And, "eq": Eq}
    if kind not in constructors:
        raise ValueError(f"unsupported predicate node {kind!r}")
    _keys(value, {"kind", "left", "right"}, "binary expression")
    return constructors[kind](expression_from_dict(value["left"], _depth=_depth + 1),
                              expression_from_dict(value["right"], _depth=_depth + 1))


@dataclass(frozen=True)
class PredicateDomain(_Domain):
    data: int
    predicate: Expr

    def __post_init__(self) -> None:
        _dimension(self.data)
        validate(self.predicate, frozenset(f"x.{q}" for q in range(self.data)))
        # Strict node classes, with an immutable normalised reconstruction.
        object.__setattr__(self, "predicate", expression_from_dict(
            expression_to_dict(self.predicate)))

    @property
    def parameters(self) -> int:
        return self.data

    def symbolic(self, algebra: Any, offset: int, guard: Guard) -> tuple[tuple, Any]:
        state, _ = FullCube(self.data).symbolic(algebra, offset, guard)

        def compile_node(expression: Expr) -> Any:
            guard.check_time()
            if type(expression) is Const:
                return algebra.one() if expression.value else algebra.zero()
            if type(expression) is Var:
                return state[int(expression.name.split(".")[1])]
            if type(expression) is Not:
                return algebra.xor(algebra.one(), compile_node(expression.operand))
            left, right = compile_node(expression.left), compile_node(expression.right)
            if type(expression) is And:
                return algebra.product((left, right))
            value = algebra.xor(left, right)
            return algebra.xor(algebra.one(), value) if type(expression) is Eq else value

        return state, compile_node(self.predicate)

    def decode(self, value: int) -> int:
        return _assignment(value, self.data)

    def contains(self, value: int) -> bool:
        if type(value) is not int or value < 0 or value >> self.data:
            return False
        return evaluate(self.predicate, {f"x.{q}": (value >> q) & 1
                                         for q in range(self.data)})

    def to_dict(self) -> dict:
        return {"kind": "predicate", "data": self.data,
                "predicate": expression_to_dict(self.predicate)}


Domain = FullCube | AffineDomain | PreparedDomain | PredicateDomain


def domain_from_dict(value: Any) -> Domain:
    if type(value) is not dict:
        raise ValueError("domain must be an object")
    kind = value.get("kind")
    if kind == "full_cube":
        _keys(value, {"kind", "data"}, "full cube domain")
        return FullCube(value["data"])
    if kind == "affine":
        _keys(value, {"kind", "data", "offset", "basis"}, "affine domain")
        if type(value["basis"]) is not list:
            raise ValueError("affine basis must be an array")
        return AffineDomain(value["data"], value["offset"], tuple(value["basis"]))
    if kind == "prepared":
        _keys(value, {"kind", "data", "gates", "free_wires"}, "prepared domain")
        if type(value["gates"]) is not list or type(value["free_wires"]) is not list:
            raise ValueError("prepared gates and free_wires must be arrays")
        gates = []
        for gate in value["gates"]:
            _keys(gate, {"name", "qubits"}, "preparation gate")
            if type(gate["qubits"]) is not list:
                raise ValueError("gate qubits must be an array")
            gates.append(Gate(gate["name"], tuple(gate["qubits"])))
        return PreparedDomain(Circuit(value["data"], gates), tuple(value["free_wires"]))
    if kind == "predicate":
        _keys(value, {"kind", "data", "predicate"}, "predicate domain")
        return PredicateDomain(value["data"], expression_from_dict(value["predicate"]))
    raise ValueError(f"unsupported domain kind {kind!r}")
