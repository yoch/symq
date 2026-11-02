"""Independent and adversarial qualification for the finite-table XOR adapter."""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from symq.circuit import Circuit, Gate
from symq.errors import UnsupportedOperation
from symq.labs.table_xor_contract import (
    ReceiptMismatch, TableXorContract, check_table_xor, replay_table_xor,
)
from symq.resources import Budget
from symq.sat import available


def spec(**changes):
    original = dict(
        width=6, address_wires=(0, 1), target_wires=(2, 3),
        clean_wires=(4,), borrowed_wires=(5,), table=(0, 1, 3, 2),
        legal_addresses=(0, 1, 2), target_values=None,
        table_id="synthetic-t0", slot_id="emission-s1", theorem="coherent",
    )
    original.update(changes)
    return TableXorContract(**original)


def linear():
    """Independent minimum linear realization of T=(0,1,3,2)."""
    return Circuit(6).cx(0, 2).cx(1, 2).cx(1, 3)


def selector():
    """An independently written row-minterm realization, unlike the linear one."""
    out = Circuit(6)
    out.x(1).ccx(0, 1, 2).x(1)  # a=01
    out.x(0).ccx(0, 1, 2).ccx(0, 1, 3).x(0)  # a=10
    out.ccx(0, 1, 3)  # a=11; declared illegal but still correct
    return out


def pack(address, target, borrowed=0, scratch=0):
    return ((address & 1) | ((address >> 1 & 1) << 1)
            | ((target & 1) << 2) | ((target >> 1 & 1) << 3)
            | (scratch << 4) | (borrowed << 5))


def direct_oracle(initial, table):
    """Independent scalar spec, with no imports from the adapter."""
    address = (initial & 1) | (((initial >> 1) & 1) << 1)
    target = ((initial >> 2) & 1) | (((initial >> 3) & 1) << 1)
    after = target ^ table[address]
    return ((initial & ~(4 | 8)) | ((after & 1) << 2) | ((after >> 1 & 1) << 3))


def basis_states(values=(0, 1, 2, 3)):
    return [pack(a, z, d) for a in (0, 1, 2) for z in values for d in (0, 1)]


def independently_apply_gates(source, initial):
    """Separate gate-table interpreter (no Circuit.run or adapter helpers)."""
    state = initial
    for gate in source.gates:
        active = 1
        for wire in gate.qubits[:-1]:
            active &= (state >> wire) & 1
        if active:
            state ^= 1 << gate.qubits[-1]
    return state


def test_two_different_emissions_and_all_coherences():
    contract = spec()
    inputs = basis_states()
    images = [direct_oracle(x, contract.table) for x in inputs]
    for source in (linear(), selector()):
        proof = check_table_xor(source, contract, backend="exhaustive")
        assert proof.equivalent and proof.checked_states == 24
        assert proof.theorem == "coherent"
        assert all(independently_apply_gates(source, x) == y
                   for x, y in zip(inputs, images))
        # Every |x><y| maps to |T(x)><T(y)|, including x!=y:
        # a direct exact matrix-unit oracle for this permutation-only grammar.
        for i, x in enumerate(inputs):
            for j, y in enumerate(inputs):
                output = (independently_apply_gates(source, x),
                          independently_apply_gates(source, y))
                assert output == (images[i], images[j])


def test_classical_intent_does_not_invent_a_channel_label():
    result = check_table_xor(linear(), spec(theorem="classical"), backend="exhaustive")
    assert result.equivalent and result.theorem == "classical"


def test_restricted_target_is_not_an_arbitrary_dirty_target():
    candidate = linear()
    # Temporarily compute z0 XOR z1 onto a clean bit, corrupt a borrowed
    # arbitrary bit on mismatched targets, and exactly uncompute scratch.
    candidate.cx(2, 4).cx(3, 4).cx(4, 5).cx(3, 4).cx(2, 4)
    restricted = check_table_xor(
        candidate, spec(target_values=(0, 3)), backend="exhaustive")
    assert restricted.equivalent and restricted.checked_states == 12
    widened = check_table_xor(candidate, spec(target_values=None), backend="exhaustive")
    assert widened.status == "different"
    assert widened.witness in basis_states()
    assert direct_oracle(widened.witness, spec().table) != candidate.run(widened.witness)


