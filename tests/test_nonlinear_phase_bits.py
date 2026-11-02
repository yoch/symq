"""Actual source certificates: nonlinear signature, aggregate carries, exact oracle."""
from __future__ import annotations

import random
from fractions import Fraction
from itertools import product

import pytest

from symq.labs import affine_phase as core
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.kraus_graph import Graph
from symq.labs.nonlinear_phase_bits import _phase_bits, check_nonlinear_phase
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard, VerificationSession
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import candidate, fixture


def test_bit_accumulator_matches_scalar_modular_arithmetic():
    rng = random.Random(712)
    for k in range(1, 9):
        for _ in range(60):
            phase = {frozenset(m for m in range(8) if rng.randrange(2)): rng.randrange(1 << k)
                     for _ in range(5)}
            graph = Graph(Guard(Budget(max_seconds=5)))
            bits = _phase_bits(phase, [graph.var(j) for j in range(3)], k, graph)
            for x in range(8):
                expected = sum(c * (sum(m & x == m for m in p) % 2)
                               for p, c in phase.items()) % (1 << k)
                observed = sum(int(graph.evaluate(b, x)) << j for j, b in enumerate(bits))
                assert observed == expected


@pytest.mark.sat
def test_every_two_signature_function_mod_four_without_modular_lifting(monkeypatch):
    def forbidden_lift(*args):
        raise AssertionError('aggregate certificate must not use integer polynomial lifting')

    monkeypatch.setattr(core, '_lift', forbidden_lift)
    for values in product(range(4), repeat=4):
        left, right, dephaser, support = fixture(values)
        result = check_nonlinear_phase(left, right, dephaser, candidate(values), support=support)
        assert result['status'] == 'proved', (values, result)
        assert result['checked_bits'] == 2
        assert same_channel(left, right, dephaser, columns=support.columns)


@pytest.mark.sat
def test_cancellation_across_predicates_is_preserved():
    dephaser = PhaseProgram(3, 1).ccx(0, 1, 3)
    dephaser.hmr(3)
    support = core.AffineSupport(3, 0, (1, 2))
    left = DyadicPhaseProgram(3, k=2).z(0).cx(0, 2).ccx(0, 1, 2).z(2)
    left.ccx(0, 1, 2).cx(0, 2)
    right = DyadicPhaseProgram(3, k=2)
    result = check_nonlinear_phase(left, right, dephaser, ((), (1,)), support=support)
    assert result['status'] == 'proved'
    assert same_channel(left, right, dephaser, columns=support.columns)
    assert core.check_affine_phase(left, right, dephaser, support=support).status == 'not_proved'


@pytest.mark.sat
def test_wrong_certificate_is_not_inequivalence_and_mutated_sources_are_bound():
    left, right, d, support = fixture()
    cert = candidate((0, 1, 2, 3))
    good = check_nonlinear_phase(left, right, d, cert, support=support)
    wrong = check_nonlinear_phase(left, right, d, ((), ()), support=support)
    assert wrong['status'] == 'not_proved' and wrong['obligation'] == 'candidate_phase_bit'
    assert same_channel(left, right, d, columns=support.columns)
    left.phase(0, Fraction(1, 4))
    changed = check_nonlinear_phase(left, right, d, cert, support=support)
    assert changed['status'] == 'not_proved'
    assert changed['source_sha256'] != good['source_sha256']
    assert not same_channel(left, right, d, columns=support.columns)
    left, right, d, support = fixture((0, 1, 0, 1))
    d.cz_if(0, 0, 1)
    assert check_nonlinear_phase(left, right, d, candidate((0, 1, 0, 1)),
                                 support=support)['status'] == 'not_proved'
    assert not same_channel(left, right, d, columns=support.columns)


@pytest.mark.sat
def test_output_obligation_and_mixed_precision_are_separate():
    left, right, d, support = fixture((0, 0, 0, 0))
    left.x(0)
    refused = check_nonlinear_phase(left, right, d, ((), ()), support=support)
    assert refused['status'] == 'not_proved' and refused['obligation'] == 'outputs'
    left = DyadicPhaseProgram(2, k=3).phase(0, Fraction(-1, 8))
    right = DyadicPhaseProgram(2, k=4).phase(0, Fraction(7, 8)).phase(1, 2)
    assert check_nonlinear_phase(left, right, PhaseProgram(2), ((),) * 4)['status'] == 'proved'


@pytest.mark.sat
def test_closed_certificate_and_shared_budgets():
    left, right, d, support = fixture()
    for invalid in ([], ((),), ((True,), ()), ((1, 1), ()), ((4,), ())):
        with pytest.raises(ValueError):
            check_nonlinear_phase(left, right, d, invalid, support=support)
    with VerificationSession(Budget(max_terms=1)):
        assert check_nonlinear_phase(left, right, d, candidate((0, 1, 2, 3)),
                                     support=support)['status'] == 'inconclusive'
    with VerificationSession(Budget(max_bytes=1)), pytest.raises(ValueError):
        check_nonlinear_phase(left, right, d, candidate((0, 1, 2, 3)), support=support)
    assert check_nonlinear_phase(left, right, d, candidate((0, 1, 2, 3)), support=support,
                                 budget=Budget(max_seconds=1e-12))['status'] == 'inconclusive'
