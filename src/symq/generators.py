"""Seeded circuit generators: random circuits, sound rewrites and structural mutants."""
from __future__ import annotations

import random

from .circuit import Circuit, Gate


def random_gate(width: int, rng: random.Random, *, max_controls: int = 3) -> Gate:
    controls = rng.randint(0, min(max_controls, width - 1))
    qubits = rng.sample(range(width), controls + 1)
    return Gate("x" if controls == 0 else "mcx", tuple(qubits))


def random_circuit(
    width: int, gates: int, rng: random.Random, *, max_controls: int = 3
) -> Circuit:
    return Circuit(width, [random_gate(width, rng, max_controls=max_controls) for _ in range(gates)])


def commute(first: Gate, second: Gate) -> bool:
    """Sufficient condition: neither target is a control of the other gate."""
    return first.qubits[-1] not in second.qubits[:-1] and second.qubits[-1] not in first.qubits[:-1]


def equivalent_variant(
    circuit: Circuit, rng: random.Random, *, steps: int = 20, max_controls: int = 3
) -> Circuit:
    """Apply only semantics-preserving rewrites: swaps of commuting neighbours and
    insertion of a self-cancelling pair ``g g``."""
    gates = list(circuit.gates)
    for _ in range(steps):
        if len(gates) >= 2 and rng.random() < 0.7:
            i = rng.randrange(len(gates) - 1)
            if commute(gates[i], gates[i + 1]):
                gates[i], gates[i + 1] = gates[i + 1], gates[i]
        else:
            gate = random_gate(circuit.width, rng, max_controls=max_controls)
            i = rng.randint(0, len(gates))
            gates[i:i] = [gate, gate]
    return Circuit(circuit.width, gates)


MUTATIONS = ("delete", "insert", "retarget", "add_control", "drop_control")


def mutate(circuit: Circuit, rng: random.Random, kind: str | None = None) -> tuple[Circuit, str]:
    """One structural edit. The result may still be equivalent; callers need an oracle."""
    gates = list(circuit.gates)
    applicable = [k for k in MUTATIONS if k == "insert" or gates]
    if kind is None:
        kind = rng.choice(applicable)
    elif kind not in applicable:
        raise ValueError(f"mutation {kind!r} not applicable")
    if kind == "insert":
        gates.insert(rng.randint(0, len(gates)), random_gate(circuit.width, rng))
        return Circuit(circuit.width, gates), kind
    i = rng.randrange(len(gates))
    qubits = list(gates[i].qubits)
    free = [q for q in range(circuit.width) if q not in qubits]
    if kind == "delete":
        del gates[i]
    elif kind == "retarget" and free:
        qubits[-1] = rng.choice(free)
        gates[i] = Gate(gates[i].name, tuple(qubits))
    elif kind == "add_control" and free:
        gates[i] = Gate("mcx", (*qubits[:-1], rng.choice(free), qubits[-1]))
    elif kind == "drop_control" and len(qubits) > 1:
        del qubits[rng.randrange(len(qubits) - 1)]
        gates[i] = Gate("x" if len(qubits) == 1 else "mcx", tuple(qubits))
    else:
        del gates[i]
        kind = "delete"
    return Circuit(circuit.width, gates), kind
