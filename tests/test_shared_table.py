"""Shared encodings, wide affine/HMR theorems and separate actual preparation."""
from __future__ import annotations

import copy

import pytest
from testkit.kraus_oracle import independent_kraus

from symq import Circuit
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.experimental.table_xor import PredicateValues, TableXorContract
from symq.labs.affine_table import affine_target_from_equations
from symq.labs.classical_transcript import Program, digest
from symq.labs.shared_table import SharedTable, prove_shared_table_preparation, verify_shared_table
from symq.resources import Budget, Guard


def wide_case():
    source = HybridProgram(42, 1)
    source.cx(8, 9).reset(9).cx(8, 9)  # identity exactly under sign-copy relation
    for j in range(5):
        source.cx(0, 2 + 8 * j)
    source.ccx(0, 1, 42)
    for j in range(5):
        source.cx(42, 2 + 8 * j + 6).cx(42, 2 + 8 * j + 7)
    source.hmr(42, "b0").cz(0, 1, condition="b0")
    rows = [sum((((a & 1) | (192 if a == 3 else 0)) << (8 * j)) for j in range(5))
            for a in range(4)]
    table = SharedTable.from_rows(rows, address_bits=2, target_bits=40)
    space = affine_target_from_equations(40, [[192 << (8 * j), 0] for j in range(5)])
    contract = {"kind": "symq_shared_affine_table_contract", "schema_version": 3,
                "width": 43, "address_wires": [0, 1], "target_wires": list(range(2, 42)),
                "clean_wires": [42], "borrowed_wires": [], "table": table.to_dict(),
                "address_domain": PredicateValues.below(2, 4).to_dict(), "target_space": space,
                "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}
    return source, contract


def test_shared_encoding_roundtrip_and_strict_column_mapping():
    rows = [0, 0b1111, 0b0101, 0b1010]
    table = SharedTable.from_rows(rows, address_bits=2, target_bits=4)
    assert len(table.columns) == 2
    assert table.rows(Guard()) == rows
    assert SharedTable.from_dict(table.to_dict()) == table
    for mutate in (
        lambda d: d.update(verified=True), lambda d: d.update(address_bits=True),
        lambda d: d["columns_hex"].append(d["columns_hex"][0]),
        lambda d: d["target_columns"].__setitem__(0, True),
        lambda d: d["columns_hex"].__setitem__(0, "A"),
        lambda d: d["target_columns"].__setitem__(0, 20),
    ):
        doc = table.to_dict()
        mutate(doc)
        with pytest.raises(ValueError):
            SharedTable.from_dict(doc)


@pytest.mark.parametrize("backend", ["anf", pytest.param("sat", marks=pytest.mark.sat)])
def test_wide_hmr_loader_retains_35_independent_targets_and_phase(backend):
    source, contract = wide_case()
    result = verify_shared_table(program_to_dict(source), contract, backend=backend)
    assert result["status"] == "equivalent"
    assert result["address_domain_size"] == 4
    assert result["target_dimension"] == 35
    assert result["target_bits"] == 40 and result["shared_columns"] == 3
    assert result["actual_context_preparation_proved"] is False
    missing = program_to_dict(source)
    missing["ops"].pop()
    assert verify_shared_table(missing, contract, backend=backend)["status"] == "not_proved"
    wide = copy.deepcopy(contract)
    wide["target_space"] = {"kind": "affine_image", "offset": 0,
                             "columns": [1 << i for i in range(40)]}
    rejected = verify_shared_table(program_to_dict(source), wide, backend=backend)
    assert rejected["status"] == "not_proved"
    assert rejected["obligation"] == "irreversible_record"


def test_predicate_domain_is_exact_and_cannot_be_silently_widened():
    source = HybridProgram(3, 0).ccx(0, 1, 2)
    contract = {"kind": "symq_shared_affine_table_contract", "schema_version": 3,
                "width": 3, "address_wires": [0, 1], "target_wires": [2],
                "clean_wires": [], "borrowed_wires": [],
                "table": SharedTable.from_rows([0] * 4, address_bits=2, target_bits=1).to_dict(),
                "address_domain": PredicateValues.below(2, 3).to_dict(),
                "target_space": {"kind": "affine_image", "offset": 0, "columns": [1]},
                "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}
    small = verify_shared_table(program_to_dict(source), contract)
    assert small["status"] == "equivalent" and small["address_domain_size"] == 3
    contract["address_domain"] = PredicateValues.below(2, 4).to_dict()
    assert verify_shared_table(program_to_dict(source), contract)["status"] == "not_proved"
    # Small independent channel oracle, including off-diagonal input pairs.
    reference = HybridProgram(3, 0)
    legal = [v for v in range(8) if v & 3 < 3]
    for x in legal:
        for y in legal:
            assert independent_kraus(source, x, y) == independent_kraus(reference, x, y)


@pytest.mark.sat
def test_actual_preparation_is_a_separate_exact_prefix_theorem():
    source, contract = wide_case()
    contract["address_domain"] = PredicateValues.below(2, 3).to_dict()
    prefix = Circuit(43)
    for j in range(5):
        prefix.cx(2 + 8 * j + 6, 2 + 8 * j + 7)
    initial = ((1, 0), (42, 0)) + tuple((2 + 8 * j + 7, 0) for j in range(5))
    pin = digest(Program.freeze(prefix))
    proof = prove_shared_table_preparation(prefix, contract, expected_source_sha256=pin,
                                            initial_constants=initial)
    assert proof["status"] == "equivalent"
    assert proof["external_initial_preparation_proved"] is False
    assert proof["complete_source_connection"] == "not_inferred_from_a_prefix_only"
    unprepared = prove_shared_table_preparation(prefix, contract, expected_source_sha256=pin,
                                                 initial_constants=initial[:-1])
    assert unprepared["status"] == "precondition_failed"
    # Loader is still conditionally correct; it cannot certify its caller.
    assert verify_shared_table(program_to_dict(source), contract)["status"] == "equivalent"
    with pytest.raises(ValueError, match="pinned"):
        prove_shared_table_preparation(Circuit(43), contract, expected_source_sha256=pin,
                                       initial_constants=initial)


def test_nonempty_predicate_witness_is_checked_and_empty_domain_refused():
    source, contract = wide_case()
    contract["address_domain"]["domain"]["predicate"] = {"kind": "const", "value": False}
    with pytest.raises(ValueError):
        verify_shared_table(program_to_dict(source), contract)


def test_width_limits_legacy_contract_and_budget_are_explicit():
    # The maintained API keeps its 16-bit target boundary.
    with pytest.raises(ValueError):
        TableXorContract(43, (0, 1), tuple(range(2, 42)), (42,), (),
                         (0, 0, 0, 0), (0, 1, 2, 3), None, "table", "slot", "classical")
    source, contract = wide_case()
    assert verify_shared_table(program_to_dict(source), contract,
                               budget=Budget(absolute_deadline=0))["status"] == "inconclusive"
    assert prove_shared_table_preparation(Circuit(43), contract,
                                          expected_source_sha256="0" * 64,
                                          budget=Budget(absolute_deadline=0))["status"] == "inconclusive"
    contract["extra"] = True
    with pytest.raises(ValueError, match="closed"):
        verify_shared_table(program_to_dict(source), contract)
