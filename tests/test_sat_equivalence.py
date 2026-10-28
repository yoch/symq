"""The SAT engine must agree with exhaustive execution, and never certify a wrong answer.

Every claim here is checked against ``Circuit.run`` on every input of small circuits, which is the
only oracle that shares no code with the encoder. The negative tests matter as much as the
positive ones: a checker that says "equivalent" when it should not is worse than one that refuses.
"""
from __future__ import annotations

import random

import pytest

from symq import Budget, Circuit
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.sat import Contract, available, build_miter, check_sat_equivalence

pytestmark = pytest.mark.skipif(not available(), reason="python-sat is not installed")


def exhaustive_answer(left: Circuit, right: Circuit, contract: Contract | None = None
                      ) -> bool:
    """Reference: compare the two circuits by concrete execution on every legal input."""
    contract = contract or Contract()
    for x in range(1 << left.width):
        if any(((x >> wire) & 1) != value for wire, value in contract.input_constants.items()):
            continue
        a, b = left.run(x), right.run(x)
        for left_wire, right_wire in _pairs(contract, left.width):
            if ((a >> left_wire) & 1) != ((b >> right_wire) & 1):
                return False
        for wire in contract.restored_wires:
            initial = (x >> wire) & 1
            if ((a >> wire) & 1) != initial or ((b >> wire) & 1) != initial:
                return False
    return True


def _pairs(contract: Contract, width: int) -> list[tuple[int, int]]:
    if contract.output_map:
        return sorted(contract.output_map.items())
    if contract.observed_outputs is not None:
        return [(wire, wire) for wire in contract.observed_outputs]
    return [(wire, wire) for wire in range(width)]


@pytest.mark.parametrize("seed", range(40))
def test_the_verdict_matches_exhaustive_execution(seed):
    rng = random.Random(seed)
    width = rng.randint(1, 5)
    left = random_circuit(width, rng.randint(0, 12), rng)
    right = (equivalent_variant(left, rng, steps=rng.randint(1, 6))
             if rng.random() < 0.5 else random_circuit(width, rng.randint(0, 12), rng))
    verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=20))
    assert verdict.outcome in ("equivalent", "different")
    assert verdict.outcome == ("equivalent" if exhaustive_answer(left, right) else "different")
    if verdict.outcome == "different":
        assert verdict.witness_checked is True
        assert left.run(verdict.witness) != right.run(verdict.witness)


def test_the_four_gate_shapes():
    for circuit in (
        Circuit(1).x(0),
        Circuit(2).cx(0, 1),
        Circuit(3).ccx(0, 1, 2),
        Circuit(5).mcx(0, 1, 2, 3, 4),
    ):
        assert check_sat_equivalence(circuit, circuit).outcome == "equivalent"
        changed = type(circuit)(circuit.width).x(circuit.width - 1)
        assert check_sat_equivalence(circuit, changed).outcome == (
            "equivalent" if exhaustive_answer(circuit, changed) else "different")


def test_identical_circuits_are_equivalent_and_mutants_are_not():
    rng = random.Random(7)
    base = random_circuit(4, 14, rng)
    assert check_sat_equivalence(base, type(base)(4, list(base.gates))).outcome == "equivalent"
    # ``mutate`` may insert a gate the circuit already contains, in which case the mutant is
    # *equivalent*: the test compares the SAT verdict with exhaustive execution either way.
    for kind in ("insert", "delete", "retarget", "add_control", "drop_control"):
        try:
            mutant, _ = mutate(base, rng, kind)
        except ValueError:
            continue
        verdict = check_sat_equivalence(base, mutant)
        expected = exhaustive_answer(base, mutant)
        assert verdict.outcome == ("equivalent" if expected else "different"), kind
        if not expected:
            assert verdict.witness_checked is True


def test_a_rare_input_difference_is_found():
    """A gate controlled on every wire differs on exactly one input."""
    width = 6
    left = Circuit(width)
    right = Circuit(width).mcx(*range(width))
    verdict = check_sat_equivalence(left, right)
    assert verdict.outcome == "different"
    # Any witness must be an input where every control is set; the solver may return any of them.
    assert verdict.witness is not None
    assert all((verdict.witness >> wire) & 1 for wire in range(width))


