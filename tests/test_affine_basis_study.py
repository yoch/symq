from __future__ import annotations

import copy
import random
from fractions import Fraction
from time import perf_counter

import pytest
from testkit.affine_basis_oracle import ExactChannel

from benchmarks.affine_basis_cases import Case, dephase, make_case
from symq.errors import InternalInconsistency
from symq.labs import affine_basis_study as prototype
from symq.labs import affine_phase as core
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.phase import PhaseProgram
from symq.resources import Budget, VerificationSession


def checked(case, method, **kwargs):
    result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                           method=method, **kwargs)
    reference = ExactChannel(case)
    truth = reference.compare()
    assert (result["status"] == "equivalent") == truth["equivalent"]
    if result["status"] == "equivalent":
        assert result["receipt"] is not None
        replay = core.replay_affine_phase(case.left, case.right, case.dephaser,
                                         result["receipt"], support=case.support)
        assert replay.equivalent
    else:
        assert result["receipt"] is None
        assert result["witness"] is not None
        assert reference.validates_witness(result["witness"])
    return result


@pytest.mark.parametrize("method", prototype.METHODS)
@pytest.mark.parametrize("presentation", ("cycle", "partition", "almost_equal", "nonlinear"))
@pytest.mark.parametrize("family", ("identity", "perturbed", "dephased_identity"))
def test_all_coherent_matrix_units(method, presentation, family):
    case = make_case(family, n=4, k=4, presentation=presentation, seed=37, mixed_support=True)
    checked(case, method)


@pytest.mark.parametrize("method", prototype.METHODS)
@pytest.mark.parametrize("family", ("singleton", "single_dense", "invariant_dense", "grouped_zero",
                                    "output_negative"))
def test_other_positive_and_negative_families(method, family):
    checked(make_case(family, n=4, k=3), method)


@pytest.mark.parametrize("seed", range(32))
def test_random_sources_differential(seed):
    rng = random.Random(seed)
    width, k = rng.randrange(2, 5), rng.randrange(1, 6)
    left, right = DyadicPhaseProgram(width, k=k), DyadicPhaseProgram(width, k=k)
    reversible = []
    for _ in range(5):
        controls = tuple(rng.sample(range(width), rng.randrange(1, min(width, 3) + 1)))
        gate = "x" if len(controls) == 1 else "mcx"
        right.append(gate, *controls)
        reversible.append((gate, controls))
        right.phase(rng.randrange(width), Fraction(rng.randrange(1, 2**k), 2**k))
    for gate, controls in reversed(reversible):
        right.append(gate, *controls)
    rows = tuple(rng.randrange(1, 2**width) for _ in range(rng.randrange(0, 3)))
    columns = [1 << i for i in range(width)]
    for _ in range(width):
        i, j = rng.sample(range(width), 2)
        columns[i] ^= columns[j]
    dimension = rng.randrange(width + 1)
    domain = core.AffineSupport(width, rng.randrange(2**width), tuple(columns[:dimension]))
    case = Case(left, right, dephase(width, rows), domain, "oracle", {"seed": seed})
    for method in prototype.METHODS:
        checked(case, method)


def test_correlated_affine_domain_and_nonzero_offset():
    for offset in (0, 1):
        case = Case(DyadicPhaseProgram(2), DyadicPhaseProgram(2).z(0), PhaseProgram(2),
                    core.AffineSupport(2, offset, (3,)), "not_proved", {})
        for method in prototype.METHODS:
            checked(case, method)
        case.right.z(1)
        for method in prototype.METHODS:
            checked(case, method)


@pytest.mark.parametrize("selected", ((1,), (1, 1), (1, 4), (1, 0), (1, True)))
def test_incomplete_dependent_and_invalid_bases_rejected(selected):
    work = core._Work(core._guard(Budget(max_terms=1000)))
    with pytest.raises(InternalInconsistency):
        prototype.validate_basis((4,), 3, (1, 2), selected, work)


def test_invertible_transform_exactly_reconstructs_selected_basis():
    work = core._Work(core._guard(Budget(max_terms=1000)))
    transform = prototype.validate_basis((15,), 4, (9, 10, 12), (3, 6, 9), work)
    assert transform == (3, 6, 1)


def test_mutant_selector_cannot_drop_a_direction(monkeypatch):
    case = make_case("single_dense", n=4)
    monkeypatch.setattr(prototype, "select_basis", lambda *args: ())
    with pytest.raises(InternalInconsistency, match="cardinality"):
        prototype.run(case.left, case.right, case.dephaser, support=case.support, method="adaptive")


def test_mutant_heuristic_zero_scores_cannot_accept_false_equality(monkeypatch):
    case = make_case("perturbed", n=4)
    monkeypatch.setattr(prototype, "_score", lambda *args: (0, 0, 0))
    checked(case, "adaptive")


def test_soft_search_limit_falls_back_without_resetting_the_budget():
    case = make_case(n=5)
    result = checked(case, "adaptive", settings=prototype.Settings(max_search_units=1))
    assert result["metrics"]["selection_fallback"] == "search work cap"
    assert result["metrics"]["canonical_basis"] == result["metrics"]["selected_basis"]


def test_dimension_cap_keeps_complete_canonical_basis():
    case = make_case(n=4)
    result = checked(case, "adaptive", settings=prototype.Settings(max_dimension=1))
    assert result["metrics"]["selection_fallback"] == "dimension cap"


def test_candidate_cap_below_dimension_is_labelled_as_such():
    case = make_case(n=4)
    result = checked(case, "adaptive", settings=prototype.Settings(max_candidates=1))
    assert result["metrics"]["selection_fallback"] == "candidate cap"
    assert result["metrics"]["canonical_basis"] == result["metrics"]["selected_basis"]


