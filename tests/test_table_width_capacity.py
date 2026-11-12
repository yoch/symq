"""Address widths beyond what the table verifiers support are refused, not crashed on.

A downstream report on 0.2.0 found that ``verify_shared_table`` accepted and documented
16 address bits while the verifier behind it refused anything above 12 with a bare
``ValueError('table width cap')``. Until the verifier supports wider tables, a well-formed
wider table must come back ``unsupported`` (no verdict, no exception) with a reason that
names both widths. The fixture is the report's minimal one: an identity program, a
constant-zero table, every address legal.
"""
from __future__ import annotations

import pytest

from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.experimental.table_xor import PredicateValues
from symq.labs.anchored_kraus import MAX_ADDRESS_BITS, verify
from symq.labs.anchored_stream import verify_stream
from symq.labs.shared_table import SharedTable, verify_shared_table
from symq.resources import Budget, Guard, ResourceLimitExceeded

BACKENDS = ["anf", pytest.param("sat", marks=pytest.mark.sat)]


def _identity(address_bits: int) -> dict:
    return program_to_dict(HybridProgram(address_bits + 1, 0))


def _shared_contract(address_bits: int) -> dict:
    table = SharedTable.from_rows([0] * (1 << address_bits), address_bits=address_bits,
                                  target_bits=1)
    return {"kind": "symq_shared_affine_table_contract", "schema_version": 3,
            "width": address_bits + 1, "address_wires": list(range(address_bits)),
            "target_wires": [address_bits], "clean_wires": [], "borrowed_wires": [],
            "table": table.to_dict(),
            "address_domain": PredicateValues.below(address_bits, 1 << address_bits).to_dict(),
            "target_space": {"kind": "affine_image", "offset": 0, "columns": [1]},
            "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}


def _v1_contract(address_bits: int, target_bits: int = 1) -> dict:
    width = address_bits + target_bits
    return {"kind": "symq_hmr_table_contract", "schema_version": 1, "width": width,
            "address_wires": list(range(address_bits)),
            "target_wires": list(range(address_bits, width)), "clean_wires": [],
            "borrowed_wires": [], "table": [0] * (1 << address_bits),
            "legal_addresses": list(range(1 << address_bits)), "target_values": None,
            "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}


def test_the_documented_limit_is_the_enforced_one():
    assert MAX_ADDRESS_BITS == 12


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_table_at_the_limit_is_still_proved(backend):
    result = verify_shared_table(_identity(12), _shared_contract(12), backend=backend)
    assert result["status"] == "equivalent", result


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("address_bits", [13, 16])
def test_a_wider_shared_table_is_unsupported_not_an_error(backend, address_bits):
    result = verify_shared_table(_identity(address_bits), _shared_contract(address_bits),
                                 backend=backend)
    assert result["status"] == "unsupported"
    assert result["obligation"] == "capacity"
    assert result["witness"] is None
    assert result["reason"] == (f"address width {address_bits} exceeds this verifier's "
                                f"limit of {MAX_ADDRESS_BITS}")
    assert result["actual_context_preparation_proved"] is False


def test_the_version_1_verifiers_refuse_the_same_way():
    source, contract = program_to_dict(HybridProgram(14, 0)), _v1_contract(13)
    for result in (verify(source, contract), verify_stream(source, contract)):
        assert result["status"] == "unsupported"
        assert result["obligation"] == "capacity"
        assert "address width 13" in result["reason"]


def test_too_many_targets_is_unsupported_too():
    """The reference verifier keeps its 16-target limit; 17 targets is a capacity refusal."""
    source, contract = program_to_dict(HybridProgram(18, 0)), _v1_contract(1, 17)
    result = verify(source, contract)
    assert result["status"] == "unsupported"
    assert result["reason"] == "target width 17 exceeds this verifier's limit of 16"


def test_a_malformed_contract_still_raises():
    """Only well-formed inputs beyond a size limit are ``unsupported``."""
    contract = _v1_contract(2)
    contract["table"] = [0]
    with pytest.raises(ValueError, match="complete table shape"):
        verify(program_to_dict(HybridProgram(3, 0)), contract)


def test_an_expired_deadline_reports_a_zero_limit_and_says_why():
    """A deadline already past when the work starts was reported as a negative limit."""
    with pytest.raises(ResourceLimitExceeded) as caught:
        Guard(Budget(absolute_deadline=0)).check_time()
    error = caught.value
    assert error.resource == "seconds" and error.limit == 0.0 and error.observed >= 0
    assert error.hint == "the deadline had already passed when this computation started"
    assert "limit -" not in str(error)


def test_a_running_deadline_keeps_its_duration_and_no_hint(monkeypatch):
    from symq import resources

    clock = iter([100.0, 100.5])
    monkeypatch.setattr(resources.time, "perf_counter", lambda: next(clock))
    guard = Guard(Budget(max_seconds=0.25))
    with pytest.raises(ResourceLimitExceeded) as caught:
        guard.check_time()
    assert caught.value.limit == 0.25 and caught.value.observed == 0.5
    assert caught.value.hint is None