def test_clean_scratch_is_not_a_borrowed_dirty_wire():
    dependent = linear().cx(4, 2)
    permitted = check_table_xor(dependent, spec(), backend="exhaustive")
    assert permitted.equivalent
    not_clean = spec(clean_wires=(), borrowed_wires=(4, 5))
    fail = check_table_xor(dependent, not_clean, backend="exhaustive")
    assert fail.status == "different"
    assert fail.witness is not None and fail.witness & (1 << 4)


@pytest.mark.parametrize("mutant", [
    lambda p: p.x(2),  # changed table bit / extra target update
    lambda p: p.cx(0, 5),  # borrowed dirty workspace not restored
    lambda p: p.x(4),  # clean scratch not restored
    lambda p: p.cx(0, 3),  # wrong target bit
])
def test_bad_emissions_are_rejected(mutant):
    candidate = mutant(linear())
    result = check_table_xor(candidate, spec(), backend="exhaustive")
    assert result.status == "different"
    assert result.witness is not None
    assert candidate.run(result.witness) != direct_oracle(result.witness, spec().table)


def test_input_bit_order_and_legal_set_are_bound():
    source = linear()
    assert check_table_xor(source, spec(), backend="exhaustive").equivalent
    bad_order = spec(target_wires=(3, 2))
    assert check_table_xor(source, bad_order, backend="exhaustive").status == "different"
    bad_table = spec(table=(0, 1, 2, 3))
    assert check_table_xor(source, bad_table, backend="exhaustive").status == "different"
    changed_legal = spec(legal_addresses=(0, 1, 2, 3))
    # This source implements the entire table, so widening to address 3 stays
    # valid; the changed contract identity nevertheless invalidates old replay.
    assert check_table_xor(source, changed_legal, backend="exhaustive").equivalent


def test_receipt_replay_requires_independent_pins_and_fresh_check():
    contract = spec()
    source = linear()
    record = check_table_xor(source, contract, backend="exhaustive").to_dict()
    assert replay_table_xor(
        source, contract, record,
        expected_source_sha256=record["source_sha256"],
        expected_contract_sha256=record["contract_sha256"],
        backend="exhaustive").equivalent

    for modified_contract in (
        replace(contract, table_id="synthetic-t1"),
        replace(contract, slot_id="emission-s2"),
        replace(contract, table=(0, 1, 2, 2)),
        replace(contract, target_values=(0, 3)),
        replace(contract, legal_addresses=(0, 1, 2, 3)),
        replace(contract, target_wires=(3, 2)),
        replace(contract, theorem="classical"),
    ):
        with pytest.raises(ReceiptMismatch, match="changed"):
            replay_table_xor(
                source, modified_contract, record,
                expected_source_sha256=record["source_sha256"],
                expected_contract_sha256=record["contract_sha256"],
                backend="exhaustive")

    with pytest.raises(ReceiptMismatch):
        replay_table_xor(source.x(2), contract, record,
                         expected_source_sha256=record["source_sha256"],
                         expected_contract_sha256=record["contract_sha256"],
                         backend="exhaustive")

    forged = copy.deepcopy(record)
    forged["source_sha256"] = "0" * 64
    with pytest.raises(ReceiptMismatch):
        replay_table_xor(linear(), contract, forged,
                         expected_source_sha256=record["source_sha256"],
                         expected_contract_sha256=record["contract_sha256"],
                         backend="exhaustive")

    forged = check_table_xor(linear().x(2), contract, backend="exhaustive").to_dict()
    forged.update(status="equivalent", witness=None)
    with pytest.raises(ReceiptMismatch, match="fresh proof"):
        replay_table_xor(linear().x(2), contract, forged,
                         expected_source_sha256=forged["source_sha256"],
                         expected_contract_sha256=forged["contract_sha256"],
                         backend="exhaustive")

    with pytest.raises(ValueError, match="pin"):
        replay_table_xor(source, contract, record,
                         expected_source_sha256="bogus",
                         expected_contract_sha256=record["contract_sha256"],
                         backend="exhaustive")


