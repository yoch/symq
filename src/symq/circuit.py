"""Exact X/CX/CCX/MCX reversible circuits on computational basis states."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .anf import ANF

ARITY = {"x": 1, "cx": 2, "ccx": 3}


class UnsupportedOperation(ValueError):
    """Instruction outside the explicitly supported reversible subset."""


@dataclass(frozen=True)
class Gate:
    """One gate: an operation name and its qubits, controls first, target last.

    Instances are immutable and self-validating, so a gate can be shared between circuits and
    no caller can change its qubits after construction. ``__post_init__`` normalises ``qubits``
    to a tuple of plain integers and rejects unsupported names, wrong arities, repeated wires
    and non-integer or negative indices.
    """

    name: str
    qubits: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise UnsupportedOperation(f"gate name must be a string, not {type(self.name).__name__}")
        if self.name not in ARITY and self.name != "mcx":
            raise UnsupportedOperation(self.name)
        if isinstance(self.qubits, (str, bytes)) or not isinstance(self.qubits, Iterable):
            raise TypeError("gate qubits must be a sequence of integers")
        qubits = tuple(self.qubits)
        if not all(type(q) is int for q in qubits):
            raise TypeError("gate qubits must be nonnegative integers, not bool or other types")
        if self.name in ARITY and len(qubits) != ARITY[self.name]:
            raise ValueError(f"{self.name} takes {ARITY[self.name]} qubits, got {len(qubits)}")
        if self.name == "mcx" and len(qubits) < 2:
            raise ValueError("mcx requires controls and target")
        if any(q < 0 for q in qubits):
            raise ValueError("gate qubits must be nonnegative integers")
        if len(set(qubits)) != len(qubits):
            raise ValueError("control and target qubits must be distinct")
        object.__setattr__(self, "qubits", qubits)

    @property
    def controls(self) -> tuple[int, ...]:
        return self.qubits[:-1]

    @property
    def target(self) -> int:
        return self.qubits[-1]


@dataclass
class Circuit:
    """A width and an ordered list of gates.

    The gate list is validated on construction and again at every public entry point, because
    ``gates`` is a public list that a caller can mutate after construction. Validation raises
    and never returns a partial verdict, so a malformed program cannot be certified by
    accident.
    """

    width: int
    gates: list[Gate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if type(self.width) is not int or self.width < 1:
            raise ValueError("width must be positive")
        if isinstance(self.gates, (str, bytes)) or not isinstance(self.gates, Iterable):
            raise TypeError("gates must be a sequence of Gate")
        if not isinstance(self.gates, list):
            self.gates = list(self.gates)
        self.validate()

    def validate(self) -> Circuit:
        """Re-check the whole IR; returns ``self`` so calls can be chained."""
        if type(self.width) is not int or self.width < 1:
            raise ValueError("width must be positive")
        for index, gate in enumerate(self.gates):
            if type(gate) is not Gate:
                raise TypeError(
                    f"gate {index} is a {type(gate).__name__}, not a Gate; "
                    "build circuits with Circuit.append or Gate(...)")
            if any(q >= self.width for q in gate.qubits):
                raise ValueError(f"gate {index} ({gate.name}) has a qubit outside width {self.width}")
        return self

    def append(self, name: str, *qubits: int) -> Circuit:
        gate = Gate(name, tuple(qubits))
        if any(q >= self.width for q in gate.qubits):
            raise ValueError("qubit index out of range")
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
        self.validate()
        if type(assignment) is not int or not 0 <= assignment < (1 << self.width):
            raise ValueError("assignment outside circuit width")
        value = assignment
        for gate in self.gates:
            *controls, target = gate.qubits
            if all(value & (1 << c) for c in controls):
                value ^= 1 << target
        return value

    def symbolic(self) -> tuple[ANF, ...]:
        self.validate()
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
        self.validate()
        mapping = {orig: local for local, orig in enumerate(sorted(set(qubits)))}
        if any(type(q) is not int or not 0 <= q < self.width for q in mapping):
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
        self.validate()
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
        """Exact exhaustive equivalence, refusing infeasible input widths.

        A non-``Circuit`` argument is not equivalent to anything: a duck-typed object is
        never certified (use ``check_equivalence`` for an explicit ``TypeError``).
        """
        self.validate()
        if not isinstance(other, Circuit):
            return False
        other.validate()
        if self.width != other.width:
            return False
        if self.width > max_width:
            raise ValueError("exhaustive verification width limit exceeded")
        return all(self.run(x) == other.run(x) for x in range(1 << self.width))
