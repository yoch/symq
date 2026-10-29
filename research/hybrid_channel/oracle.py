"""Exact small CPTP channel oracle for a CLOSED hybrid quantum/classical grammar.

This is a research reference, NOT the symbolic scalable verifier or a general
Hadamard simulator. It deliberately makes no imports from other repositories.

The accepted gates are reversible basis permutations (X/CX/CCX/MCX/SWAP/CSWAP),
diagonal sign phases (Z/CZ/CCZ), X-basis HMR, Z-basis measurement, *true*
standalone reset, and measured-outcome-controlled value or sign gates.
Each measurement is an immutable event; mutable classical slots are separate.

The input to the channel is any coherent data state, with every ancilla in |0>.
The channel is established by its action on ALL |x><y|, not on diagonals alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from symq.circuit import UnsupportedOperation
from symq.resources import Budget, Guard, ResourceLimitExceeded

Matrix = dict[tuple[int, int], Fraction]
_BIT = re.compile(r"b(0|[1-9][0-9]*)\Z")
_ARITY = {
    "x": 1, "cx": 2, "ccx": 3, "swap": 2, "cswap": 3,
    "z": 1, "cz": 2, "ccz": 3, "neg": 0,
    "hmr": 1, "measure_z": 1, "reset": 1,
}
_QUANTUM = set(_ARITY) | {"mcx"}
_CONTROLLED = {"x", "cx", "ccx", "mcx", "swap", "cswap",
               "z", "cz", "ccz", "neg"}


def _slot(value: str) -> bool:
    return type(value) is str and _BIT.fullmatch(value) is not None


@dataclass(frozen=True)
class HOp:
    kind: str
    wires: tuple[int, ...] = ()
    slot: str | None = None
    condition: str | None = None
    source: str | None = None
    value: int | None = None


@dataclass
class HybridProgram:
    data: int
    ancillas: int = 0
    ops: list[HOp] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    @property
    def width(self) -> int:
        return self.data + self.ancillas

    def validate(self) -> None:
        if type(self.data) is not int or self.data < 1:
            raise ValueError("at least one data wire is required")
        if type(self.ancillas) is not int or self.ancillas < 0:
            raise ValueError("ancillas must be nonnegative")
        if type(self.ops) is not list:
            raise UnsupportedOperation("ops must be a list")
        initialized: set[str] = set()
        for index, op in enumerate(self.ops):
            where = f"op {index}"
            if type(op) is not HOp:
                raise UnsupportedOperation(f"{where}: HOp required")
            kind, wires = op.kind, op.wires
            if kind not in _QUANTUM | {"store", "invert", "oxor"}:
                raise UnsupportedOperation(f"{where}: unsupported {kind!r}")
            if type(wires) is not tuple or any(type(q) is not int or
                                               q < 0 or q >= self.width for q in wires):
                raise UnsupportedOperation(f"{where}: invalid wire indices")
            if len(set(wires)) != len(wires):
                raise UnsupportedOperation(f"{where}: repeated wire")
            arity = _ARITY.get(kind)
            if arity is not None and len(wires) != arity:
                raise UnsupportedOperation(f"{where}: incorrect arity")
            if kind == "mcx" and len(wires) < 2:
                raise UnsupportedOperation(f"{where}: mcx needs controls and target")
            if kind in _QUANTUM and kind not in _CONTROLLED and op.condition is not None:
                raise UnsupportedOperation(f"{where}: measurement/reset cannot be guarded")
            if op.condition is not None:
                cond = op.condition.removeprefix("!")
                if not _slot(cond) or cond not in initialized:
                    raise UnsupportedOperation(f"{where}: uninitialized classical condition")
            if kind in _QUANTUM:
                if kind in {"hmr", "measure_z"}:
                    if not _slot(op.slot):
                        raise UnsupportedOperation(f"{where}: measurement needs a classical slot")
                    initialized.add(op.slot)
                elif op.slot is not None:
                    raise UnsupportedOperation(f"{where}: unexpected classical output slot")
                if op.source is not None or op.value is not None:
                    raise UnsupportedOperation(f"{where}: extraneous quantum parameters")
                continue
            if wires or op.condition is not None and kind != "invert":
                raise UnsupportedOperation(f"{where}: invalid classical arguments")
            if not _slot(op.slot):
                raise UnsupportedOperation(f"{where}: classical destination required")
            if kind == "store":
                if op.source is not None or type(op.value) is not int or op.value not in (0, 1):
                    raise UnsupportedOperation(f"{where}: store requires bit 0 or 1")
                initialized.add(op.slot)
            elif kind == "invert":
                if op.slot not in initialized or op.source is not None or op.value is not None:
                    raise UnsupportedOperation(f"{where}: invert needs initialized destination")
            else:  # oxor
                if (op.slot not in initialized or not _slot(op.source)
                        or op.source not in initialized or op.value is not None):
                    raise UnsupportedOperation(f"{where}: oxor needs initialized slots")

    def _add(self, kind: str, wires: tuple[int, ...] = (), *,
             slot: str | None = None, condition: str | None = None,
             source: str | None = None, value: int | None = None) -> HybridProgram:
        self.ops.append(HOp(kind, wires, slot, condition, source, value))
        try:
            self.validate()
        except (ValueError, TypeError):
            self.ops.pop()
            raise
        return self

    def x(self, q: int, *, condition: str | None = None) -> HybridProgram:
        return self._add("x", (q,), condition=condition)

    def cx(self, c: int, t: int, *, condition: str | None = None) -> HybridProgram:
        return self._add("cx", (c, t), condition=condition)

    def ccx(self, a: int, b: int, t: int, *,
            condition: str | None = None) -> HybridProgram:
        return self._add("ccx", (a, b, t), condition=condition)

    def mcx(self, *wires: int, condition: str | None = None) -> HybridProgram:
        return self._add("mcx", wires, condition=condition)

    def swap(self, a: int, b: int, *, condition: str | None = None) -> HybridProgram:
        return self._add("swap", (a, b), condition=condition)

    def cswap(self, c: int, a: int, b: int, *,
              condition: str | None = None) -> HybridProgram:
        return self._add("cswap", (c, a, b), condition=condition)

    def z(self, q: int, *, condition: str | None = None) -> HybridProgram:
        return self._add("z", (q,), condition=condition)

    def cz(self, a: int, b: int, *, condition: str | None = None) -> HybridProgram:
        return self._add("cz", (a, b), condition=condition)

    def ccz(self, a: int, b: int, c: int, *,
            condition: str | None = None) -> HybridProgram:
        return self._add("ccz", (a, b, c), condition=condition)

    def neg(self, *, condition: str | None = None) -> HybridProgram:
        return self._add("neg", (), condition=condition)

    def hmr(self, q: int, slot: str) -> HybridProgram:
        return self._add("hmr", (q,), slot=slot)

    def measure_z(self, q: int, slot: str) -> HybridProgram:
        return self._add("measure_z", (q,), slot=slot)

    def reset(self, q: int) -> HybridProgram:
        return self._add("reset", (q,))

    def store(self, dest: str, bit: int) -> HybridProgram:
        return self._add("store", slot=dest, value=bit)

    def invert(self, dest: str, *, condition: str | None = None) -> HybridProgram:
        return self._add("invert", slot=dest, condition=condition)

    def oxor(self, dest: str, source: str) -> HybridProgram:
        return self._add("oxor", slot=dest, source=source)


@dataclass
class _Branch:
    matrix: Matrix
    classical: dict[str, int]
    events: tuple[int, ...]


@dataclass(frozen=True)
class ChannelResult:
    equivalent: bool
    trace_ancillas: bool
    checked_pairs: int
    witness: tuple[int, int] | None = None


def _add(matrix: Matrix, key: tuple[int, int], value: Fraction) -> None:
    if not value:
        return
    total = matrix.get(key, Fraction(0)) + value
    if total:
        matrix[key] = total
    else:
        matrix.pop(key, None)


def _permute(value: int, op: HOp) -> int:
    kind, qs = op.kind, op.wires
    if kind in {"x", "cx", "ccx", "mcx"}:
        *controls, target = qs
        return value ^ (1 << target) if all(value >> c & 1 for c in controls) else value
    if kind == "swap":
        a, b = qs
        return value ^ ((1 << a) | (1 << b)) if ((value >> a) ^ (value >> b)) & 1 else value
    if kind == "cswap":
        c, a, b = qs
        return (value ^ ((1 << a) | (1 << b))
                if (value >> c & 1) and (((value >> a) ^ (value >> b)) & 1) else value)
    raise UnsupportedOperation(f"unsupported permutation {kind!r}")


def _sign(value: int, op: HOp) -> int:
    if op.kind == "neg":
        return -1
    return -1 if all(value >> q & 1 for q in op.wires) else 1


def _condition(condition: str | None, classical: dict[str, int]) -> bool:
    if condition is None:
        return True
    inverted = condition.startswith("!")
    name = condition[1:] if inverted else condition
    return bool(classical[name] ^ int(inverted))


def _quantum_step(matrix: Matrix, op: HOp, guard: Guard) -> Matrix:
    result: Matrix = {}
    permutation = op.kind in {"x", "cx", "ccx", "mcx", "swap", "cswap"}
    for (row, col), coeff in matrix.items():
        guard.check_time()
        if permutation:
            newrow, newcol = _permute(row, op), _permute(col, op)
            _add(result, (newrow, newcol), coeff)
        else:
            _add(result, (row, col), coeff * _sign(row, op) * _sign(col, op))
        guard.check_terms(len(result))
    return result


def _measure(matrix: Matrix, q: int, outcome: int, *,
             x_basis: bool, guard: Guard) -> Matrix:
    """The exact normalized Kraus action; HMR has coefficient 1/2."""
    bit = 1 << q
    result: Matrix = {}
    for (row, col), coeff in matrix.items():
        guard.check_time()
        a, b = int(bool(row & bit)), int(bool(col & bit))
        if x_basis:
            phase = -1 if outcome and (a ^ b) else 1
            _add(result, (row & ~bit, col & ~bit),
                 coeff * Fraction(phase, 2))
        elif a == b == outcome:
            _add(result, (row, col), coeff)
        guard.check_terms(len(result))
    return result


def _reset(matrix: Matrix, q: int, guard: Guard) -> Matrix:
    """CPTP trace-out-and-prepare |0>, not classical assignment or a unitary."""
    bit = 1 << q
    out: Matrix = {}
    for (row, col), coeff in matrix.items():
        guard.check_time()
        if bool(row & bit) == bool(col & bit):
            _add(out, (row & ~bit, col & ~bit), coeff)
        guard.check_terms(len(out))
    return out


def _partial_trace(matrix: Matrix, data: int) -> Matrix:
    out: Matrix = {}
    mask = (1 << data) - 1
    for (row, col), coeff in matrix.items():
        if row >> data == col >> data:
            _add(out, (row & mask, col & mask), coeff)
    return out


def _evolve(program: HybridProgram, x: int, y: int, *,
            guard: Guard, max_events: int, max_branches: int) -> Matrix:
    branches = [_Branch({(x, y): Fraction(1)}, {}, ())]
    for op in program.ops:
        guard.check_time()
        if op.kind in {"store", "invert", "oxor"}:
            for branch in branches:
                if op.kind == "store":
                    branch.classical[op.slot] = op.value
                elif op.kind == "invert":
                    branch.classical[op.slot] ^= int(_condition(op.condition, branch.classical))
                else:
                    branch.classical[op.slot] ^= branch.classical[op.source]
        elif op.kind in {"hmr", "measure_z"}:
            next_branches: list[_Branch] = []
            if len(branches) * 2 > max_branches:
                raise ResourceLimitExceeded("branches", max_branches, len(branches) * 2)
            for branch in branches:
                for outcome in (0, 1):
                    matrix = _measure(branch.matrix, op.wires[0], outcome,
                                      x_basis=op.kind == "hmr", guard=guard)
                    if matrix:
                        table = branch.classical.copy()
                        table[op.slot] = outcome
                        next_branches.append(_Branch(matrix, table, branch.events + (outcome,)))
            branches = next_branches
        elif op.kind == "reset":
            for branch in branches:
                branch.matrix = _reset(branch.matrix, op.wires[0], guard)
        else:
            for branch in branches:
                if _condition(op.condition, branch.classical):
                    branch.matrix = _quantum_step(branch.matrix, op, guard)
        if len(branches) > max_branches:
            raise ResourceLimitExceeded("branches", max_branches, len(branches))
        guard.check_terms(sum(len(b.matrix) for b in branches))
        if branches and max(len(b.events) for b in branches) > max_events:
            raise ResourceLimitExceeded("events", max_events,
                                        max(len(b.events) for b in branches))
    result: Matrix = {}
    for branch in branches:
        for key, coeff in branch.matrix.items():
            _add(result, key, coeff)
    guard.check_terms(len(result))
    return result


def coherence_image(
    program: HybridProgram, x: int, y: int, *, trace_ancillas: bool = False,
    budget: Budget | None = None, max_width: int = 6, max_events: int = 8,
    max_branches: int = 256, _guard: Guard | None = None,
) -> Matrix:
    """Exact E(|x><y|) on data, with ancillas initially |0>.

    Returns full output including ancillas, or its partial trace on data.
    This is an *exponential-size* oracle with strict explicit width/event caps.
    """
    guard = _guard if _guard is not None else Guard(budget)
    guard.check_time()
    if type(program) is not HybridProgram:
        raise TypeError("HybridProgram required")
    program.validate()
    if type(x) is not int or type(y) is not int or not (
        0 <= x < 1 << program.data and 0 <= y < 1 << program.data
    ):
        raise ValueError("basis-coherence pair outside the data input width")
    for name, val in (("max_width", max_width), ("max_events", max_events),
                      ("max_branches", max_branches)):
        if type(val) is not int or val < 1:
            raise ValueError(f"{name} must be a positive integer")
    if guard.budget.max_nodes is not None:
        raise ValueError("max_nodes is not supported by the density-matrix oracle")
    if program.width > max_width:
        raise ResourceLimitExceeded("width", max_width, program.width)
    event_count = sum(op.kind in {"hmr", "measure_z"} for op in program.ops)
    if event_count > max_events:
        raise ResourceLimitExceeded("events", max_events, event_count)
    output = _evolve(program, x, y, guard=guard, max_events=max_events,
                     max_branches=max_branches)
    if trace_ancillas:
        output = _partial_trace(output, program.data)
    guard.check_time()
    guard.check_terms(len(output))
    return output


def same_channel(
    left: HybridProgram, right: HybridProgram, *, trace_ancillas: bool = False,
    budget: Budget | None = None, max_width: int = 6, max_events: int = 8,
    max_branches: int = 256,
) -> ChannelResult:
    """Full, exact channel comparison on all |x><y| pairs (or reduced channel).

    A difference has a concrete input-coherence witness (x,y).
    This method does not enumerate superposition states: linearity makes the
    full set of matrix units a complete basis of input density operators.
    """
    guard = Guard(budget)
    guard.check_time()
    if type(left) is not HybridProgram or type(right) is not HybridProgram:
        raise TypeError("two HybridPrograms required")
    left.validate()
    right.validate()
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("matching data and ancilla widths required")
    checked = 0
    for x in range(1 << left.data):
        for y in range(1 << left.data):
            guard.check_time()
            a = coherence_image(
                left, x, y, trace_ancillas=trace_ancillas, _guard=guard,
                max_width=max_width, max_events=max_events,
                max_branches=max_branches,
            )
            b = coherence_image(
                right, x, y, trace_ancillas=trace_ancillas, _guard=guard,
                max_width=max_width, max_events=max_events,
                max_branches=max_branches,
            )
            checked += 1
            if a != b:
                return ChannelResult(False, trace_ancillas, checked, (x, y))
    guard.check_time()
    return ChannelResult(True, trace_ancillas, checked)
