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
    guard = Guard(Budget(max_seconds=30))
    left = ANF(frozenset(range(16)))
    right = ANF(frozenset(mask << 4 for mask in range(16)))
    # With only factor-boundary polling this 256-pair multiplication finishes
    # before the synthetic clock reaches its deadline. Pair polling must stop it.
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


def test_phase_difference_obeys_the_same_term_limit_as_each_program():
    left, right = PhaseProgram(2).z(0), PhaseProgram(2).z(1)
    for program in (left, right):
        assert len(phase_semantics(program, budget=Budget(max_terms=1)).phase.terms) == 1
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        check_phase_equivalence(left, right, budget=Budget(max_terms=1))
    record = verify_explicit(left, right, theorem="sign_phase_exact", engine="phase-reference",
                             budget=Budget(max_terms=1))
    assert record.outcome == "inconclusive" and record.witness is None
    assert check_phase_equivalence(left, right, budget=Budget(max_terms=2)).witness == 1


def test_output_difference_is_bounded_even_when_each_output_has_one_term():
    # Swap using an ancilla and corrected HMR, keeping every wire/phase at <=1 term.
    # The comparison with identity still needs the two-term difference x0+x1.
    swap = PhaseProgram(2, 1).cx(0, 2)
    swap.z_if(swap.hmr(0), 2).cx(1, 0)
    swap.z_if(swap.hmr(1), 0).cx(2, 1)
    swap.z_if(swap.hmr(2), 1)
    semantics = phase_semantics(swap, budget=Budget(max_terms=1))
    assert not semantics.violations()
    assert semantics.outputs[:2] == (ANF.variable(1), ANF.variable(0))
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        check_phase_equivalence(PhaseProgram(2), swap, budget=Budget(max_terms=1))
    record = verify_explicit(PhaseProgram(2), swap, theorem="sign_phase_exact",
                             engine="phase-reference", budget=Budget(max_terms=1))
    assert record.outcome == "inconclusive" and record.witness is None
    assert check_phase_equivalence(PhaseProgram(2), swap, budget=Budget(max_terms=2)).witness == 1


@pytest.mark.parametrize("program", [PhaseProgram(2).cx(0, 1), PhaseProgram(2).z(0).z(1)])
def test_gate_xor_checks_before_materializing_an_oversized_anf(monkeypatch, program):
    sizes = []
    original = ANF.__post_init__

    def record_size(self):
        original(self)
        sizes.append(len(self.terms))

    monkeypatch.setattr(ANF, "__post_init__", record_size)
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        phase_semantics(program, budget=Budget(max_terms=1))
    assert sizes and max(sizes) <= 1


def test_deadline_is_polled_during_xor_construction(monkeypatch):
    from symq.phase import _xor

    ticks = iter(range(1000))
    monkeypatch.setattr(time, "perf_counter", lambda: next(ticks))
    guard = Guard(Budget(max_seconds=20))
    left, right = ANF(frozenset(range(64))), ANF(frozenset(range(64, 128)))
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        _xor(left, right, guard)
