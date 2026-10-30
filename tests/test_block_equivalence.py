"""Tests for circuit block decomposition and block-based equivalence verification."""
from __future__ import annotations

import random

import pytest

from symq import Budget, Circuit, ResourceLimitExceeded
from symq.backends import BACKENDS, has_native
from symq.equivalence import check_equivalence_by_blocks


def test_connected_components_splits_independent_wire_blocks():
    c = Circuit(6)
    c.cx(0, 1).mcx(0, 1, 2)
    c.cx(3, 4).mcx(3, 4, 5)

    components = c.connected_components()
    assert len(components) == 2
    qubits_0, sub_0 = components[0]
    qubits_1, sub_1 = components[1]

    assert qubits_0 == [0, 1, 2]
    assert sub_0.width == 3
    assert len(sub_0.gates) == 2

    assert qubits_1 == [3, 4, 5]
    assert sub_1.width == 3
    assert len(sub_1.gates) == 2


def test_connected_components_single_qubits_and_empty():
    c = Circuit(4)
    components = c.connected_components()
    assert len(components) == 4
    for i, (qubits, sub) in enumerate(components):
        assert qubits == [i]
        assert sub.width == 1
        assert len(sub.gates) == 0


def test_subcircuit_extraction_and_remapping():
    c = Circuit(5)
    c.x(1).cx(1, 3).mcx(1, 3, 4).cx(0, 2)

    sub = c.subcircuit([1, 3, 4])
    assert sub.width == 3
    assert len(sub.gates) == 3
    assert sub.gates[0].name == "x" and sub.gates[0].qubits == (0,)
    assert sub.gates[1].name == "cx" and sub.gates[1].qubits == (0, 1)
    assert sub.gates[2].name == "mcx" and sub.gates[2].qubits == (0, 1, 2)


@pytest.mark.skipif("zdd-native" not in BACKENDS, reason="zdd-native not built")
def test_check_equivalence_by_blocks_width_exceeding_native_limit():
    """Verify an 80-qubit circuit partitioned into two 40-qubit blocks using zdd-native."""
    left = Circuit(80)
    # Block 1 on wires 0..39
    left.x(0).cx(0, 10).mcx(0, 10, 39)
    # Block 2 on wires 40..79
    left.x(40).cx(40, 50).mcx(40, 50, 79)

    # Identical right circuit with reordered independent gates
    right = Circuit(80)
    right.x(40).cx(40, 50).mcx(40, 50, 79)
    right.x(0).cx(0, 10).mcx(0, 10, 39)

    res = check_equivalence_by_blocks(left, right, backend="zdd-native", max_block_width=64)
    assert res.equivalent is True
    assert res.stats.gates == 12
    assert res.stats.peak_terms is not None
    assert res.stats.seconds > 0


@pytest.mark.skipif("zdd-native" not in BACKENDS, reason="zdd-native not built")
def test_check_equivalence_by_blocks_detects_mutation_and_confirms_witness():
    """Blocked verification on >64 wires detects differences and yields a validated witness."""
    left = Circuit(80)
    left.x(0).cx(0, 10).mcx(0, 10, 39)
    left.x(40).cx(40, 50).mcx(40, 50, 79)

    mutant = Circuit(80)
    mutant.x(0).cx(0, 10).mcx(0, 10, 39)
    mutant.x(40).cx(40, 50).mcx(40, 50, 79).x(79)  # mutation on wire 79

    res = check_equivalence_by_blocks(left, mutant, backend="zdd-native", max_block_width=64)
    assert res.equivalent is False
    assert res.output == 79
    assert res.witness is not None
    # Re-check on the full 80-wire circuit
    assert left.run(res.witness) != mutant.run(res.witness)


@pytest.mark.skipif("zdd-native" not in BACKENDS, reason="zdd-native not built")
def test_width_limit_hint_message():
    from symq.backends.zdd_native import MAX_WIDTH, NativeZDDAlgebra

    with pytest.raises(ResourceLimitExceeded) as excinfo:
        NativeZDDAlgebra(MAX_WIDTH + 1)
    err = str(excinfo.value)
    assert "width limit exceeded" in err
    assert "uint64_t" in err or "64" in err
    assert "zdd" in err


def _random_circuit(rng, width, gates):
    circuit = Circuit(width)
    for _ in range(gates):
        qubits = rng.sample(range(width), rng.randint(1, min(3, width)))
        if len(qubits) == 1:
            circuit.x(qubits[0])
        else:
            circuit.mcx(*qubits)
    return circuit


def test_block_verdicts_match_exhaustive_oracle():
    rng = random.Random(20261027)
    for _ in range(300):
        width = rng.randint(2, 9)
        left = _random_circuit(rng, width, rng.randint(0, 6))
        right = Circuit(width, list(left.gates))
        draw = rng.random()
        if draw < 0.3:
            right = _random_circuit(rng, width, rng.randint(0, 6))
        elif draw < 0.7:
            right.cx(*rng.sample(range(width), 2))
        expected = left.equivalent(right)
        for max_block_width in (1, 2, 3, width):
            result = check_equivalence_by_blocks(
                left, right, backend="sparse", max_block_width=max_block_width
            )
            assert result.equivalent == expected
            if not expected:
                assert left.run(result.witness) != right.run(result.witness)
                assert (left.run(result.witness) ^ right.run(result.witness)) >> result.output & 1


def test_blocks_come_from_both_circuits():
    left = Circuit(3).cx(0, 1)
    right = Circuit(3).cx(0, 1).cx(1, 2)
    result = check_equivalence_by_blocks(left, right, backend="sparse", max_block_width=1)
    assert not result.equivalent
    assert result.output == 2
    assert result.backend == "zdd"


def test_fallback_is_explicit_and_reported():
    left = Circuit(4).cx(0, 1).ccx(0, 1, 2).x(3)
    right = Circuit(4).x(3).cx(0, 1).ccx(0, 1, 2)
    result = check_equivalence_by_blocks(left, right, backend="sparse", max_block_width=1)
    assert result.equivalent and result.backend == "sparse+zdd"
    with pytest.raises(ResourceLimitExceeded):
        check_equivalence_by_blocks(left, right, backend="sparse", max_block_width=1, fallback=None)
    with pytest.raises(ValueError):
        check_equivalence_by_blocks(left, right, max_block_width=0)


def test_default_backend_follows_the_native_core():
    left = Circuit(2).cx(0, 1)
    result = check_equivalence_by_blocks(left, Circuit(2, list(left.gates)))
    assert result.backend == ("zdd-native" if has_native() else "zdd")


def test_time_budget_covers_all_blocks():
    width = 400
    left = Circuit(width)
    for start in range(0, width, 4):
        left.mcx(start, start + 1, start + 2).cx(start + 2, start + 3)
    right = Circuit(width, list(left.gates))
    with pytest.raises(ResourceLimitExceeded):
        check_equivalence_by_blocks(
            left, right, backend="sparse", max_block_width=4, budget=Budget(max_seconds=1e-6)
        )


def test_subcircuit_rejects_crossing_gates_and_bad_wires():
    circuit = Circuit(4).cx(0, 1).cx(1, 2)
    with pytest.raises(ValueError, match="crosses"):
        circuit.subcircuit([0, 1])
    with pytest.raises(ValueError, match="out of range"):
        circuit.subcircuit([0, 7])
    assert circuit.wire_blocks() == [[0, 1, 2], [3]]