def test_cache_eviction_and_bounded_observation_do_not_change_results():
    case = make_case(n=5)
    result = checked(case, "canonical_cache", settings=prototype.Settings(
        max_cache_entries=1, max_cache_terms=100, max_observed_key_terms=1))
    metrics = result["metrics"]
    assert metrics["cache_peak_terms"] <= 100
    assert metrics["cache_evictions"] > 0
    assert not metrics["unique_lift_keys_complete"]


def test_lift_cache_keys_include_coefficients_and_derivative_does_not_mutate_entries():
    work, metrics = core._Work(core._guard(Budget(max_terms=1000))), {}
    cache = prototype.Lifts(True, prototype.Settings(), work, metrics)
    value = frozenset((1, 2))
    one = dict(cache.get(value, 1, 8))
    minus = dict(cache.get(value, -1, 8))
    assert one != minus
    assert cache.get(value, 9, 8) == one
    assert cache.get(value, 1, 4) == {1: 1, 2: 1, 3: 2}
    prototype.derivative({value: 1}, 1, 3, work, cache)
    assert cache.get(value, 1, 8) == one
    assert metrics["lift_hits"] >= 2


@pytest.mark.parametrize("method", prototype.METHODS)
def test_term_and_inherited_deadline_caps_return_no_certificate(method):
    case = make_case(n=9, k=6)
    result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                           method=method, budget=Budget(max_terms=20))
    assert result["status"] == "inconclusive" and result["receipt"] is None
    with VerificationSession(Budget(max_seconds=5)) as session:
        saved_deadline = session._deadline
        session._deadline = perf_counter() - 1
        try:
            result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                                   method=method, budget=Budget(max_seconds=5))
            assert result["status"] == "inconclusive" and result["receipt"] is None
        finally:
            session._deadline = saved_deadline


def test_post_cleanup_deadline_cannot_return_equivalent(monkeypatch):
    original = prototype._execute

    def expires_on_return(*args):
        result = original(*args)
        args[-2].guard._deadline = perf_counter() - 1
        return result

    monkeypatch.setattr(prototype, "_execute", expires_on_return)
    case = make_case(n=3)
    result = prototype.run(case.left, case.right, case.dephaser, support=case.support)
    assert result["status"] == "inconclusive" and result["receipt"] is None


def test_source_and_receipt_mutations_fail_fresh_published_replay():
    case = make_case(n=4)
    result = checked(case, "canonical_cache")
    document = copy.deepcopy(result["receipt"])
    document["kernel_basis"] = document["kernel_basis"][:-1]
    assert not core.replay_affine_phase(case.left, case.right, case.dephaser, document,
                                       support=case.support).equivalent
    case.right.phase(0, Fraction(1, 8))
    assert not core.replay_affine_phase(case.left, case.right, case.dephaser, result["receipt"],
                                       support=case.support).equivalent


def test_nonaffine_and_nonrestoring_source_contracts_unchanged():
    left = DyadicPhaseProgram(2)
    bad_sources = (PhaseProgram(2, 1).ccx(0, 1, 2), PhaseProgram(2).x(0))
    bad_sources[0].hmr(2)
    for source in bad_sources:
        for method in prototype.METHODS:
            result = prototype.run(left, left, source, method=method)
            assert result["status"] == "not_proved" and result["receipt"] is None


@pytest.mark.parametrize("value", (True, 0, -1, 1.0))
def test_search_limits_reject_misleading_or_unbounded_values(value):
    with pytest.raises(ValueError):
        prototype.Settings(max_candidates=value)


def test_forged_dataclass_metadata_does_not_erase_caps():
    settings = prototype.Settings(max_search_units=1)
    object.__setattr__(settings, "__dataclass_fields__", {})
    result = checked(make_case(n=4), "adaptive", settings=settings)
    assert result["metrics"]["selection_fallback"] == "search work cap"
    object.__setattr__(settings, "max_search_units", 0)
    with pytest.raises(ValueError):
        checked(make_case(n=4), "adaptive", settings=settings)


def test_forged_settings_fields_reject_boolean_and_integer_subclasses():
    class MisleadingInt(int):
        pass

    for item in (True, MisleadingInt(128)):
        settings = prototype.Settings()
        object.__setattr__(settings, "max_candidates", item)
        with pytest.raises(ValueError):
            checked(make_case(n=4), "adaptive", settings=settings)


def test_settings_snapshot_is_inside_original_deadline(monkeypatch):
    original = prototype.freeze_settings

    def expired_after_snapshot(value, guard):
        result = original(value, guard)
        guard._deadline = perf_counter() - 1
        return result

    monkeypatch.setattr(prototype, "freeze_settings", expired_after_snapshot)
    case = make_case(n=3)
    for method in prototype.METHODS:
        result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                               method=method)
        assert result["status"] == "inconclusive" and result["receipt"] is None


@pytest.mark.parametrize("method", prototype.METHODS)
def test_final_receipt_conversion_is_inside_original_deadline(monkeypatch, method):
    original_freeze, original_document = prototype.freeze_settings, core.AffinePhaseReceipt.to_dict
    guards, conversions = [], []

    def freeze(value, guard):
        guards.append(guard)
        return original_freeze(value, guard)

    def document(receipt):
        conversions.append(receipt)
        result = original_document(receipt)
        if len(conversions) == 2:
            guards[0]._deadline = perf_counter() - 1
        return result

    monkeypatch.setattr(prototype, "freeze_settings", freeze)
    monkeypatch.setattr(core.AffinePhaseReceipt, "to_dict", document)
    case = make_case(n=3)
    result = prototype.run(case.left, case.right, case.dephaser, support=case.support, method=method,
                           budget=Budget(max_seconds=1))
    assert len(conversions) == 2
    assert result["status"] == "inconclusive" and result["receipt"] is None
