"""The variable-order policy: reversible, explicit, and never silent about the order used."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from symq import POLICIES, Circuit, algebra_order, make_algebra, order_for, simulate
from symq.generators import random_circuit
from symq.generators.arithmetic import cuccaro_adder

ROOT = Path(__file__).resolve().parents[1]




def test_the_identity_policy_is_the_default_and_is_unchanged():
    circuit = Circuit(4)
    assert order_for(circuit) == (0, 1, 2, 3)
    assert order_for(circuit, "identity") == (0, 1, 2, 3)
    assert algebra_order(4) == (0, 1, 2, 3)


def test_the_reversed_policy_reverses():
    circuit = Circuit(5)
    assert order_for(circuit, "reversed") == (4, 3, 2, 1, 0)
    assert algebra_order(5, "reversed") == (4, 3, 2, 1, 0)


def test_the_last_use_policy_needs_the_gates():
    circuit = Circuit(3).cx(0, 1).cx(1, 2)
    # gate 0 touches wires 0 and 1; gate 1 touches 1 and 2, so the last uses are 0:0, 1:1, 2:1
    assert order_for(circuit, "last_use") == (1, 2, 0)
    with pytest.raises(ValueError, match="needs the circuit"):
        algebra_order(3, "last_use")


def test_unknown_policies_are_rejected_explicitly():
    with pytest.raises(ValueError, match="unknown order policy"):
        order_for(Circuit(3), "min_fill")
    with pytest.raises(ValueError, match="unknown order policy"):
        algebra_order(3, "degree")
    assert set(POLICIES) == {"identity", "reversed", "last_use"}


def test_a_non_circuit_is_rejected():
    with pytest.raises(TypeError, match="Circuit is required"):
        order_for("not a circuit")  # type: ignore[arg-type]


def test_the_width_is_checked():
    with pytest.raises(ValueError):
        algebra_order(0)


@pytest.mark.parametrize("policy", ["identity", "reversed"])
def test_both_width_only_policies_are_permutations_at_every_width(policy):
    for width in range(1, 20):
        order = algebra_order(width, policy)
        assert sorted(order) == list(range(width))


@pytest.mark.native
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


@pytest.mark.native
def test_the_reversed_order_reduces_the_diagram_on_a_carry_chain():
    """The measured effect, pinned on a small case.

    A Cuccaro adder lays out ``c0, b[..], a[..], z`` and carries through ``a``; the reversed
    order follows the carry, so the diagram is strictly smaller. The assertion is a strict
    inequality on node counts, not a ratio, so it cannot decay into a tautology.
    """
    circuit = cuccaro_adder(12)
    forward = make_algebra("zdd-native", circuit.width, order=order_for(circuit, "identity"))
    simulate(circuit, forward)
    backward = make_algebra("zdd-native", circuit.width, order=order_for(circuit, "reversed"))
    simulate(circuit, backward)
    assert backward.node_count < forward.node_count, (backward.node_count, forward.node_count)


@pytest.mark.native
def test_both_orders_agree_with_an_independent_backend():
    circuit = cuccaro_adder(5)
    reference = make_algebra("zdd", circuit.width)
    expected = tuple(reference.to_anf(value) for value in simulate(circuit, reference))
    for policy in POLICIES:
        algebra = make_algebra("zdd-native", circuit.width, order=order_for(circuit, policy))
        assert tuple(algebra.to_anf(value) for value in simulate(circuit, algebra)) == expected


@pytest.mark.native
@pytest.mark.parametrize("seed", range(8))
def test_witnesses_agree_across_backends_under_any_order(seed):
    """Every backend picks the same minimum-degree witness, whatever the variable order."""
    rng = random.Random(1000 + seed)
    circuit = random_circuit(6, 25, rng)
    mutant = random_circuit(6, 25, rng)
    order = list(range(6))
    rng.shuffle(order)
    from symq import check_equivalence

    reference = check_equivalence(circuit, mutant, backend="sparse")
    for backend in ("zdd", "zdd-native"):
        result = check_equivalence(circuit, mutant, backend=backend,
                                   backend_options={"order": order})
        assert (result.equivalent, result.output, result.witness) == (
            reference.equivalent, reference.output, reference.witness), backend
