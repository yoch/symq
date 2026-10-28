"""The variable-order policy: reversible, explicit, and never silent about the order used."""
from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

from symq import POLICIES, Circuit, algebra_order, make_algebra, order_for, simulate
from symq.generators import random_circuit

ROOT = Path(__file__).resolve().parents[1]


def load_adders():
    """The experiment's adder generator, loaded by path (``research/`` is not a package)."""
    path = ROOT / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("engineering_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["engineering_adders"] = module
    spec.loader.exec_module(module)
    return module


def test_the_identity_policy_is_the_default_and_is_unchanged():
    circuit = Circuit(4)
    assert order_for(circuit) == (0, 1, 2, 3)
    assert order_for(circuit, "identity") == (0, 1, 2, 3)
    assert algebra_order(4) == (0, 1, 2, 3)


def test_the_reversed_policy_reverses():
    circuit = Circuit(5)
    assert order_for(circuit, "reversed") == (4, 3, 2, 1, 0)
    assert algebra_order(5, "reversed") == (4, 3, 2, 1, 0)


def test_unknown_policies_are_rejected_explicitly():
    with pytest.raises(ValueError, match="unknown order policy"):
        order_for(Circuit(3), "min_fill")
    with pytest.raises(ValueError, match="unknown order policy"):
        algebra_order(3, "degree")
    assert set(POLICIES) == {"identity", "reversed"}


def test_a_non_circuit_is_rejected():
    with pytest.raises(TypeError, match="Circuit is required"):
        order_for("not a circuit")  # type: ignore[arg-type]


def test_the_width_is_checked():
    with pytest.raises(ValueError):
        algebra_order(0)


@pytest.mark.parametrize("policy", POLICIES)
def test_both_policies_are_permutations_at_every_width(policy):
    for width in range(1, 20):
        order = algebra_order(width, policy)
        assert sorted(order) == list(range(width))


@pytest.mark.parametrize("policy", POLICIES)
def test_the_policy_never_changes_the_function(policy):
    """An order changes the diagram, never the polynomial: outputs must be identical."""
    rng = random.Random(31)
    for seed in range(12):
        circuit = random_circuit(rng.randint(2, 6), rng.randint(0, 20), rng)
        reference = make_algebra("zdd", circuit.width)
        expected = tuple(reference.to_anf(value) for value in simulate(circuit, reference))
        algebra = make_algebra("zdd-native", circuit.width, order=order_for(circuit, policy))
        observed = tuple(algebra.to_anf(value) for value in simulate(circuit, algebra))
        assert observed == expected, (seed, policy)


def test_a_malformed_circuit_is_rejected_before_an_order_is_chosen():
    circuit = Circuit(2).cx(0, 1)
    circuit.width = 1
    with pytest.raises(ValueError, match="outside width"):
        order_for(circuit, "reversed")


def test_the_reversed_order_reduces_the_diagram_on_a_carry_chain():
    """The measured effect, pinned on a small case.

    A Cuccaro adder lays out ``c0, b[..], a[..], z`` and carries through ``a``; the reversed
    order follows the carry, so the diagram is strictly smaller. The assertion is a strict
    inequality on node counts, not a ratio, so it cannot decay into a tautology.
    """
    adders = load_adders()
    circuit = adders.adder(12)
    forward = make_algebra("zdd-native", circuit.width, order=order_for(circuit, "identity"))
    simulate(circuit, forward)
    backward = make_algebra("zdd-native", circuit.width, order=order_for(circuit, "reversed"))
    simulate(circuit, backward)
    assert backward.node_count < forward.node_count, (backward.node_count, forward.node_count)


def test_both_orders_agree_with_an_independent_backend():
    adders = load_adders()
    circuit = adders.adder(5)
    reference = make_algebra("zdd", circuit.width)
    expected = tuple(reference.to_anf(value) for value in simulate(circuit, reference))
    for policy in POLICIES:
        algebra = make_algebra("zdd-native", circuit.width, order=order_for(circuit, policy))
        assert tuple(algebra.to_anf(value) for value in simulate(circuit, algebra)) == expected
