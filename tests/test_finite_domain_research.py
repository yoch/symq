"""Finite-domain phase/outcome coefficients and GF(2) dual certificate tests."""
import itertools
import random

import pytest

from research.bitset_degree3.finite_domain import Domain, OutcomePoly, evaluate_finite
from research.bitset_degree3.linear_certificate import unsat_dual, verify_dual
from symq import Budget, PhaseProgram, ResourceLimitExceeded, UnsupportedOperation
from symq.phase import phase_semantics


def test_nonempty_explicit_domain_and_hash_contract():
    d = Domain(2, 1, (0, 2))
    assert d.sha256 == Domain(2, 1, (0, 2)).sha256
    assert d.sha256 != Domain(2, 0, (0, 2)).sha256
    for invalid in ((), (0, 0), (-1,), (4,), (True,)):
        with pytest.raises(ValueError):
            Domain(2, 1, invalid)


def test_finite_branch_equal_only_on_declared_input_support():
    ref = PhaseProgram(2)
    changed = PhaseProgram(2).cx(0, 1)
    d = Domain(2, 0, (0, 2))  # q0=0; CX acts as identity only here
    assert evaluate_finite(ref, d).same_branches(evaluate_finite(changed, d))
    whole = Domain(2, 0, (0, 1, 2, 3))
    assert not evaluate_finite(ref, whole).same_branches(evaluate_finite(changed, whole))
    with pytest.raises(ValueError, match="domain"):
        evaluate_finite(ref, d).same_branches(evaluate_finite(ref, whole))


@pytest.mark.parametrize("seed", range(25))
def test_exact_small_phase_semantics_including_every_outcome(seed):
    rng = random.Random(seed)
    p = PhaseProgram(3, 1)
    for _ in range(8):
        q = rng.randrange(4)
        kind = rng.choice(("x", "cx", "cz", "hmr", "cz_if"))
        if kind == "x":
            p.x(q)
        elif kind == "cx":
            a, b = rng.sample(range(4), 2)
            p.cx(a, b)
        elif kind == "cz":
            a, b = rng.sample(range(4), 2)
            p.cz(a, b)
        elif kind == "hmr":
            p.hmr(q)
        elif p.measurements:
            a, b = rng.sample(range(4), 2)
            p.cz_if(rng.randrange(p.measurements), a, b)
    domain = Domain(3, 1, (0, 1, 2, 3, 5, 7))
    finite = evaluate_finite(p, domain)
    baseline = phase_semantics(p)
    for point, x in enumerate(domain.points):
        for outcomes in range(1 << p.measurements):
            for q in range(p.width):
                assert finite.outputs[q].evaluate(point, outcomes) == (
                    baseline.outputs[q].evaluate(x | outcomes << p.data)
                )
            assert finite.phase.evaluate(point, outcomes) == (
                baseline.phase.evaluate(x | outcomes << p.data)
            )


def test_large_outcome_count_without_enumeration_and_mutated_correction():
    p = PhaseProgram(2, 1)
    for _ in range(126):
        p.hmr(2)
    d = Domain(2, 1, tuple(range(4)))
    assert evaluate_finite(p, d).events == 126
    original = PhaseProgram(2, 1).ccx(0, 1, 2)
    m = original.hmr(2)
    corrected = PhaseProgram(2, 1, list(original.ops)).cz_if(m, 0, 1)
    d = Domain(2, 1, (0, 1, 2, 3))
    assert not evaluate_finite(original, d).same_branches(evaluate_finite(corrected, d))


def test_degree_and_budget_rejections_do_not_truncate():
    full = 0b1111
    a = OutcomePoly.event(full, 0)
    b = OutcomePoly.event(full, 1)
    with pytest.raises(ResourceLimitExceeded, match="event degree"):
        a.multiply(b, Budget().start(), max_event_degree=1)
    with pytest.raises(ResourceLimitExceeded, match="domain points"):
        evaluate_finite(PhaseProgram(1), Domain(1, 0, (0, 1)), max_points=1)
    with pytest.raises(ResourceLimitExceeded):
        evaluate_finite(PhaseProgram(1), Domain(1, 0, (0, 1)),
                        budget=Budget(max_seconds=1e-12))
    with pytest.raises(ValueError, match="max_nodes"):
        evaluate_finite(PhaseProgram(1), Domain(1, 0, (0,)),
                        budget=Budget(max_nodes=1))
    with pytest.raises(UnsupportedOperation):
        PhaseProgram(1).append("reset", 0)


def test_all_small_affine_unsat_dual_certificates():
    for rows in range(1, 4):
        for columns in itertools.product(range(1 << rows), repeat=2):
            for rhs in range(1 << rows):
                witness = unsat_dual(tuple(columns), rhs, rows)
                satisfiable = any(
                    (sum(c for bit, c in enumerate(columns) if x >> bit & 1) == -1)
                    for x in ()
                )  # no implicit assumption: brute force below
                satisfiable = any(
                    (columns[0] if x & 1 else 0) ^ (columns[1] if x & 2 else 0) == rhs
                    for x in range(4)
                )
                assert (witness is None) == satisfiable
                if witness is not None:
                    assert verify_dual(tuple(columns), rhs, rows, witness)
    with pytest.raises(ValueError):
        verify_dual((4,), 0, 2, 1)
