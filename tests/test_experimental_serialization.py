"""Closed JSON round trips and malformed-document rejection."""
import json
from dataclasses import dataclass

import pytest

from symq.experimental.contracts import VerificationContract
from symq.experimental.domains import AffineDomain
from symq.experimental.hybrid import HybridProgram, freeze_hybrid
from symq.experimental.serialization import (
    load_contract,
    load_json,
    load_program,
    program_from_dict,
    program_to_dict,
    save_contract,
    save_program,
    save_result,
)
from symq.phase import PhaseProgram


def test_sign_hmr_roundtrip_preserves_event_identities_and_coherent_semantics(tmp_path):
    program = PhaseProgram(2, 1).cx(0, 2)
    event = program.hmr(2)
    program.mcz_if(event, 0, 1)
    path = tmp_path / "program.json"
    save_program(program, path)
    restored = load_program(path)
    assert restored == program
    assert program_to_dict(restored)["schema_version"] == 1
    assert restored.ops[-1].outcome == 0


def test_hybrid_roundtrip_preserves_reused_classical_slot_and_feedback(tmp_path):
    program = HybridProgram(2).measure_z(0, "b0").x(1, condition="b0")
    program.measure_z(1, "b0")
    path = tmp_path / "hybrid.json"
    save_program(program, path)
    assert load_program(path) == program
    assert program_to_dict(freeze_hybrid(program)) == program_to_dict(program)


def test_reduced_contract_roundtrip_preserves_affine_domain_and_output_order(tmp_path):
    contract = VerificationContract("reduced_channel", "zdd", AffineDomain(3, 1, (3, 6)),
                                    left_outputs=(2, 0), right_outputs=(1, 4))
    path = tmp_path / "contract.json"
    save_contract(contract, path)
    restored = load_contract(path)
    assert restored == contract
    assert restored.sha256 == contract.sha256
    document = json.loads(path.read_text())
    document["ignored"] = "not accepted"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="unknown"):
        load_contract(path)


def test_program_documents_reject_unknown_fields_unsupported_version_and_mutant_events():
    program = PhaseProgram(1)
    program.hmr(0)
    original = program_to_dict(program)
    for mutation in [dict(original, schema_version=2), dict(original, schema_version=True),
                     dict(original, kind="arbitrary_quantum"), dict(original, ignored=1)]:
        with pytest.raises(ValueError):
            program_from_dict(mutation)
    mutated = json.loads(json.dumps(original))
    mutated["ops"][0]["outcome"] = 1
    with pytest.raises(ValueError, match="expected 0|index 0"):
        program_from_dict(mutated)
    mutated = json.loads(json.dumps(original))
    mutated["ops"][0]["qubits"] = [True]
    with pytest.raises(ValueError):
        program_from_dict(mutated)


def test_json_loader_rejects_duplicate_keys_nonfinite_and_resource_overflow(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('{"x": 1, "x": 2}')
    with pytest.raises(ValueError, match="duplicate"):
        load_json(path)
    path.write_text('{"x": NaN}')
    with pytest.raises(ValueError, match="non-finite"):
        load_json(path)
    path.write_text("{}")
    with pytest.raises(ValueError, match="max_bytes"):
        load_json(path, max_bytes=1)


def test_result_document_is_a_record_and_carries_schema_version(tmp_path):
    @dataclass(frozen=True)
    class Record:
        outcome: str
        witness: tuple[int, int]

    path = tmp_path / "result.json"
    save_result(Record("different", (0, 1)), path)
    assert load_json(path) == {"schema_version": 1, "outcome": "different", "witness": [0, 1]}
