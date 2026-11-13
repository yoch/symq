"""Term and time budgets apply inside arithmetic, before subsequent cancellation."""
import random
import time

import pytest

from symq import ANF, Budget, ResourceLimitExceeded
from symq.phase import PhaseProgram, _product, check_phase_equivalence, phase_semantics
from symq.resources import Guard
from symq.verification import verify_explicit


@pytest.mark.parametrize("kind", ["mcx", "mcz", "mcz_if"])
def test_zero_final_factor_cannot_hide_an_oversized_intermediate(kind):
    # Every stored wire has at most two terms. The controls first build
    # (1+x0)(1+x1), with four terms, before the zero ancilla cancels everything.
    program = PhaseProgram(3, 1).x(0).x(1)
    if kind == "mcx":
        program.mcx(0, 1, 3, 2)
    elif kind == "mcz":
        program.mcz(0, 1, 3)
    else:
        outcome = program.hmr(3)
        program.mcz_if(outcome, 0, 1, 3)
    assert check_phase_equivalence(program, program).equivalent
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        phase_semantics(program, budget=Budget(max_terms=2))
    result = verify_explicit(program, program, theorem="sign_phase_exact",
                             engine="phase-reference", budget=Budget(max_terms=2))
    assert result.outcome == "inconclusive"
    assert result.witness is None and not result.certified


def test_cancellation_inside_one_binary_product_still_checks_the_peak():
    # (1+x)(1+xy) = 1+x, but the sparse accumulator visits {1,x,xy}.
    # Checking only after ANF.__mul__ returns would miss this three-term set.
    program = (PhaseProgram(2, 1).ccx(0, 1, 2).x(2).x(0).cz(0, 2)
               .x(0).x(2).ccx(0, 1, 2))
    unlimited = phase_semantics(program)
    assert unlimited.phase == ANF.constant(1) ^ ANF.variable(0)
    assert not unlimited.violations()
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        phase_semantics(program, budget=Budget(max_terms=2))
    assert phase_semantics(program, budget=Budget(max_terms=3)) == unlimited


def test_deadline_is_polled_inside_a_single_binary_product(monkeypatch):
    ticks = iter(range(1000))
    monkeypatch.setattr(time, "perf_counter", lambda: next(ticks))
    guard = Guard(Budget(max_seconds=2))
    left = ANF(frozenset(range(64)))
    right = ANF(frozenset(mask << 6 for mask in range(64)))
    # With only factor-boundary polling this 4096-pair multiplication finishes
    # before the synthetic clock reaches its deadline. Periodic polling must stop it.
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        _product([left, right], guard)


@pytest.mark.parametrize("seed", range(24))
def test_bounded_products_match_boolean_evaluation(seed):
    rng = random.Random(seed)
    factors = [ANF(frozenset(mask for mask in range(8) if rng.randrange(2)))
               for _ in range(rng.randrange(6))]
    product = _product(factors, Guard(Budget(max_terms=8)))
    for assignment in range(8):
        expected = int(all(factor.evaluate(assignment) for factor in factors))
        assert product.evaluate(assignment) == expected


def test_product_boundary_values():
    guard = Guard(Budget(max_terms=1))
    assert _product([], guard) == ANF.constant(1)
    assert _product([ANF()], guard) == ANF()
    assert _product([ANF.variable(0), ANF.variable(1)], guard) == ANF(frozenset({3}))


def _record_anf_sizes(monkeypatch):
    sizes = []
    original = ANF.__post_init__

    def record_size(self):
        original(self)
        sizes.append(len(self.terms))

    monkeypatch.setattr(ANF, "__post_init__", record_size)
    return sizes


def test_phase_difference_is_decided_without_materializing_it(monkeypatch):
    # Each phase has one term, within max_terms=1; their two-term difference is only
    # inspected (emptiness, equality with 1, minimal monomial), never stored.
    left, right = PhaseProgram(2).z(0), PhaseProgram(2).z(1)
    for program in (left, right):
        assert len(phase_semantics(program, budget=Budget(max_terms=1)).phase.terms) == 1
    sizes = _record_anf_sizes(monkeypatch)
    assert check_phase_equivalence(left, right, budget=Budget(max_terms=1)).witness == 1
    assert sizes and max(sizes) <= 1
    record = verify_explicit(left, right, theorem="sign_phase_exact", engine="phase-reference",
                             budget=Budget(max_terms=1))
    assert record.outcome == "different" and record.witness == 1


def test_global_sign_is_recognized_at_the_term_limit():
    # Phases 1+x0 and x0 fit max_terms=2; their difference is exactly the constant 1.
    left, right = PhaseProgram(1).x(0).z(0).x(0), PhaseProgram(1).z(0)
    result = check_phase_equivalence(left, right, budget=Budget(max_terms=2))
    assert result.up_to_global_phase and not result.equivalent


def test_disjoint_in_budget_phases_stay_decisive():
    # Six disjoint monomials per side: max_terms=6 bounds each phase but not their
    # twelve-term difference, which the comparison never builds.
    left, right = PhaseProgram(8), PhaseProgram(8)
    for a, b in ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3)):
        left.cz(a, b)
    for a, b in ((0, 4), (1, 5), (2, 6), (3, 7), (0, 6), (1, 7)):
        right.cz(a, b)
    unlimited = check_phase_equivalence(left, right)
    bounded = check_phase_equivalence(left, right, budget=Budget(max_terms=6))
    assert bounded == unlimited and bounded.witness is not None


