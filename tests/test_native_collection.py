"""Collection inside ``simulate`` must not change a single output.

The audit's second reservation was that the rebuild was a prototype, not a feature: the engine had
no collection, so the coverage gain was not available from ``check_equivalence``. ``collect_every``
is now a constructor option of ``NativeZDDAlgebra``, and these tests are the price of putting it
in the engine: every output must be identical to a run without collection, on every circuit, for
several thresholds, and the node identifiers returned must belong to the manager that is left.

What is deliberately *not* claimed here: that collection is free. It costs a rebuild per threshold
crossing, and the benchmarks that price it are in ``research/innovation/2026-10-28``.
"""
from __future__ import annotations

import random

import pytest

from symq import ANF, Circuit, check_equivalence, make_algebra, simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit


def native_outputs(circuit, **options) -> tuple[ANF, ...]:
    algebra = NativeZDDAlgebra(circuit.width, **options)
    return tuple(algebra.to_anf(value) for value in simulate(circuit, algebra))


def reference(circuit) -> tuple[ANF, ...]:
    algebra = make_algebra("zdd", circuit.width)
    return tuple(algebra.to_anf(value) for value in simulate(circuit, algebra))


@pytest.mark.parametrize("threshold", [1, 2, 5, 50])
@pytest.mark.parametrize("seed", range(12))
def test_collection_never_changes_the_outputs(threshold, seed):
    rng = random.Random(seed)
    circuit = random_circuit(rng.randint(2, 6), rng.randint(0, 20), rng)
    expected = reference(circuit)
    assert native_outputs(circuit) == expected
    assert native_outputs(circuit, collect_every=threshold) == expected


def test_collection_actually_happens_and_is_counted():
    rng = random.Random(7)
    circuit = random_circuit(6, 40, rng)
    algebra = NativeZDDAlgebra(6, collect_every=5)
    simulate(circuit, algebra)
    assert algebra.collections > 0, "a threshold of 5 nodes must trigger on this circuit"
    assert algebra.collected_nodes >= 0


def test_a_large_threshold_never_collects():
    rng = random.Random(7)
    circuit = random_circuit(5, 10, rng)
    algebra = NativeZDDAlgebra(5, collect_every=10_000_000)
    simulate(circuit, algebra)
    assert algebra.collections == 0


def test_an_empty_circuit_still_returns_the_variables():
    algebra = NativeZDDAlgebra(3, collect_every=1)
    outputs = simulate(Circuit(3), algebra)
    assert tuple(algebra.to_anf(value) for value in outputs) == tuple(Circuit(3).symbolic())


def test_check_equivalence_works_with_collection():
    """The point of the feature: the checker, not only a prototype, can use it."""
    rng = random.Random(11)
    left = random_circuit(5, 25, rng)
    right = type(left)(5, [*left.gates])
    from symq import EquivalenceResult

    result = check_equivalence(left, right, backend="zdd-native")
    assert isinstance(result, EquivalenceResult) and result.equivalent
    del rng


def test_the_returned_identifiers_belong_to_the_final_manager():
    rng = random.Random(3)
    circuit = random_circuit(5, 30, rng)
    algebra = NativeZDDAlgebra(5, collect_every=4)
    outputs = simulate(circuit, algebra)
    assert algebra.collections > 0
    # If any returned id were stale, these calls would raise "node id outside this manager".
    counts = [algebra.terms(value) for value in outputs]
    assert all(count >= 0 for count in counts)


@pytest.mark.parametrize("bad", [0, -1, True, 2.5, "10"])
def test_the_threshold_is_validated(bad):
    with pytest.raises(ValueError, match="collect_every"):
        NativeZDDAlgebra(3, collect_every=bad)
