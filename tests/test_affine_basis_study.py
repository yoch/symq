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


# Lift-reuse methods: identical derivative polynomials, so identical decisions and receipts.

def _random_sources(seed, width_range=(2, 5), phases=5):
    rng = random.Random(seed)
    width, k = rng.randrange(*width_range), rng.randrange(1, 7)
    programs = []
    for _ in range(2):
        program, reversible = DyadicPhaseProgram(width, k=k), []
        for _ in range(phases):
            controls = tuple(rng.sample(range(width), rng.randrange(1, min(width, 3) + 1)))
            gate = "x" if len(controls) == 1 else "mcx"
            program.append(gate, *controls)
            reversible.append((gate, controls))
            # Numerators of every 2-adic valuation, including M/2 and even multiples.
            program.phase(rng.randrange(width), Fraction(rng.randrange(1, 2**k), 2**k))
        for gate, controls in reversed(reversible):
            program.append(gate, *controls)
        programs.append(program)
    rows = tuple(rng.randrange(1, 2**width) for _ in range(rng.randrange(0, 3)))
    columns = [1 << i for i in range(width)]
    for _ in range(width):
        i, j = rng.sample(range(width), 2)
        columns[i] ^= columns[j]
    dimension = rng.randrange(width + 1)
    domain = core.AffineSupport(width, rng.randrange(2**width), tuple(columns[:dimension]))
    return Case(programs[0], programs[1], dephase(width, rows), domain, "random", {"seed": seed})


def _same_as_published(case, method, **kwargs):
    published = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                              method="published")
    result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                           method=method, **kwargs)
    assert published["status"] != "inconclusive"
    for key in ("status", "receipt", "witness"):
        assert result[key] == published[key], (method, key)
    return result


@pytest.mark.parametrize("method", prototype.REUSE_METHODS)
def test_reuse_methods_match_published_and_the_oracle_on_random_sources(method):
    statuses = set()
    for seed in range(48):
        case = _random_sources(seed)
        result = _same_as_published(case, method)
        checked(case, method)
        statuses.add(result["status"])
    assert statuses == {"equivalent", "not_proved"}


@pytest.mark.parametrize("method", prototype.REUSE_METHODS)
def test_reuse_receipts_are_byte_identical_to_published_beyond_the_oracle(method):
    rng = random.Random(151)
    for index in range(16):
        family = rng.choice(("identity", "perturbed", "dephased_identity", "near_invariant_dense"))
        case = make_case(family, n=rng.randrange(5, 10), k=rng.randrange(1, 7),
                         presentation=rng.choice(("cycle", "partition", "almost_equal",
                                                  "nonlinear")),
                         seed=index, mixed_support=rng.random() < 0.5,
                         scale=rng.randrange(1, 9))
        _same_as_published(case, method)
    for seed in range(16):
        _same_as_published(_random_sources(1000 + seed, (5, 8), phases=8), method)


def _anf_value(value, z):
    return sum(1 for mask in value if mask & z == mask) % 2


def _evaluate(polynomial, z, modulus):
    return sum(c for mask, c in polynomial.items() if mask & z == mask) % modulus


def _canonical(*polynomials, modulus, work):
    out = {}
    for polynomial in polynomials:
        for mask, term in polynomial.items():
            core._add_term(out, mask, term, modulus, work)
    return out


def test_lift_sign_scaling_and_complement_identities_exhaustively_for_three_variables():
    work = core._Work(core._guard(Budget(max_terms=10_000)))
    one = frozenset((0,))
    for bits in range(256):
        value = frozenset(mask for mask in range(8) if bits >> mask & 1)
        for k in range(1, 5):
            modulus = 1 << k
            for c in range(modulus):
                lifted = core._lift(value, c, modulus, work)
                # Independent check: the lift is the function z -> c [p(z)] mod 2^k.
                assert all(_evaluate(lifted, z, modulus) == c * _anf_value(value, z) % modulus
                           for z in range(8))
                negated = {mask: -t % modulus for mask, t in lifted.items()}
                assert core._lift(value, -c, modulus, work) == negated
                doubled = _canonical({m: 2 * t for m, t in lifted.items()}, modulus=modulus,
                                     work=work)
                assert core._lift(value, 2 * c, modulus, work) == doubled
                complement = _canonical({0: c}, negated, modulus=modulus, work=work)
                assert core._lift(value ^ one, c, modulus, work) == complement
                derivative = _canonical({0: c}, core._lift(value, -2 * c, modulus, work),
                                        modulus=modulus, work=work)
                assert _canonical(core._lift(value ^ one, c, modulus, work), negated,
                                  modulus=modulus, work=work) == derivative


def test_boolean_derivative_split_identity():
    work = core._Work(core._guard(Budget(max_terms=10_000)))
    pairs = [(p, d) for p in range(16) for d in range(16)]  # exhaustive on two variables
    rng = random.Random(7)
    pairs += [(rng.randrange(256), rng.randrange(256)) for _ in range(400)]  # three variables
    for p_bits, d_bits in pairs:
        p = frozenset(m for m in range(8) if p_bits >> m & 1)
        d = frozenset(m for m in range(8) if d_bits >> m & 1)
        for k in range(1, 5):
            modulus = 1 << k
            for c in range(1, modulus):
                left = _canonical(core._lift(p ^ d, c, modulus, work),
                                  core._lift(p, -c, modulus, work), modulus=modulus, work=work)
                right = _canonical(core._lift(d, c, modulus, work),
                                   core._lift(core._product([p, d], work), -2 * c, modulus, work),
                                   modulus=modulus, work=work)
                assert left == right


