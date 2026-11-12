"""Address widths beyond what the table verifiers support are refused, not crashed on.

A downstream report on 0.2.0 found that ``verify_shared_table`` accepted and documented
16 address bits while the verifier behind it refused anything above 12 with a bare
``ValueError('table width cap')``. 0.2.1 made a well-formed wider table ``unsupported``
(no verdict, no exception) with a reason naming both widths. Since 0.3.0 the version-2
and shared contracts are verified up to 16 address bits (``affine_table.MAX_ADDRESS_BITS``)
and version-1 contracts keep their limit of 12. The fixture is the report's minimal one:
an identity program, a constant-zero table, every address legal.
"""
from __future__ import annotations

import pytest

from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.experimental.table_xor import PredicateValues
from symq.labs.affine_table import MAX_ADDRESS_BITS as AFFINE_ADDRESS_BITS
from symq.labs.affine_table import verify_affine_table
from symq.labs.anchored_kraus import MAX_ADDRESS_BITS, verify
from symq.labs.anchored_stream import verify_stream
from symq.labs.shared_table import SharedTable, verify_shared_table
from symq.resources import Budget, Guard, ResourceLimitExceeded, VerificationSession

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


def _v2_contract(address_bits: int) -> dict:
    contract = _v1_contract(address_bits)
    del contract["target_values"]
    contract.update(kind="symq_affine_hmr_table_contract", schema_version=2,
                    target_space={"kind": "affine_image", "offset": 0, "columns": [1]})
    return contract


def test_the_documented_limits_are_the_enforced_ones():
    assert MAX_ADDRESS_BITS == 12 and AFFINE_ADDRESS_BITS == 16


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_table_at_the_limit_is_still_proved(backend):
    result = verify_shared_table(_identity(12), _shared_contract(12), backend=backend)
    assert result["status"] == "equivalent", result


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("address_bits", [13, 14, 16])
def test_a_shared_table_up_to_16_bits_is_proved(backend, address_bits):
    result = verify_shared_table(_identity(address_bits), _shared_contract(address_bits),
                                 backend=backend)
    assert result["status"] == "equivalent", result
    assert result["address_domain_size"] == 1 << address_bits
    assert result["actual_context_preparation_proved"] is False


def _every_verifier(source, contract):
    yield verify(source, contract)
    yield verify_stream(source, contract)
    yield verify_stream(source, contract, backend="sat")


@pytest.mark.sat
def test_the_version_1_verifiers_refuse_the_same_way():
    source, contract = program_to_dict(HybridProgram(14, 0)), _v1_contract(13)
    for result in _every_verifier(source, contract):
        assert result["status"] == "unsupported"
        assert result["obligation"] == "capacity"
        assert "address width 13" in result["reason"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_affine_verifier_refuses_beyond_16_bits(backend):
    result = verify_affine_table(program_to_dict(HybridProgram(18, 0)), _v2_contract(17),
                                 backend=backend)
    assert result["status"] == "unsupported" and result["obligation"] == "capacity"
    assert result["witness"] is None
    assert result["reason"] == "address width 17 exceeds this verifier's limit of 16"
    assert verify_affine_table(program_to_dict(HybridProgram(17, 0)), _v2_contract(16),
                               backend=backend)["status"] == "equivalent"


@pytest.mark.sat
def test_too_many_targets_is_unsupported_too():
    """The reference verifiers keep their 16-target limit; 17 targets is a capacity refusal."""
    source, contract = program_to_dict(HybridProgram(18, 0)), _v1_contract(1, 17)
    for result in _every_verifier(source, contract):
        assert result["status"] == "unsupported"
        assert result["reason"] == "target width 17 exceeds this verifier's limit of 16"


def _malformed(contract: dict, defect: str) -> dict:
    if defect == "short table":
        contract["table"] = contract["table"][:-1]
    elif defect == "unsorted addresses":
        contract["legal_addresses"] = contract["legal_addresses"][::-1]
    elif defect == "row out of range":
        contract["table"][1] = 1 << len(contract["target_wires"])
    elif defect == "bad target values":
        contract["target_values"] = [7]
    return contract


@pytest.mark.parametrize("address_bits", [2, 13])
@pytest.mark.parametrize("defect", ["short table", "unsorted addresses", "row out of range",
                                    "bad target values"])
def test_a_malformed_contract_raises_whatever_its_width(address_bits, defect):
    """``unsupported`` is reserved for well-formed contracts: width does not hide a defect."""
    source = program_to_dict(HybridProgram(address_bits + 1, 0))
    contract = _malformed(_v1_contract(address_bits), defect)
    for check in (verify, verify_stream):
        with pytest.raises(ValueError):
            check(source, contract)


@pytest.mark.parametrize("address_bits", [2, 13])
def test_a_malformed_source_raises_whatever_the_width(address_bits):
    source = program_to_dict(HybridProgram(address_bits + 1, 0))
    source["ops"] = [{"kind": "teleport", "wires": [0], "slot": None, "condition": None,
                      "source": None, "value": None}]
    with pytest.raises(ValueError):
        verify(source, _v1_contract(address_bits))


@pytest.mark.parametrize("address_bits", [2, 13])
def test_a_bad_target_space_raises_whatever_the_width(address_bits):
    contract = _v2_contract(address_bits)
    contract["target_space"] = {"kind": "affine_image", "offset": 5, "columns": [1]}
    with pytest.raises(ValueError):
        verify_affine_table(program_to_dict(HybridProgram(address_bits + 1, 0)), contract)


def test_an_expired_deadline_reports_a_zero_limit_and_says_why():
    """A deadline already past when the work starts was reported as a negative limit."""
    with pytest.raises(ResourceLimitExceeded) as caught:
        Guard(Budget(absolute_deadline=0)).check_time()
    error = caught.value
    assert error.resource == "seconds" and error.limit == 0.0 and error.observed >= 0
    assert error.hint == "the deadline had already passed when this computation started"
    assert "limit -" not in str(error)


def test_an_expired_session_reports_the_same_way():
    with pytest.raises(ResourceLimitExceeded) as entering, \
            VerificationSession(Budget(absolute_deadline=0)):
        pass
    session = VerificationSession(Budget(absolute_deadline=0))
    for raised in [entering.value] + [_raised(call) for call in (session.remaining_seconds,
                                                                  session.remaining_budget)]:
        assert raised.limit == 0.0
        assert raised.hint == "the deadline had already passed when this computation started"


def _raised(call):
    with pytest.raises(ResourceLimitExceeded) as caught:
        call()
    return caught.value


def test_a_tiny_positive_budget_is_not_reported_as_zero():
    """Rounding must not turn a positive limit into the "already expired" zero."""
    with pytest.raises(ResourceLimitExceeded) as caught:
        guard = Guard(Budget(max_seconds=3e-7))
        while True:
            guard.check_time()
    # The limit is a difference of clock readings, so only its order of magnitude is exact;
    # rounding to 6 decimals (the defect) would have made it 0.
    assert 1e-7 < caught.value.limit < 1e-6 and caught.value.hint is None


def test_a_running_deadline_keeps_its_duration_and_no_hint(monkeypatch):
    from symq import resources

    clock = iter([100.0, 100.5])
    monkeypatch.setattr(resources.time, "perf_counter", lambda: next(clock))
    guard = Guard(Budget(max_seconds=0.25))
    with pytest.raises(ResourceLimitExceeded) as caught:
        guard.check_time()
    assert caught.value.limit == 0.25 and caught.value.observed == 0.5
    assert caught.value.hint is None
