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


@pytest.mark.parametrize("seed", range(12))
def test_check_equivalence_uses_collection_and_keeps_both_root_sets(seed):
    """Regression: two independent simulations can otherwise silently reuse stale IDs."""
    rng = random.Random(seed)
    left = random_circuit(4, rng.randint(6, 22), rng)
    equivalent = Circuit(left.width, [*left.gates])
    different = Circuit(left.width, [*left.gates]).x(0)
    for right, expected in ((equivalent, True), (different, False)):
        result = check_equivalence(
            left, right, backend="zdd-native",
            backend_options={"collect_every": 2},
        )
        assert result.equivalent is expected
        assert result.stats.gates == len(left.gates) + len(right.gates)
        assert result.stats.seconds > 0
        if not expected:
            assert result.witness is not None
            assert left.run(result.witness) != right.run(result.witness)


def test_simulate_pair_preserves_both_outputs_through_collection():
    left = Circuit(4).cx(0, 1).ccx(0, 1, 2).cx(2, 3).x(0).cx(0, 2)
    right = Circuit(4).x(3).cx(1, 2).ccx(0, 2, 3).cx(0, 1).x(1)
    algebra = NativeZDDAlgebra(4, collect_every=2)
    roots_left, roots_right = algebra.simulate_pair(left, right)
    assert algebra.collections > 0
    assert tuple(algebra.to_anf(root) for root in roots_left) == left.symbolic()
    assert tuple(algebra.to_anf(root) for root in roots_right) == right.symbolic()


def test_collection_rejects_reuse_with_published_node_ids():
    algebra = NativeZDDAlgebra(3, collect_every=2)
    left = Circuit(3).cx(0, 1).cx(1, 2).x(0)
    outputs = algebra.simulate(left)
    expected = tuple(algebra.to_anf(value) for value in outputs)
    with pytest.raises(RuntimeError, match="fresh, one-shot"):
        algebra.simulate(Circuit(3).x(1))
    assert tuple(algebra.to_anf(value) for value in outputs) == expected


def test_collection_requires_pristine_manager_without_external_handles():
    algebra = NativeZDDAlgebra(3, collect_every=1)
    algebra.variable(0)  # an exposed ID could be invalidated by a rebuild
    with pytest.raises(RuntimeError, match="fresh, one-shot"):
        algebra.simulate(Circuit(3).x(0))


def test_block_checker_passes_collection_options_to_native_blocks():
    from symq import check_equivalence_by_blocks

    left = Circuit(4).cx(0, 1).cx(2, 3)
    right = Circuit(4, [*left.gates])
    result = check_equivalence_by_blocks(
        left, right, backend="zdd-native", max_block_width=4,
        backend_options={"collect_every": 1},
    )
    assert result.equivalent


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