@pytest.mark.parametrize("method", prototype.REUSE_METHODS)
def test_reuse_derivatives_equal_the_published_derivative_along_every_direction(method):
    rng = random.Random(29)
    for _ in range(40):
        n, k = rng.randrange(1, 5), rng.randrange(1, 6)
        delta = {}
        for _ in range(rng.randrange(1, 5)):
            value = frozenset(m for m in range(2**n) if rng.random() < 0.4)
            if value:
                delta[value] = rng.randrange(1, 2**k)
        directions = tuple(range(1, 2**n))
        work = core._Work(core._guard(Budget(max_terms=100_000)))
        metrics = {}
        lifts = prototype.Lifts(True, prototype.Settings(), work, metrics)
        reuse = prototype.Reuse(method, delta, directions, k, work, metrics, lifts)
        for direction in directions:
            assert reuse.derivative(direction) == core._derivative(delta, direction, k, work)


CACHE_SETTINGS = (prototype.Settings(), prototype.Settings(max_cache_entries=1, max_cache_terms=1),
                  prototype.Settings(max_cache_entries=1, max_cache_terms=100),
                  prototype.Settings(max_cache_entries=2, max_cache_terms=400,
                                     max_observed_key_terms=1))


@pytest.mark.parametrize("method", prototype.REUSE_METHODS)
def test_cache_size_eviction_and_pinned_rejection_do_not_change_results(method):
    cases = (make_case(n=6), make_case("perturbed", n=6), make_case(n=6, presentation="nonlinear"),
             make_case(n=5, k=5, mixed_support=True, seed=3, scale=6))
    counters = {"evictions": 0, "rejected": 0, "pinned_hits": 0}
    for case in cases:
        reference = None
        for settings in CACHE_SETTINGS:
            # Small term budgets refuse pinned entries (recomputed) or end inconclusive.
            for terms in (100_000, 600, 200, 120, 90, 60):
                budget = Budget(max_terms=terms)
                result = prototype.run(case.left, case.right, case.dephaser,
                                       support=case.support, method=method, settings=settings,
                                       budget=budget)
                if result["status"] == "inconclusive":
                    assert result["receipt"] is None and result["witness"] is None
                    continue
                observed = (result["status"], result["receipt"], result["witness"])
                reference = reference or observed
                assert observed == reference
                metrics = result["metrics"]
                counters["evictions"] += metrics["cache_evictions"]
                counters["rejected"] += metrics["pinned_rejected"]
                counters["pinned_hits"] += metrics["pinned_hits"]
        assert reference is not None
        checked(case, method)
    if method != "canonical_factorized":  # it uses neither the pinned table nor the LRU
        assert counters["rejected"] > 0 and counters["pinned_hits"] > 0
        assert counters["evictions"] > 0


def test_pinned_lifts_survive_a_one_entry_lru():
    case = make_case(n=8)
    settings = prototype.Settings(max_cache_entries=1, max_cache_terms=100)
    lru = checked(case, "canonical_cache", settings=settings)["metrics"]
    pinned = checked(case, "canonical_precompute", settings=settings)["metrics"]
    assert lru["lift_hits"] == 0
    assert pinned["pinned_hits"] > 0 and pinned["pinned_rejected"] == 0
    assert pinned["lift_misses"] + pinned["pinned_misses"] < lru["lift_misses"]


def test_lazy_pinning_never_lifts_an_everywhere_invariant_predicate():
    case = make_case("invariant_dense", n=24, k=16)
    for method in prototype.REUSE_METHODS:
        result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                               method=method)
        assert result["status"] == "equivalent"
        assert result["metrics"]["pinned_misses"] == 0 and result["metrics"]["lift_misses"] == 0


class _Exhausted(Exception):
    pass


@pytest.mark.parametrize("method", prototype.REUSE_METHODS)
@pytest.mark.parametrize("spec", ({"n": 3, "k": 3}, {"family": "perturbed", "n": 4, "k": 4},
                                  {"n": 4, "presentation": "nonlinear"}))
def test_exhaustion_at_every_accounting_point_is_inconclusive(monkeypatch, method, spec):
    case = make_case(**spec)
    original, calls = core._Work.check, [0]

    def counting(self, count=0):
        calls[0] += 1
        return original(self, count)

    monkeypatch.setattr(core._Work, "check", counting)
    expected = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                             method=method)
    assert expected["status"] == case.expected
    total = calls[0]
    assert total > 50

    for point in range(1, total + 1):
        calls[0] = 0

        def exhausted(self, count=0, _point=point):
            calls[0] += 1
            if calls[0] == _point:
                raise core.ResourceLimitExceeded("terms", 0, count)
            return original(self, count)

        monkeypatch.setattr(core._Work, "check", exhausted)
        result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                               method=method)
        assert result["status"] == "inconclusive" and result["receipt"] is None, point
        assert result["witness"] is None


@pytest.mark.parametrize("method", prototype.METHODS)
def test_fibre_constant_phase_that_is_not_identically_zero(method):
    # c[p] + c[p + q] - 2c[p (1 + q)] = c[q] with q measured: no whole-phase cancellation.
    for case in (make_case("fibre_constant", n=4, k=3),
                 make_case("fibre_constant", n=5, k=4, mixed_support=True, seed=2, scale=3)):
        result = checked(case, method)
        assert result["status"] == "equivalent"
        if method == "canonical_factorized":
            assert result["metrics"]["factorized_terms"] > 0
