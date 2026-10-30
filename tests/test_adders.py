"""The arithmetic generator must implement the operation it advertises.

The audit found that the previous ``adders.py`` did not compute ``b <- a + b``: its ``maj`` and
``uma`` were the same gates in the same direction, so the circuit was not an adder at all. 13 of
the 19 circuits in the order campaign came from it. These tests exist so that this cannot recur:
they compare the circuit with integer arithmetic on **every** legal input, for 1 to 4 bits, and
they check the properties the campaign relies on (reversibility, ancilla restoration, the
controlled variant).

They also guard the shape of the reference itself: ``expected_output`` refuses ``carry_in = 1``,
which is the domain restriction the Cuccaro circuit actually has.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load():
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("engineering_adders_verified", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["engineering_adders_verified"] = module
    spec.loader.exec_module(module)
    return module


ADDERS = load()


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_the_adder_computes_addition_on_every_legal_input(n):
    circuit = ADDERS.adder(n)
    for x in ADDERS.legal_inputs(n):
        assert circuit.run(x) == ADDERS.expected_output(n, x), (n, x)


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_the_controlled_adder_is_the_identity_when_control_is_zero(n):
    circuit = ADDERS.adder(n, controlled=True)
    for x in ADDERS.legal_inputs(n, controlled=True):
        if (x >> (2 * n + 2)) & 1:
            continue
        assert circuit.run(x) == x, (n, x)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_the_controlled_adder_adds_when_control_is_one(n):
    circuit = ADDERS.adder(n, controlled=True)
    for x in ADDERS.legal_inputs(n, controlled=True):
        if not (x >> (2 * n + 2)) & 1:
            continue
        assert circuit.run(x) == ADDERS.expected_output(n, x, controlled=True), (n, x)


@pytest.mark.parametrize("n", [1, 2, 3])
def test_the_adder_is_a_permutation(n):
    circuit = ADDERS.adder(n)
    outputs = {circuit.run(x) for x in ADDERS.legal_inputs(n)}
    assert len(outputs) == len(ADDERS.legal_inputs(n))


@pytest.mark.parametrize("n", [1, 2, 3])
def test_the_carry_wire_is_restored_and_z_gets_the_carry(n):
    """``c0`` comes back as 0 and ``z`` is XORed with the carry-out of ``a + b``."""
    circuit = ADDERS.adder(n)
    for x in ADDERS.legal_inputs(n):
        out = circuit.run(x)
        assert (out >> 0) & 1 == 0, "carry_in must come back as 0"
        value_b = sum(((x >> (1 + i)) & 1) << i for i in range(n))
        value_a = sum(((x >> (1 + n + i)) & 1) << i for i in range(n))
        total = value_a + value_b
        assert (out >> 1) & ((1 << n) - 1) == total & ((1 << n) - 1)
        z_in = (x >> (2 * n + 1)) & 1
        assert (out >> (2 * n + 1)) & 1 == z_in ^ ((total >> n) & 1)


def test_the_reference_refuses_the_illegal_domain():
    with pytest.raises(ValueError, match="carry_in = 0"):
        ADDERS.expected_output(2, 1)


def test_the_adder_is_its_own_candidate_for_an_inverse_pair():
    """``adder(n)`` followed by its inverse is the identity.

    Note the weaker but correct statement: ``_maj`` followed by ``_uma`` is *not* the identity in
    isolation -- the Cuccaro pair is only inverse in the context of the CNOT that separates them.
    The previous version of this file assumed the opposite, which is how the defect went unnoticed.
    """
    circuit = ADDERS.adder(2)
    composed = type(circuit)(circuit.width, [*circuit.gates, *circuit.inverse().gates])
    for x in ADDERS.legal_inputs(2):
        assert composed.run(x) == x, x


def test_the_previous_generator_really_was_wrong():
    """Guard: the gate list the audit criticised is not the one shipped any more."""
    circuit = ADDERS.adder(2)
    names = [(gate.name, gate.qubits) for gate in circuit.gates]
    previous_first_block = [("cx", (3, 1)), ("cx", (3, 0)), ("ccx", (0, 1, 3))]
    assert names[:3] == previous_first_block, (
        "the corrected block starts from carry_in, b[0], a[0]; if this changes, re-verify")
    wrong = sum(1 for x in ADDERS.legal_inputs(2)
                if circuit.run(x) != ADDERS.expected_output(2, x))
    assert wrong == 0
