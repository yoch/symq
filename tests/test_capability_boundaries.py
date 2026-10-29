"""Static admission agrees with the exact engine's declared boundaries.

These checks do not execute an exponential-width oracle or predict whether a
runtime branch/node/time budget will fit.
"""
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from symq.backends import BACKENDS, make_algebra
from symq.experimental import AffineDomain, VerificationContract, inspect, verify
from symq.experimental.capabilities import backend_capabilities
from symq.experimental.hybrid import HybridProgram
from symq.phase import PhaseProgram
from symq.resources import ResourceLimitExceeded


@pytest.mark.parametrize("width", (6, 7))
def test_hybrid_static_width_includes_zero_prepared_ancillas(width):
    program = HybridProgram(1, width - 1)
    contract = VerificationContract(backend="hybrid-exact")
    caps = inspect(program, program, contract=contract)
    assert caps.grammar_supported and caps.backend_available and caps.contract_compatible
    assert caps.supported == caps.monolithic_supported == caps.static_admissible == (width == 6)
    assert dict(caps.static_limits) == {"width": 6, "events": 8}
    assert dict(caps.runtime_limits) == {"branches": 256, "terms": None, "seconds": None}
    result = verify(program, program, contract)
    assert result.outcome == ("equivalent" if width == 6 else "inconclusive")
    if width == 7:
        assert any(d.category == "static_limit" and (d.resource, d.observed, d.limit) ==
                   ("width", 7, 6) for d in caps.diagnostics)
        assert "width" in result.reason


@pytest.mark.parametrize("events", (8, 9))
def test_hybrid_event_cap_is_static_but_branch_count_is_runtime(events):
    program = HybridProgram(1)
    for _ in range(events):
        program.hmr(0, "b0")
    caps = inspect(program, engine="hybrid-exact")
    assert caps.static_admissible == (events == 8)
    assert caps.supported == (events == 8)
    if events == 9:
        assert verify(program, program, engine="hybrid-exact").outcome == "inconclusive"
        assert any(d.resource == "events" for d in caps.diagnostics)


@pytest.mark.parametrize("backend,maximum", (("zdd-native", 64), ("zdd-native-wide", 128)))
@pytest.mark.parametrize("available", (False, True))
@pytest.mark.parametrize("data", (32, 33, 64, 65))
def test_native_paired_width_and_optional_availability_are_independent(
        monkeypatch, backend, maximum, available, data):
    if available:
        monkeypatch.setitem(BACKENDS, backend, SimpleNamespace(max_width=maximum))
    else:
        monkeypatch.delitem(BACKENDS, backend, raising=False)
    caps = inspect(PhaseProgram(data), engine=backend)
    assert caps.grammar_supported and caps.contract_compatible
    assert caps.backend_available == available
    assert caps.static_admissible == (2 * data <= maximum)
    assert caps.supported == (available and 2 * data <= maximum)
    assert caps.monolithic_supported == caps.supported
    assert caps.pair_variables == 2 * data and caps.max_pair_variables == maximum
    assert backend_capabilities()[backend] == {"pair_variables": maximum, "available": available}


@pytest.mark.parametrize("backend,maximum", (("zdd-native", 64), ("zdd-native-wide", 128)))
@pytest.mark.parametrize("width", (64, 65, 128, 129))
def test_native_representation_boundaries_match_registered_capability(backend, maximum, width):
    if backend not in BACKENDS:
        pytest.skip("optional native backend unavailable")
    assert backend_capabilities()[backend]["pair_variables"] == maximum
    if width > maximum:
        with pytest.raises(ResourceLimitExceeded, match="width"):
            make_algebra(backend, width)
    else:
        algebra = make_algebra(backend, width)
        high_bit = 1 << (width - 1)
        assert algebra.to_anf(algebra.variable(width - 1)).terms == frozenset({high_bit})


