"""Differential, exhaustive and soundness tests for bounded bitset sign/HMR ANF."""
import random

import pytest

from symq import Budget, PhaseProgram, ResourceLimitExceeded
from symq.phase import phase_semantics
from research.bitset_degree3.bitset import Polynomial, Space, evaluate_phase


@pytest.mark.parametrize("n", range(1, 6))
def test_exact_combinadic_roundtrip_every_supported_monomial(n):
    for k in range(5):
        sp = Space.create(n, k)
        seen = set()
        for index in range(sp.capacity):
            mask = sp.mask(index)
            assert sp.index(mask) == index
            seen.add(mask)
        assert len(seen) == sp.capacity


@pytest.mark.parametrize("n", range(1, 6))
def test_all_small_products_against_separate_set_oracle(n):
    sp = Space.create(n, min(3, n))
    rng = random.Random(20261029+n)
    masks = [m for m in range(1 << n) if m.bit_count() <= sp.degree]
    guard = Budget(max_terms=10000).start()
    for _ in range(80):
        aa = [rng.choice(masks) for _ in range(rng.randrange(0, 9))]
        bb = [rng.choice(masks) for _ in range(rng.randrange(0, 9))]
        a, b = Polynomial.from_masks(sp, aa), Polynomial.from_masks(sp, bb)
        lhs, rhs = set(a.masks()), set(b.masks())
        products = [x | y for x in lhs for y in rhs]
        if a.bits == b.bits:
            # The exact identity f^2=f is allowed without an intermediate expansion.
            expected = lhs
        elif any(m.bit_count() > sp.degree for m in products):
            with pytest.raises(ResourceLimitExceeded, match="degree"):
                a.multiply(b, guard)
            continue
        else:
            expected = {m for m in products if products.count(m) % 2}
        actual = set(a.multiply(b, guard).masks())
        assert actual == expected
        for assignment in range(1 << n):
            assert a.multiply(b, guard).evaluate(assignment) == (
                a.evaluate(assignment) & b.evaluate(assignment)
            )


def test_no_silent_degree_truncation_and_term_budget():
    sp = Space.create(4, 3)
    one = Polynomial.from_masks(sp, [1])
    product = Polynomial.from_masks(sp, [2 | 4 | 8])
    with pytest.raises(ResourceLimitExceeded, match="degree"):
        one.multiply(product, Budget().start())
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        Polynomial.from_masks(sp, [1, 2]).xor(
            Polynomial.from_masks(sp, [4]), Budget(max_terms=2).start()
        )
    with pytest.raises(ResourceLimitExceeded, match="capacity"):
        Space.create(150, 3, max_capacity_bits=10000)


@pytest.mark.parametrize("seed", range(40))
def test_restricted_hmr_differential_vs_unbounded_anf(seed):
    rng = random.Random(seed)
    p = PhaseProgram(3, 2)
    for _ in range(8):
        qs = rng.sample(range(5), rng.randint(1, 2))
        kind = rng.choice(("mcx", "mcz", "hmr", "mcz_if"))
        if kind == "mcx":
            p.mcx(*qs)
        elif kind == "mcz":
            p.mcz(*qs)
        elif kind == "hmr":
            p.hmr(rng.randrange(5))
        elif p.measurements:
            p.mcz_if(rng.randrange(p.measurements), *qs)
    normal = phase_semantics(p)
    try:
        packed = evaluate_phase(p, degree=3)
    except ResourceLimitExceeded as ex:
        assert ex.resource == "degree" and ex.observed > 3
        return
    assert tuple(v.to_anf() for v in packed.outputs) == normal.outputs
    assert packed.phase.to_anf() == normal.phase
    assert bool(packed.violations()) == bool(normal.violations())


def test_temporary_and_phase_erasure_and_bad_correction():
    good = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    m = good.hmr(3)
    good.cz_if(m, 0, 1)
    p = evaluate_phase(good)
    assert not p.violations()
    assert not p.phase.bits
    assert not p.outputs[3].bits
    bad = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    bad.hmr(3)
    q = evaluate_phase(bad)
    assert "O2: phase depends on measurement outcomes" in q.violations()


def test_dirty_data_target_and_many_fresh_outcomes():
    p = PhaseProgram(3).ccx(0, 1, 2)
    state = evaluate_phase(p)
    assert state.outputs[2].evaluate(4) == 1
    assert state.outputs[2].evaluate(7) == 0
    large = PhaseProgram(1, 1)
    for _ in range(126):
        large.hmr(1)
    result = evaluate_phase(large, degree=3)
    assert result.measurements == 126
    assert not result.phase.bits
    assert not result.violations()


def test_budget_and_invalid_contracts_fail_closed():
    p = PhaseProgram(2, 1).ccx(0, 1, 2)
    with pytest.raises(ResourceLimitExceeded):
        evaluate_phase(p, budget=Budget(max_seconds=1e-12))
    with pytest.raises(ValueError, match="max_nodes"):
        evaluate_phase(p, budget=Budget(max_nodes=10))
    with pytest.raises(ValueError):
        Space.create(2, 5)
    with pytest.raises(ValueError):
        Polynomial(Space.create(2, 2), -1)