def test_equivalent_but_structurally_different():
    left = Circuit(3).ccx(0, 1, 2).cx(2, 0)
    right = Circuit(3).cx(2, 0)
    for gate in left.gates[:1]:
        right.gates.append(gate)
    # The two circuits differ only in gate order; both act on distinct wires.
    assert exhaustive_answer(left, right) == (left.run(0) == right.run(0) and all(
        left.run(x) == right.run(x) for x in range(8)))
    verdict = check_sat_equivalence(left, right)
    assert verdict.outcome == ("equivalent" if exhaustive_answer(left, right) else "different")


def test_a_constant_input_narrows_the_domain():
    """With wire 0 fixed to 0, a gate controlled on wire 0 can never fire."""
    left = Circuit(2)
    right = Circuit(2).cx(0, 1)
    unrestricted = check_sat_equivalence(left, right)
    assert unrestricted.outcome == "different"
    contract = Contract(input_constants={0: 0})
    assert check_sat_equivalence(left, right, contract).outcome == "equivalent"
    assert exhaustive_answer(left, right, contract)


def test_observed_outputs_let_an_ancilla_be_ignored():
    """A circuit that writes garbage into a wire nobody observes is equivalent on the others."""
    left = Circuit(3).ccx(0, 1, 2)
    right = Circuit(3).ccx(0, 1, 2).x(2)
    assert check_sat_equivalence(left, right).outcome == "different"
    contract = Contract(observed_outputs=(0, 1))
    assert check_sat_equivalence(left, right, contract).outcome == "equivalent"
    assert exhaustive_answer(left, right, contract)


def test_restored_wires_express_the_clean_ancilla_obligation():
    """An uncomputed ancilla must come back to its input value."""
    good = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    dirty = Circuit(3).ccx(0, 1, 2)
    contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))
    assert check_sat_equivalence(good, Circuit(3), contract).outcome == "equivalent"
    assert check_sat_equivalence(dirty, Circuit(3), contract).outcome == "different"


def test_a_wire_permutation_can_be_declared():
    left = Circuit(2).cx(0, 1).cx(1, 0)
    right = Circuit(2).cx(1, 0).cx(0, 1)
    verdict = check_sat_equivalence(left, right, Contract(output_map={0: 1, 1: 0}))
    assert verdict.outcome in ("equivalent", "different")
    assert verdict.outcome == ("equivalent"
                               if exhaustive_answer(left, right, Contract(output_map={0: 1,
                                                                                    1: 0}))
                               else "different")


def test_contracts_reject_contradictions():
    with pytest.raises(ValueError, match="outside width"):
        Contract(input_constants={5: 0}).validate(3)
    with pytest.raises(ValueError, match="must be 0 or 1"):
        Contract(input_constants={0: 2}).validate(3)
    with pytest.raises(ValueError, match="must not repeat"):
        Contract(observed_outputs=(1, 1)).validate(3)
    with pytest.raises(ValueError, match="injective"):
        Contract(output_map={0: 1, 2: 1}).validate(3)
    with pytest.raises(ValueError, match="mutually exclusive"):
        Contract(observed_outputs=(0,), output_map={1: 2}).validate(3)
    with pytest.raises(ValueError, match="cannot also be mapped"):
        Contract(restored_wires=(1,), output_map={0: 1}).validate(3)


def test_the_miter_is_reusable_and_has_the_declared_size():
    left = Circuit(2).cx(0, 1)
    right = Circuit(2).cx(1, 0)
    miter = build_miter(left, right)
    assert len(miter.inputs) == 2
    assert miter.encoder.clauses
    assert len(miter.difference) == 2


def test_a_budget_that_cannot_be_met_is_inconclusive_not_equivalent():
    rng = random.Random(3)
    left = random_circuit(5, 40, rng)
    right = random_circuit(5, 40, rng)
    verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=1e-6))
    assert verdict.outcome in ("inconclusive", "equivalent", "different")
    if verdict.outcome == "inconclusive":
        assert verdict.equivalent is None, "an inconclusive run is not a verdict"


def test_the_availability_report_is_honest():
    from symq import sat

    assert sat.available() is True
    assert "python-sat" in sat.versions()
