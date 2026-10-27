"""Exact X/CX/CCX/MCX reversible circuits on computational basis states."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .anf import ANF


class UnsupportedOperation(ValueError):
    """Instruction outside the explicitly supported reversible subset."""


@dataclass(frozen=True)
class Gate:
    name: str
    qubits: tuple[int, ...]

    def __post_init__(self) -> None:
        expected = {"x": 1, "cx": 2, "ccx": 3}
        if self.name not in expected and self.name != "mcx":
            raise UnsupportedOperation(self.name)
        if self.name in expected and len(self.qubits) != expected[self.name]:
            raise ValueError("incorrect gate arity")
        if self.name == "mcx" and len(self.qubits) < 2:
            raise ValueError("mcx requires controls and target")
        if len(set(self.qubits)) != len(self.qubits):
            raise ValueError("control and target qubits must be distinct")
        if any(not isinstance(q, int) or q < 0 for q in self.qubits):
            raise ValueError("qubit indices must be nonnegative integers")


@dataclass
class Circuit:
    width: int
    gates: list[Gate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.width, int) or self.width < 1:
            raise ValueError("width must be positive")
        for gate in self.gates:
            self._validate(gate)

    def _validate(self, gate: Gate) -> None:
        if any(q >= self.width for q in gate.qubits):
            raise ValueError("qubit index out of range")

    def append(self, name: str, *qubits: int) -> Circuit:
        gate = Gate(name, tuple(qubits))
        self._validate(gate)
        self.gates.append(gate)
        return self

    def x(self, target: int) -> Circuit:
        return self.append("x", target)

    def cx(self, control: int, target: int) -> Circuit:
        return self.append("cx", control, target)

    def ccx(self, a: int, b: int, target: int) -> Circuit:
        return self.append("ccx", a, b, target)

    def mcx(self, *qubits: int) -> Circuit:
        return self.append("mcx", *qubits)

    def run(self, assignment: int) -> int:
        if not isinstance(assignment, int) or not 0 <= assignment < (1 << self.width):
            raise ValueError("assignment outside circuit width")
        value = assignment
        for gate in self.gates:
            *controls, target = gate.qubits
            if all(value & (1 << c) for c in controls):
                value ^= 1 << target
        return value

    def symbolic(self) -> tuple[ANF, ...]:
        state = [ANF.variable(i) for i in range(self.width)]
        for gate in self.gates:
            *controls, target = gate.qubits
            expression = ANF.constant(1)
            for control in controls:
                expression = expression * state[control]
            state[target] = state[target] ^ expression
        return tuple(state)

    def inverse(self) -> Circuit:
        # Each supported controlled-X gate is self-inverse.
        return Circuit(self.width, list(reversed(self.gates)))

    def subcircuit(self, qubits: Sequence[int]) -> Circuit:
        """Gates acting only on ``qubits``, reindexed to ``0..len(qubits)-1`` in sorted order.

        Gates disjoint from ``qubits`` are dropped; a gate touching both ``qubits`` and other
        wires raises ``ValueError``, since dropping it would change the restricted function.
        """
        mapping = {orig: local for local, orig in enumerate(sorted(set(qubits)))}
        if any(not isinstance(q, int) or not 0 <= q < self.width for q in mapping):
            raise ValueError("qubit index out of range")
        gates = []
        for gate in self.gates:
            inside = sum(q in mapping for q in gate.qubits)
            if inside == len(gate.qubits):
                gates.append(Gate(gate.name, tuple(mapping[q] for q in gate.qubits)))
            elif inside:
                raise ValueError(f"gate {gate} crosses the boundary of the selected wires")
        return Circuit(len(mapping), gates)

    def wire_blocks(self) -> list[list[int]]:
        """Wires grouped by gate interaction (connected components), sorted by first wire."""
        parent = list(range(self.width))

        def find(i: int) -> int:
            root = i
            while parent[root] != root:
                root = parent[root]
            while parent[i] != root:
                parent[i], i = root, parent[i]
            return root

        for gate in self.gates:
            first = find(gate.qubits[0])
            for q in gate.qubits[1:]:
                other = find(q)
                if other != first:
                    parent[other] = first

        groups: dict[int, list[int]] = {}
        for q in range(self.width):
            groups.setdefault(find(q), []).append(q)
        return sorted(groups.values())

    def connected_components(self) -> list[tuple[list[int], Circuit]]:
        """``(wires, subcircuit)`` for each block of :meth:`wire_blocks`."""
        return [(qubits, self.subcircuit(qubits)) for qubits in self.wire_blocks()]

    def equivalent(self, other: Circuit, *, max_width: int = 16) -> bool:
        """Exact exhaustive equivalence, refusing infeasible input widths."""
        if not isinstance(other, Circuit) or self.width != other.width:
            return False
        if self.width > max_width:
            raise ValueError("exhaustive verification width limit exceeded")
        return all(self.run(x) == other.run(x) for x in range(1 << self.width))
