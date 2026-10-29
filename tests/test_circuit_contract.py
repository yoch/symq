"""The public Circuit IR is validated before any execution, comparison or certification."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from symq import Circuit, Gate, check_equivalence, make_algebra, simulate
from symq.circuit import UnsupportedOperation


def test_duck_typed_gate_objects_are_rejected():
    with pytest.raises(TypeError, match="not a Gate"):
        Circuit(1, [SimpleNamespace(name="h", qubits=(0,))])


def test_unknown_operations_are_rejected_at_construction():
    with pytest.raises(UnsupportedOperation):
        Gate("h", (0,))
    with pytest.raises(ValueError, match="takes 2 qubits"):
        Gate("cx", (0, 1, 2))
    with pytest.raises(ValueError, match="distinct"):
        Gate("cx", (1, 1))


@pytest.mark.parametrize("qubits", [(0.0,), (True,), ("0",), (-1,)])
def test_non_integer_qubits_are_rejected(qubits):
    with pytest.raises((TypeError, ValueError)):
        Gate("x", qubits)


def test_gate_qubits_are_normalised_to_an_immutable_tuple():
    wires = [0, 1]
    gate = Gate("cx", wires)
    wires[0] = 1
    assert gate.qubits == (0, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        gate.qubits = (1, 0)


def test_mutating_the_public_gate_list_fails_closed():
    circuit = Circuit(2).cx(0, 1)
    circuit.gates.append(SimpleNamespace(name="h", qubits=(0,)))
    with pytest.raises(TypeError, match="not a Gate"):
        circuit.run(0)
    with pytest.raises(TypeError, match="not a Gate"):
        circuit.symbolic()
    with pytest.raises(TypeError, match="not a Gate"):
        circuit.equivalent(Circuit(2).cx(0, 1))
    with pytest.raises(TypeError, match="not a Gate"):
        simulate(circuit, make_algebra("zdd", 2))


def test_a_gate_list_modified_to_leave_the_width_fails_closed():
    circuit = Circuit(2).cx(0, 1)
    circuit.gates.append(Gate("x", (1,)))
    circuit.gates[-1] = Gate("x", (0,))
    circuit.width = 1
    with pytest.raises(ValueError, match="outside width"):
        circuit.run(0)


def test_duck_typed_circuit_is_not_certified():
    fake = SimpleNamespace(width=1, gates=[SimpleNamespace(name="h", qubits=(0,))],
                           run=lambda value: value ^ 1)
    fake.width = 1
    assert not Circuit(1).x(0).equivalent(fake)
    with pytest.raises(TypeError):
        check_equivalence(Circuit(1).x(0), fake)


def test_a_circuit_whose_gates_are_not_a_gate_list_is_rejected():
    with pytest.raises(TypeError):
        Circuit(1, "x")
    with pytest.raises(TypeError):
        Circuit(1, [("x", 0)])


def test_valid_circuits_are_unchanged():
    circuit = Circuit(3).cx(0, 1).ccx(0, 1, 2).mcx(0, 1, 2)
    expected = [circuit.run(x) for x in range(8)]
    assert len(set(expected)) == 8
    assert circuit.inverse().equivalent(circuit)
    assert Circuit(3, list(circuit.gates)).symbolic() == circuit.symbolic()


def test_equivalence_still_decides_valid_pairs():
    left = Circuit(2).x(1).cx(0, 1)
    right = Circuit(2).cx(0, 1).x(1)
    assert left.equivalent(right)
    assert not left.equivalent(Circuit(2).cx(0, 1))
    assert check_equivalence(left, right, backend="zdd").equivalent