def test_inspect_distinguishes_grammar_contract_and_static_limit():
    hybrid = HybridProgram(1)
    wrong_engine = inspect(hybrid, engine="zdd")
    assert not wrong_engine.grammar_supported and wrong_engine.backend_available
    assert wrong_engine.static_admissible and wrong_engine.contract_compatible
    assert wrong_engine.diagnostics[0].category == "grammar"
    domain = AffineDomain(1, 0, ())
    wrong_domain = inspect(hybrid, contract=VerificationContract(backend="hybrid-exact", domain=domain))
    assert wrong_domain.grammar_supported and wrong_domain.static_admissible
    assert not wrong_domain.contract_compatible and not wrong_domain.monolithic_supported
    assert any(d.category == "contract" for d in wrong_domain.diagnostics)
    missing_slot = inspect(hybrid, contract=VerificationContract(
        "instrument", "hybrid-exact", observed_slots=("b0",)))
    assert not missing_slot.supported and not missing_slot.contract_compatible


def test_ordered_output_mappings_and_output_dimensions_are_checked():
    small, large = HybridProgram(1), HybridProgram(1, 1)
    contract = VerificationContract("reduced_channel", "hybrid-exact",
                                    left_outputs=(0,), right_outputs=(1,))
    assert inspect(small, large, contract=contract).supported
    assert verify(small, large, contract).outcome == "different"
    assert not inspect(large, small, contract=contract).contract_compatible
    outside = VerificationContract("reduced_channel", "hybrid-exact",
                                   left_outputs=(1,), right_outputs=(0,))
    assert not inspect(small, large, contract=outside).supported
    dimensions = VerificationContract("reduced_channel", "hybrid-exact",
                                      left_outputs=(), right_outputs=(0,))
    assert not inspect(small, large, contract=dimensions).contract_compatible
    full = inspect(small, large, engine="hybrid-exact")
    assert not full.contract_compatible and not full.monolithic_supported


def test_pair_inspection_checks_both_sides_and_serializes_diagnostics():
    small, wide = HybridProgram(1), HybridProgram(1, 6)
    contract = VerificationContract("reduced_channel", "hybrid-exact",
                                    left_outputs=(0,), right_outputs=(0,))
    caps = inspect(small, wide, contract=contract)
    assert not caps.supported and caps.contract_compatible and not caps.static_admissible
    assert any(d["resource"] == "width" and d["observed"] == 7
               for d in asdict(caps)["diagnostics"])
    assert verify(small, wide, contract).outcome == "inconclusive"


def test_native_block_admission_does_not_confuse_width_with_availability(monkeypatch):
    program = PhaseProgram(65)
    monkeypatch.delitem(BACKENDS, "zdd-native", raising=False)
    caps = inspect(program, program, engine="zdd-native-blocks")
    assert caps.static_admissible and not caps.backend_available and not caps.supported
    assert not caps.monolithic_supported and not caps.blocks_supported
    assert any(d.category == "availability" for d in caps.diagnostics)


@pytest.mark.parametrize("program_type,backend", ((PhaseProgram, "zdd"),
                                                (HybridProgram, "hybrid-exact")))
def test_malformed_physical_contracts_remain_validation_errors(program_type, backend):
    left, right = program_type(1), program_type(1, 1)
    assert not inspect(left, right, engine=backend).contract_compatible
    with pytest.raises(ValueError, match="widths must match"):
        verify(left, right, engine=backend)
    invalid_mapping = VerificationContract("reduced_channel", backend,
                                           left_outputs=(1,), right_outputs=(0,))
    assert not inspect(left, right, contract=invalid_mapping).contract_compatible
    with pytest.raises(ValueError, match="valid wires"):
        verify(left, right, invalid_mapping)
    invalid_dimension = VerificationContract("reduced_channel", backend,
                                             left_outputs=(), right_outputs=(0,))
    with pytest.raises(ValueError, match="dimensions differ"):
        verify(left, right, invalid_dimension)
