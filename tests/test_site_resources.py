"""Resource dossiers never turn a local assumption or an observation into a site proof."""
from dataclasses import FrozenInstanceError, replace
from itertools import product

import pytest
from testkit.kraus_oracle import independent_kraus

from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.channel_composition import FrozenHybridProgram, HybridFragment
from symq.labs.site_resources import (
    CacheRequirement,
    EvidenceNote,
    ResourceLease,
    SiteResourceRequest,
    assess_site_resources,
)
from symq.resources import Budget, ResourceLimitExceeded


def temporary_and(*, data=3, ancillas=1, prefix=(), missing_correction=False):
    original = (HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)), HOp("ccx", (0, 1, 3)))
    candidate = (HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
                 HOp("hmr", (3,), slot="b0"), HOp("cz", (0, 1), condition="b0"))
    if missing_correction:
        candidate = candidate[:-1]
    source = HybridProgram(data, ancillas, list(prefix + original))
    span = (len(prefix), len(prefix) + len(original))
    return SiteResourceRequest(
        FrozenHybridProgram.freeze(source), span, HybridFragment(4, candidate),
        (0, 1, 2, 3), (ResourceLease("temporary", 3, "clean_zero", span),),
    )


def obligation(result, name, resource="temporary"):
    return next(o for o in result.obligations if o.name == name and o.resource == resource)


def test_prepared_hmr_has_separate_entry_return_and_context_evidence():
    request = temporary_and()
    result = assess_site_resources(request)
    assert result.site_applicability == "established"
    assert result.local_equivalence.outcome == result.contextual_equivalence.outcome == "equivalent"
    assert obligation(result, "clean_input").status == "proved"
    assert obligation(result, "clean_input").condition_used_by_local_proof
    assert obligation(result, "restoration").status == "proved"
    assert result.source_span == (0, 3) and result.replacement_span == (0, 4)
    # The result remains an inspection dossier, not a candidate-carrying seal.
    report = result.to_dict()
    assert report["candidate_authorized"] is False and report["advisory_only"] is True
    assert report["coherent_control_extension"] == "not_established"
    assert not hasattr(result, "candidate")
    assert "not_independent_certificates" in report["evidence_level"]

    candidate = HybridProgram(3, 1, list(request.replacement.ops))
    for x, y in product(range(8), repeat=2):
        assert independent_kraus(request.source.to_program(), x, y) == independent_kraus(candidate, x, y)


def test_unknown_ancilla_keeps_local_theorem_conditional_despite_observation():
    request = temporary_and(data=4, ancillas=0)
    request = replace(request, notes=(EvidenceNote("temporary", "observation", "zero in sampled runs"),))
    result = assess_site_resources(request)
    assert result.local_equivalence.outcome == "equivalent"
    assert result.contextual_equivalence.outcome == "not_proved"
    assert result.site_applicability == "conditional"
    assert obligation(result, "clean_input").status == "open"
    assert obligation(result, "clean_input").evidence_origin == "assumption"
    assert obligation(result, "restoration").status == "proved"
    assert result.to_dict()["notes"][0]["condition_used_by_local_proof"] is False


def test_provably_dirty_ancilla_is_not_mistaken_for_an_unknown_clean_resource():
    result = assess_site_resources(temporary_and(prefix=(HOp("x", (3,)),)))
    assert result.local_equivalence.outcome == "equivalent"
    assert obligation(result, "clean_input").status == "not_satisfied"
    assert "proves one" in obligation(result, "clean_input").reason
    assert result.site_applicability == "not_applicable"


def test_217_operation_lease_may_hold_nonzero_temporary_values_inside():
    # Original synthetic example, not the external DQI optimization or a scaling claim.
    ops = (HOp("cx", (0, 2)),) + (HOp("z", (1,)),) * 215 + (HOp("cx", (0, 2)),)
    source = HybridProgram(2, 1, list(ops))
    request = SiteResourceRequest(
        FrozenHybridProgram.freeze(source), (0, 217), HybridFragment(3, ops), (0, 1, 2),
        (ResourceLease("temporary", 2, "clean_zero", (0, 217)),),
    )
    result = assess_site_resources(request)
    assert result.site_applicability == "established"
    assert obligation(result, "restoration").status == "proved"
    assert result.source_span == result.replacement_span == (0, 217)
    # On input |01>, the first operation writes 1 into the temporary wire.
    middle = HybridProgram(2, 1, [ops[0]])
    assert independent_kraus(middle, 1, 1)[()] == {(5, 5): 1}
    assert independent_kraus(source, 1, 1)[()] == {(1, 1): 1}


