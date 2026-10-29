"""Regressions found by an independent whole-call-budget audit of prepared references."""
from unittest.mock import patch

import pytest

from symq.experimental.api import replay
from symq.experimental.contracts import VerificationContract
from symq.experimental.domains import AffineDomain, FullCube
from symq.experimental.prepared import PreparedReference
from symq.phase import PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded


def _first_validation_costs_two_seconds(clock):
    actual = PhaseProgram.validate
    called = False

    def validate(self):
        nonlocal called
        if not called:
            clock[0] += 2
            called = True
        return actual(self)

    return validate


def test_reference_preparation_budget_starts_before_validation():
    clock = [100.0]
    program = PhaseProgram(1)
    with (patch("symq.resources.time.perf_counter", lambda: clock[0]),
          patch.object(PhaseProgram, "validate", _first_validation_costs_two_seconds(clock)),
          pytest.raises(ResourceLimitExceeded, match="seconds")):
        PreparedReference(program, budget=Budget(max_seconds=1))


def test_prepared_comparison_validation_spends_the_callers_budget():
    clock = [100.0]
    program = PhaseProgram(1)
    with PreparedReference(program) as prepared:
        with (patch("symq.resources.time.perf_counter", lambda: clock[0]),
              patch.object(PhaseProgram, "validate", _first_validation_costs_two_seconds(clock))):
            result = prepared.compare(program, budget=Budget(max_seconds=1))
        assert result.outcome == "inconclusive"
        assert not result.certified
        assert "seconds" in result.reason


def test_prepared_contract_cannot_relabel_restricted_roots_as_a_full_cube_proof():
    restricted = VerificationContract(domain=AffineDomain(1, 0, ()))
    full = VerificationContract(domain=FullCube(1))
    candidate = PhaseProgram(1).z(0)
    with PreparedReference(PhaseProgram(1), restricted) as prepared:
        assert prepared.compare(candidate).equivalent
        with pytest.raises(AttributeError):
            prepared.contract = full
        with pytest.raises(AttributeError):
            prepared.domain = FullCube(1)
        result = prepared.compare(candidate)
        assert result.equivalent
        assert result.contract_sha256 == restricted.sha256


@pytest.mark.parametrize("backend", ["zdd", "zdd-native"])
def test_early_output_counterexamples_use_bounded_cache_and_compaction(backend):
    from symq.backends import BACKENDS

    if backend not in BACKENDS:
        pytest.skip("optional native backend unavailable")
    reference = PhaseProgram(8)
    contract = VerificationContract(backend=backend)
    with PreparedReference(reference, contract, max_cache_entries=2) as prepared:
        baseline_nodes = prepared._algebra.node_count
        resident_nodes = []
        for controls_mask in range(1, 49):
            controls = tuple(q for q in range(7) if controls_mask >> q & 1)
            candidate = PhaseProgram(8).mcx(*controls, 7)
            result = prepared.compare(candidate)
            assert result.outcome == "different" and result.witness_kind == "input"
            assert replay(result, reference, candidate, contract).witness_checked
            assert len(prepared._cache) <= 2
            resident_nodes.append(prepared._algebra.node_count)
        assert prepared.comparisons == 48
        # Once full, the result cache evicts and drops all candidate roots.
        assert resident_nodes[2:] == [baseline_nodes] * 46
        assert max(resident_nodes) <= baseline_nodes + 4 * reference.width
        cached = prepared.compare(candidate)
        assert dict(cached.statistics)["cache_hit"] == 1
        assert replay(cached, reference, candidate, contract).witness_checked
        assert prepared.comparisons == 48
        assert prepared._algebra.node_count == baseline_nodes