def test_mutated_and_forged_gate_is_rejected_before_analysis():
    c = linear()
    c.gates[0] = object()
    with pytest.raises(TypeError):
        check_table_xor(c, spec(), backend="exhaustive")
    fake = object.__new__(Gate)
    object.__setattr__(fake, "name", "cx")
    object.__setattr__(fake, "qubits", (0, True))
    c = linear()
    c.gates[0] = fake
    with pytest.raises(TypeError):
        check_table_xor(c, spec(), backend="exhaustive")


def test_bad_contracts_and_strict_json():
    original = spec()
    assert TableXorContract.from_dict(original.to_dict()) == original
    with pytest.raises(ValueError, match="nonempty"):
        spec(legal_addresses=())
    with pytest.raises(ValueError, match="table"):
        spec(table=(0, 1, 3))
    with pytest.raises(ValueError, match="table rows"):
        spec(table=(0, 1, 3, 4))
    with pytest.raises(ValueError, match="partition"):
        spec(address_wires=(0, 2))
    with pytest.raises(ValueError, match="exact"):
        spec(table=(0, True, 3, 2))
    with pytest.raises(ValueError, match="target_values"):
        spec(target_values=(0, 0))
    with pytest.raises(ValueError, match="theorem"):
        spec(theorem="channel")
    with pytest.raises(ValueError, match="ordering"):
        spec(bit_order="msb_first")
    with pytest.raises(ValueError, match="distinct"):
        spec(table_id="emission-s1")
    broken = original.to_dict()
    broken["unknown"] = True
    with pytest.raises(ValueError, match="unknown"):
        TableXorContract.from_dict(broken)
    broken = original.to_dict()
    broken["target_domain"] = {"kind": "values", "values": [0, True]}
    with pytest.raises(ValueError, match="target_values"):
        TableXorContract.from_dict(broken)
    broken = original.to_dict()
    broken["schema_version"] = True
    with pytest.raises(ValueError, match="version"):
        TableXorContract.from_dict(broken)
    with pytest.raises(UnsupportedOperation):
        linear().append("hmr", 4)


def test_strict_resource_limits_fail_closed():
    contract = spec()
    source = linear()
    assert check_table_xor(source, contract, backend="exhaustive",
                           max_states=10).status == "inconclusive"
    assert check_table_xor(source, contract, backend="exhaustive",
                           budget=Budget(max_terms=10)).status == "inconclusive"
    assert check_table_xor(source, contract, backend="exhaustive",
                           budget=Budget(max_seconds=1e-12)).status == "inconclusive"
    with pytest.raises(ValueError, match="not supported"):
        check_table_xor(source, contract, budget=Budget(max_nodes=1))


@pytest.mark.sat
def test_sat_exact_contract_and_replayed_counterexample():
    assert available()
    contract = spec()
    for candidate in (linear(), selector()):
        success = check_table_xor(candidate, contract, backend="sat",
                                  budget=Budget(max_seconds=10))
        assert success.equivalent and success.sat_clauses > 0
        replay = replay_table_xor(
            candidate, contract, success.to_dict(),
            expected_source_sha256=success.source_sha256,
            expected_contract_sha256=success.contract_sha256,
            backend="sat", budget=Budget(max_seconds=10))
        assert replay.equivalent
    for candidate in (linear().x(2), linear().cx(0, 5)):
        difference = check_table_xor(candidate, contract, backend="sat",
                                     budget=Budget(max_seconds=10))
        assert difference.status == "different"
        assert difference.witness in basis_states()
        assert candidate.run(difference.witness) != direct_oracle(
            difference.witness, contract.table)


@pytest.mark.sat
def test_sat_restricted_target_and_reference_gate_cap():
    assert available()
    source = linear().cx(2, 4).cx(3, 4).cx(4, 5).cx(3, 4).cx(2, 4)
    assert check_table_xor(source, spec(target_values=(0, 3)), backend="sat").equivalent
    assert check_table_xor(source, spec(), backend="sat").status == "different"
    assert check_table_xor(linear(), spec(), backend="sat",
                           budget=Budget(max_terms=1)).status == "inconclusive"