def test_larger_reservation_is_explicitly_open_instead_of_inferred_from_idleness():
    base = temporary_and()
    source = replace(base.source, ops=base.source.ops + (HOp("x", (0,)),))
    request = replace(base, source=source,
                      resources=(ResourceLease("temporary", 3, "clean_zero", (0, 4)),))
    result = assess_site_resources(request)
    assert result.contextual_equivalence.outcome == "equivalent"
    assert obligation(result, "reservation").status == "open"
    assert result.site_applicability == "conditional"


def test_clean_return_is_a_separate_requirement_even_for_identical_programs():
    ops = (HOp("x", (1,)),)
    request = SiteResourceRequest(
        FrozenHybridProgram.freeze(HybridProgram(1, 1, list(ops))), (0, 1),
        HybridFragment(2, ops), (0, 1),
        (ResourceLease("temporary", 1, "clean_zero", (0, 1)),),
    )
    result = assess_site_resources(request)
    assert result.local_equivalence.outcome == result.contextual_equivalence.outcome == "equivalent"
    assert obligation(result, "restoration").status == "open"
    assert result.site_applicability == "conditional"


def test_borrowed_bridge_preserves_arbitrary_correlations():
    ops = (HOp("cx", (0, 1)), HOp("cx", (1, 2)), HOp("cx", (0, 1)), HOp("cx", (1, 2)))
    candidate = (HOp("cx", (0, 2)),)
    request = SiteResourceRequest(
        FrozenHybridProgram.freeze(HybridProgram(3, 0, list(ops))), (0, 4),
        HybridFragment(3, candidate), (0, 1, 2),
        (ResourceLease("borrow", 1, "borrowed", (0, 4)),),
    )
    result = assess_site_resources(request)
    assert result.site_applicability == "established"
    assert obligation(result, "restoration", "borrow").status == "proved"
    for x, y in product(range(8), repeat=2):
        assert independent_kraus(request.source.to_program(), x, y) == independent_kraus(
            HybridProgram(3, 0, list(candidate)), x, y,
        )


def test_borrowed_phase_error_fails_despite_equal_classical_bits():
    ops = (HOp("cz", (0, 1)),)
    request = SiteResourceRequest(
        FrozenHybridProgram.freeze(HybridProgram(2, 0, list(ops))), (0, 1),
        HybridFragment(2, ops), (0, 1), (ResourceLease("borrow", 1, "borrowed", (0, 1)),),
    )
    result = assess_site_resources(request)
    assert result.local_equivalence.outcome == "equivalent"  # the two programs are identical
    assert obligation(result, "restoration", "borrow").status == "open"
    assert result.contextual_equivalence.outcome == "not_proved"
    assert result.site_applicability == "conditional"
    identity = HybridProgram(2)
    for x in range(4):
        assert independent_kraus(request.source.to_program(), x, x) == independent_kraus(identity, x, x)
    assert independent_kraus(request.source.to_program(), 3, 1) != independent_kraus(identity, 3, 1)


def test_missing_hmr_correction_fails_even_when_ancilla_return_is_correct():
    request = temporary_and(missing_correction=True)
    result = assess_site_resources(request)
    assert result.local_equivalence.outcome == "not_proved"
    assert result.site_applicability == "not_established"
    assert obligation(result, "restoration").status == "proved"
    wrong = HybridProgram(3, 1, list(request.replacement.ops))
    assert any(independent_kraus(request.source.to_program(), x, y)
               != independent_kraus(wrong, x, y)
               for x, y in product(range(8), repeat=2) if x != y)


def test_semantics_preserving_mutation_is_accepted():
    request = temporary_and()
    replacement = replace(request.replacement,
                          ops=request.replacement.ops + (HOp("x", (0,)), HOp("x", (0,))))
    assert assess_site_resources(replace(request, replacement=replacement)).site_applicability == "established"