def _random_program(rng, data):
    program = PhaseProgram(data, 1)
    for _ in range(rng.randrange(1, 7)):
        kind = rng.choice(["x", "cx", "ccx", "z", "cz"])
        wires = rng.sample(range(data), {"x": 1, "z": 1, "cx": 2, "cz": 2, "ccx": 3}[kind])
        getattr(program, kind)(*wires)
    return program


def _reference_equivalence(left, right):
    """The pre-budget comparison: materialize the differences with plain ANF arithmetic."""
    a, b = phase_semantics(left), phase_semantics(right)
    for wire in range(left.data):
        if a.outputs[wire] != b.outputs[wire]:
            difference = a.outputs[wire] ^ b.outputs[wire]
            return False, False, min(difference.terms, key=lambda m: (m.bit_count(), m))
    difference = a.phase ^ b.phase
    if not difference.terms:
        return True, True, None
    if difference == ANF.constant(1):
        return False, True, None
    return False, False, min(difference.terms, key=lambda m: (m.bit_count(), m))


@pytest.mark.parametrize("seed", range(60))
def test_budgeted_comparison_matches_the_unbudgeted_reference(seed):
    rng = random.Random(seed)
    left, right = _random_program(rng, 3), _random_program(rng, 3)
    expected = _reference_equivalence(left, right)
    for limit in (1, 2, 3, 4, 8, None):
        try:
            result = check_phase_equivalence(left, right, budget=Budget(max_terms=limit))
        except ResourceLimitExceeded:
            # Only a stored wire, phase or intermediate product may exceed the bound.
            assert limit is not None
            continue
        assert (result.equivalent, result.up_to_global_phase, result.witness) == expected


def test_output_difference_is_decided_when_each_output_has_one_term(monkeypatch):
    # Swap using an ancilla and corrected HMR, keeping every wire/phase at <=1 term.
    # The comparison with identity still needs the two-term difference x0+x1.
    swap = PhaseProgram(2, 1).cx(0, 2)
    swap.z_if(swap.hmr(0), 2).cx(1, 0)
    swap.z_if(swap.hmr(1), 0).cx(2, 1)
    swap.z_if(swap.hmr(2), 1)
    semantics = phase_semantics(swap, budget=Budget(max_terms=1))
    assert not semantics.violations()
    assert semantics.outputs[:2] == (ANF.variable(1), ANF.variable(0))
    sizes = _record_anf_sizes(monkeypatch)
    assert check_phase_equivalence(PhaseProgram(2), swap, budget=Budget(max_terms=1)).witness == 1
    assert sizes and max(sizes) <= 1
    record = verify_explicit(PhaseProgram(2), swap, theorem="sign_phase_exact",
                             engine="phase-reference", budget=Budget(max_terms=1))
    assert record.outcome == "different" and record.witness == 1


@pytest.mark.parametrize("program", [PhaseProgram(2).cx(0, 1), PhaseProgram(2).z(0).z(1)])
def test_gate_xor_checks_before_materializing_an_oversized_anf(monkeypatch, program):
    sizes = _record_anf_sizes(monkeypatch)
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        phase_semantics(program, budget=Budget(max_terms=1))
    assert sizes and max(sizes) <= 1


def test_deadline_is_polled_while_streaming_a_difference(monkeypatch):
    from symq.phase import _min_difference_monomial

    ticks = iter(range(1000))
    monkeypatch.setattr(time, "perf_counter", lambda: next(ticks))
    guard = Guard(Budget(max_seconds=2))
    left, right = ANF(frozenset(range(4096))), ANF(frozenset(range(4096, 8192)))
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        _min_difference_monomial(left, right, guard)


def test_xor_above_the_bound_is_refused_before_materialization(monkeypatch):
    from symq.phase import _xor

    left, right = ANF(frozenset(range(4))), ANF(frozenset(range(2, 8)))
    sizes = _record_anf_sizes(monkeypatch)
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        _xor(left, right, Guard(Budget(max_terms=5)))
    assert sizes == []
    assert _xor(left, right, Guard(Budget(max_terms=6))).terms == frozenset({0, 1, 4, 5, 6, 7})


def test_constant_plus_variable_difference_is_not_a_global_sign():
    # Phase 1+x0 against the empty phase: the difference contains 1 but is not 1.
    left, right = PhaseProgram(1).x(0).z(0).x(0), PhaseProgram(1)
    for limit in (2, None):
        result = check_phase_equivalence(left, right, budget=Budget(max_terms=limit))
        assert not result.up_to_global_phase and not result.equivalent
        assert result.witness == 0


def test_clock_is_read_periodically_inside_one_product(monkeypatch):
    from symq.phase import _POLL

    calls = []
    real = time.perf_counter
    monkeypatch.setattr(time, "perf_counter", lambda: calls.append(1) or real())
    guard = Guard(Budget(max_seconds=600))
    left = ANF(frozenset(range(64)))
    right = ANF(frozenset(mask << 6 for mask in range(64)))
    before = len(calls)
    _product([left, right], guard)
    # Factor boundaries alone read the clock three times; the 4096 pairs add four polls.
    assert len(calls) - before >= 3 + (64 + 64 * 64) // _POLL
