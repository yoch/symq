"""The affine bit-mask backend: exact on X/CX circuits of any width, refusing degree two."""
from __future__ import annotations

import random

import pytest

from symq import Budget, Circuit, ResourceLimitExceeded, check_equivalence, make_algebra, simulate


def linear_circuit(width: int, gates: int, rng: random.Random) -> Circuit:
    circuit = Circuit(width)
    for _ in range(gates):
        if rng.random() < 0.2:
            circuit.x(rng.randrange(width))
        else:
            a, b = rng.sample(range(width), 2)
            circuit.cx(a, b)
    return circuit


@pytest.mark.parametrize("seed", range(10))
def test_linear_backend_agrees_with_the_reference_on_small_circuits(seed):
    rng = random.Random(seed)
    circuit = linear_circuit(rng.randint(2, 9), rng.randint(0, 60), rng)
    linear = make_algebra("linear", circuit.width)
    assert [linear.to_anf(v) for v in simulate(circuit, linear)] == list(circuit.symbolic())


def test_wide_linear_stages_are_checked_with_replayed_witnesses():
    rng = random.Random(1)
    circuit = linear_circuit(840, 50_000, rng)
    # The inverse undoes it exactly; a single retargeted CX breaks it.
    identity = Circuit(840, [*circuit.gates, *circuit.inverse().gates])
    assert check_equivalence(identity, Circuit(840), backend="linear",
                             budget=Budget(max_seconds=60)).equivalent
    broken = Circuit(840, [*circuit.gates[:-1], *circuit.inverse().gates])
    result = check_equivalence(identity, broken, backend="linear")
    assert not result.equivalent
    assert identity.run(result.witness) != broken.run(result.witness)


def test_nonlinear_gates_are_refused_not_approximated():
    with pytest.raises(ResourceLimitExceeded) as info:
        simulate(Circuit(3).ccx(0, 1, 2), make_algebra("linear", 3))
    assert info.value.resource == "degree"
    # A Toffoli whose controls are equal or complementary stays affine and is exact.
    algebra = make_algebra("linear", 3)
    x0 = algebra.variable(0)
    assert algebra.product([x0, x0]) == x0
    assert algebra.product([x0, algebra.xor(x0, algebra.one())]) == 0
