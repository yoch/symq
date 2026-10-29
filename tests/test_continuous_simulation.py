"""The fragmented simulation must equal the monolithic one, monomial for monomial.

This is the test that the first version of pilot C lacked: it called ``algebra.simulate`` on each
fragment, which restarts from the identity state, so the "chunks" were independent simulations
rather than one continuous run. Nothing in the old pilot could have caught it, because it never
compared against a reference.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import continuous

from symq import make_algebra, simulate
from symq.anf import ANF
from symq.generators import random_circuit


def reference(circuit) -> tuple[ANF, ...]:
    """An independent backend, so a native bug cannot hide behind itself."""
    algebra = make_algebra("zdd", circuit.width)
    return tuple(algebra.to_anf(value) for value in simulate(circuit, algebra))


def native_outputs(circuit) -> tuple[ANF, ...]:
    algebra = make_algebra("zdd-native", circuit.width)
    return tuple(algebra.to_anf(value) for value in simulate(circuit, algebra))


@pytest.mark.parametrize("seed", range(30))
def test_chunked_simulation_matches_the_monolithic_run(seed):
    rng = random.Random(seed)
    circuit = random_circuit(rng.randint(2, 6), rng.randint(0, 25), rng)
    expected = reference(circuit)
    assert native_outputs(circuit) == expected, "the monolithic native run must match too"
    for count in (1, 2, 3, 5, 8):
        algebra = make_algebra("zdd-native", circuit.width)
        state = continuous.simulate_in_chunks(algebra, circuit, count)
        assert tuple(algebra.to_anf(value) for value in state) == expected, (seed, count)


@pytest.mark.parametrize("seed", range(10))
def test_a_split_at_every_gate_is_still_the_same_function(seed):
    rng = random.Random(1000 + seed)
    circuit = random_circuit(4, rng.randint(1, 12), rng)
    expected = reference(circuit)
    gates = circuit.gates
    for split in range(len(gates) + 1):
        from symq import Circuit

        algebra = make_algebra("zdd-native", 4)
        state = continuous.initial_state(algebra)
        state = continuous.apply_fragment(algebra, state, Circuit(4, gates[:split]))
        state = continuous.apply_fragment(algebra, state, Circuit(4, gates[split:]))
        assert tuple(algebra.to_anf(value) for value in state) == expected, split


def test_an_empty_fragment_is_the_identity_on_the_state():
    from symq import Circuit

    algebra = make_algebra("zdd-native", 3)
    circuit = Circuit(3).cx(0, 1).x(1)
    state = continuous.initial_state(algebra)
    after = continuous.apply_fragment(algebra, state, circuit)
    again = continuous.apply_fragment(algebra, after, Circuit(3))
    assert again == after


def test_state_length_and_width_are_checked():
    from symq import Circuit

    algebra = make_algebra("zdd-native", 3)
    with pytest.raises(ValueError, match="one node id per wire"):
        continuous.apply_fragment(algebra, (1, 1), Circuit(3).x(0))
    with pytest.raises(ValueError, match="width differ"):
        continuous.apply_fragment(algebra, (1, 1, 1), Circuit(4).x(0))


def test_the_between_hook_can_replace_the_state():
    from symq import Circuit

    calls = []

    def hook(state):
        calls.append(len(state))

    algebra = make_algebra("zdd-native", 3)
    state = continuous.simulate_in_chunks(algebra, Circuit(3).cx(0, 1).cx(1, 2), 3,
                                          between=hook)
    # Two gates cannot be split into three non-empty fragments; the hook runs once per fragment.
    assert calls == [3, 3]
    assert len(state) == 3


def test_chunks_cover_the_circuit_in_order():
    rng = random.Random(7)
    circuit = random_circuit(3, 10, rng)
    parts = continuous.chunks(circuit, 3)
    flat = [gate for part in parts for gate in part.gates]
    assert flat == list(circuit.gates)
    assert len(parts) == 3