@pytest.mark.parametrize("live", [False, True])
def test_actual_suffix_selects_instrument_instead_of_forgotten_channel(live):
    ops = (HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"))
    suffix = (HOp("x", (0,), condition="b0"),) if live else ()
    request = SiteResourceRequest(
        FrozenHybridProgram.freeze(HybridProgram(2, 0, list(ops + suffix))), (0, 2),
        HybridFragment(2, ops + (HOp("invert", slot="b0"),)), (0, 1),
    )
    result = assess_site_resources(request)
    assert result.site_applicability == ("not_established" if live else "established")
    assert result.local_equivalence.theorem == (
        "local_coherent_instrument" if live else "local_coherent_channel"
    )


def test_explicit_observed_slot_also_requires_instrument_comparison():
    ops = (HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"))
    request = SiteResourceRequest(
        FrozenHybridProgram.freeze(HybridProgram(2, 0, list(ops))), (0, 2),
        HybridFragment(2, ops + (HOp("invert", slot="b0"),)), (0, 1),
        observed_slots=("b0",),
    )
    result = assess_site_resources(request)
    assert result.local_equivalence.theorem == "local_coherent_instrument"
    assert result.site_applicability == "not_established"


def test_a_declared_classical_input_cannot_read_a_future_measurement():
    source = HybridProgram(2, 0, [HOp("measure_z", (1,), slot="b0"), HOp("x", (0,), condition="b0")])
    replacement = HybridFragment(2, (
        HOp("x", (0,), condition="b0"), HOp("measure_z", (1,), slot="b0"),
    ), ("b0",))
    request = SiteResourceRequest(FrozenHybridProgram.freeze(source), (0, 2), replacement, (0, 1))
    result = assess_site_resources(request)
    assert obligation(result, "classical_inputs", "site").status == "open"
    assert result.contextual_equivalence.outcome == "unsupported"
    assert "uninitialized" in result.contextual_equivalence.reason


def test_reused_classical_name_keeps_the_old_and_new_ssa_versions():
    ops = (HOp("store", slot="b0", value=1), HOp("x", (0,), condition="b0"),
           HOp("measure_z", (1,), slot="b0"), HOp("x", (0,), condition="b0"))
    request = SiteResourceRequest(FrozenHybridProgram.freeze(HybridProgram(2, 0, list(ops))),
                                  (0, 4), HybridFragment(2, ops), (0, 1))
    result = assess_site_resources(request)
    assert result.site_applicability == "established"
    assert [(r.operation, r.version, r.measurement_events) for r in result.classical_reads] == [
        (1, 0, ()), (3, 1, (0,)),
    ]


def cache_request(*, changed):
    prefix = (HOp("ccx", (0, 1, 2)),)
    if changed:
        prefix += (HOp("x", (0,)),)
    use = (HOp("cx", (2, 3)),)
    source = HybridProgram(4, 0, list(prefix + use))
    cache = CacheRequirement("product", "q2 = q0 AND q1", (0, 1, 2), (), 1, len(prefix))
    return SiteResourceRequest(
        FrozenHybridProgram.freeze(source), (len(prefix), len(prefix) + 1),
        HybridFragment(2, (HOp("cx", (0, 1)),)), (2, 3), caches=(cache,),
        notes=(EvidenceNote("product", "observation", "relation observed before subsequent operations"),),
    )


@pytest.mark.parametrize("changed", [False, True])
def test_cache_versions_never_replace_a_relation_proof(changed):
    result = assess_site_resources(cache_request(changed=changed))
    assert result.local_equivalence.outcome == result.contextual_equivalence.outcome == "equivalent"
    cache = obligation(result, "cache_relation", "product")
    assert cache.status == "open" and not cache.condition_used_by_local_proof
    assert ("dependencies changed" in cache.reason) == changed
    assert any(a != b for _, a, b in cache.dependency_versions) == changed
    assert result.site_applicability == "conditional"


def test_classical_cache_watch_detects_overwrite_even_with_the_same_slot_name():
    ops = (HOp("store", slot="b0", value=0), HOp("store", slot="b0", value=1),
           HOp("x", (0,), condition="b0"))
    request = SiteResourceRequest(
        FrozenHybridProgram.freeze(HybridProgram(1, 0, list(ops))), (2, 3),
        HybridFragment(1, (ops[-1],), ("b0",)), (0,),
        caches=(CacheRequirement("flag", "b0 = 0", (), ("b0",), 1, 2),),
    )
    result = assess_site_resources(request)
    assert obligation(result, "cache_relation", "flag").dependency_versions == (("b0", 0, 1),)
    assert result.site_applicability == "conditional"


def test_forged_or_mutated_report_is_not_a_proof_input():
    request = temporary_and(data=4, ancillas=0)
    result = assess_site_resources(request)
    report = result.to_dict()
    report["site_applicability"] = "established"
    report["candidate_authorized"] = True
    report["local_equivalence"]["evidence_level"] = "independent_certificate"
    with pytest.raises(TypeError, match="reports are not proof inputs"):
        assess_site_resources(report)
    assert result.site_applicability == "conditional"
    assert assess_site_resources(request).site_applicability == "conditional"


def test_source_change_with_identical_window_invalidates_the_site_binding():
    request = temporary_and(prefix=(HOp("z", (0,)),))
    original = assess_site_resources(request)
    altered_source = replace(request.source, ops=(HOp("x", (3,)),) + request.source.ops[1:])
    altered = assess_site_resources(replace(request, source=altered_source))
    assert request.source.ops[1:] == altered_source.ops[1:]
    assert original.source_sha256 != altered.source_sha256
    assert original.request_sha256 != altered.request_sha256
    assert original.site_applicability == "established"
    assert altered.site_applicability == "not_applicable"


def test_freezing_source_and_request_prevents_accidental_builder_mutation():
    source = HybridProgram(2, 0, [HOp("x", (0,))])
    request = SiteResourceRequest(FrozenHybridProgram.freeze(source), (0, 1),
                                  HybridFragment(2, (HOp("x", (0,)),)), (0, 1))
    source.ops[0] = HOp("x", (1,))
    assert request.source.ops == (HOp("x", (0,)),)
    assert assess_site_resources(request).site_applicability == "established"
    with pytest.raises(FrozenInstanceError):
        request.span = (0, 0)


def test_resource_exhaustion_is_inconclusive_and_never_an_application(monkeypatch):
    from symq.labs import site_resources

    def exhausted(*args, **kwargs):
        raise ResourceLimitExceeded("test proof budget", 1, 2)

    monkeypatch.setattr(site_resources, "_conditional_check", exhausted)
    result = assess_site_resources(temporary_and())
    assert result.site_applicability == "inconclusive"
    assert result.contextual_equivalence.outcome == "not_run"
    assert result.to_dict()["candidate_authorized"] is False


def test_operation_limit_and_whole_call_deadline_are_explicit():
    result = assess_site_resources(temporary_and(), max_operations=2)
    assert result.site_applicability == "inconclusive"
    assert "site operations" in result.interrupted
    assert assess_site_resources(temporary_and(), budget=Budget(max_seconds=1e-12)).site_applicability == "inconclusive"


def test_global_wire_and_ssa_event_bounds_precede_large_intermediate_allocations():
    result = assess_site_resources(temporary_and(), max_global_wires=3)
    assert result.site_applicability == "inconclusive" and "global wires" in result.interrupted
    ops = (HOp("hmr", (0,), slot="b0"), HOp("hmr", (0,), slot="b0"))
    request = SiteResourceRequest(FrozenHybridProgram.freeze(HybridProgram(1, 0, list(ops))),
                                  (0, 2), HybridFragment(1, ops), (0,))
    result = assess_site_resources(request, max_measurement_events=1)
    assert result.site_applicability == "inconclusive" and "measurement events" in result.interrupted


def test_refuse_conflicting_or_forged_contract_fields():
    request = temporary_and()
    with pytest.raises(ValueError, match="never a proof"):
        EvidenceNote("temporary", "proof", "I certify this resource")
    with pytest.raises(ValueError, match="conflicting"):
        replace(request, resources=request.resources + (ResourceLease("borrow", 3, "borrowed", (0, 3)),))
    with pytest.raises(ValueError, match="cover"):
        replace(request, resources=(ResourceLease("temporary", 3, "clean_zero", (1, 3)),))
    with pytest.raises(ValueError, match="unique"):
        replace(request, wires=(0, 1, 2, 2))
    with pytest.raises(ValueError, match="node/byte"):
        assess_site_resources(request, budget=Budget(max_nodes=10))
    with pytest.raises(ValueError, match="span"):
        ResourceLease("temporary", 3, "clean_zero", (True, 3))


@pytest.mark.parametrize("kind", ["resource", "cache", "note"])
def test_revalidate_nested_dataclasses_even_when_their_initializers_were_bypassed(kind):
    request = temporary_and()
    if kind == "resource":
        forged = ResourceLease("temporary", 3, "clean_zero", (0, 3))
        object.__setattr__(forged, "kind", "invented_preparation")
        field, values = "resources", (forged,)
    elif kind == "cache":
        forged = CacheRequirement("cache", "q0 = 0", (0,), (), 0, 1)
        object.__setattr__(forged, "established_at", True)
        field, values = "caches", (forged,)
    else:
        forged = EvidenceNote("temporary", "observation", "sampled")
        object.__setattr__(forged, "origin", "proof")
        field, values = "notes", (forged,)
    with pytest.raises(ValueError):
        replace(request, **{field: values})
    object.__setattr__(request, field, values)
    with pytest.raises(ValueError):
        assess_site_resources(request)

