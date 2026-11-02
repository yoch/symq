"""Independent finite-oracle, hostile-certificate and non-completeness checks."""
from __future__ import annotations

import random
from fractions import Fraction
from itertools import product

import pytest

from benchmarks.phase_factored import MATRICES, VALUES, mixed_family, recheck, small_mixed
from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
from symq.labs import kraus_graph, phase_discovery, phase_factored
from symq.labs.affine_phase import AffineSupport
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.nonlinear_phase_bits import check_nonlinear_phase
from symq.labs.phase_factored import (
    _evaluate, _freeze_certificate, _linear_source, _recover, _span,
    check_factored_phase, discover_factored_phase,
)
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard, VerificationSession
from tests.testkit.affine_phase_oracle import same_channel


def test_affine_span_recovery_against_exhaustive_small_linear_combinations():
    rng = random.Random(16611)
    for width in range(1, 5):
        for _ in range(40):
            signature = [frozenset(m for m in range(1 << width) if rng.randrange(4) == 0)
                         for _ in range(4)]
            guard = Guard(Budget(max_seconds=5))
            basis = _span(signature, guard)
            reachable = {_linear_source(form, signature, guard) for form in range(1 << 5)}
            for monomial in range(1 << width):
                poly = frozenset((monomial,))
                answer = _recover(poly, basis, guard)
                assert (answer is not None) == (poly in reachable)
                if answer is not None:
                    assert _linear_source(answer, signature, guard) == poly


def test_factored_arithmetic_and_empty_product_semantics():
    rng = random.Random(16612)
    guard = Guard(Budget(max_seconds=10))
    for width in range(5):
        for _ in range(30):
            certificate = tuple((rng.randrange(8), tuple(
                tuple(rng.randrange(1 << (width + 1)) for _ in range(rng.randrange(4)))
                for _ in range(rng.randrange(4)))) for _ in range(3))
            frozen, _count = _freeze_certificate(certificate, width, 3, guard, 10000)
            assert frozen == certificate
            for word in range(1 << width):
                expected = 0
                for coefficient, products in certificate:
                    parity = False
                    for factors in products:
                        value = True
                        for form in factors:
                            bit = bool(form & 1)
                            for j in range(width):
                                if form >> (j + 1) & 1:
                                    bit ^= bool(word >> j & 1)
                            value &= bit
                        parity ^= value
                    expected += coefficient * parity
                assert _evaluate(certificate, word, guard) == expected
    assert _evaluate(((3, ((),)),), 0, guard) == 3
    assert _evaluate(((3, ()),), 0, guard) == 0


@pytest.mark.sat
def test_all_two_coordinate_affine_mixings_with_independent_channel_oracle():
    for matrix, offset, values in product(MATRICES, range(4), VALUES):
        left, right, d, support = small_mixed(values, matrix, offset)
        answer = discover_factored_phase(left, right, d, support=support)
        assert answer['status'] == 'proved' and answer['fresh_verified']
        assert same_channel(left, right, d, columns=support.columns)
        recheck(left, right, d, support, answer)


@pytest.mark.sat
@pytest.mark.parametrize('degree', (3, 8, 16, 32))
@pytest.mark.parametrize('kind', ('star', 'chain'))
def test_factored_certificate_never_materializes_its_exponential_anf(degree, kind):
    left, right, d, support = mixed_family(degree, kind)
    answer = discover_factored_phase(left, right, d, support=support, max_items=10000)
    assert answer['status'] == 'proved'
    assert len(answer['certificate']) == 1
    coefficient, polynomials = answer['certificate'][0]
    assert coefficient == 1 and len(polynomials) == 1 and len(polynomials[0]) == degree
    assert answer['certificate_items'] < 3 * degree * degree
    recheck(left, right, d, support, answer)
    if degree <= 8:
        # Independent truth-table Moebius transform of the phase as a function of h.
        table = []
        for h in range(1 << degree):
            if kind == 'star':
                last = h >> (degree - 1) & 1
                q = [((h >> i) & 1) ^ last for i in range(degree - 1)] + [last]
            else:
                q = [sum(h >> j & 1 for j in range(i, degree)) % 2 for i in range(degree)]
            table.append(int(all(q)))
        for bit in range(degree):
            for mask in range(1 << degree):
                if mask >> bit & 1:
                    table[mask] ^= table[mask ^ (1 << bit)]
        assert sum(table) == 1 << (degree - 1)


@pytest.mark.sat
def test_structural_failure_is_not_a_difference_and_cancellation_still_checks():
    # h=ab, delta=2a+2(a XOR ab) = 2h mod4. Neither predicate factors separately.
    d = PhaseProgram(3, 1).ccx(0, 1, 3)
    d.hmr(3)
    support = AffineSupport(3, 0, (1, 2))
    left = DyadicPhaseProgram(3, k=2).z(0).cx(0, 2).ccx(0, 1, 2).z(2)
    left.ccx(0, 1, 2).cx(0, 2)
    right = DyadicPhaseProgram(3, k=2)
    missed = discover_factored_phase(left, right, d, support=support)
    assert missed['status'] == 'not_proved' and missed['obligation'] == 'structural_factorization'
    assert missed['witness'] is None and missed['certificate'] is None
    assert check_factored_phase(left, right, d, ((2, ((2,),)),), support=support)['status'] == 'proved'
    assert check_nonlinear_phase(left, right, d, ((), (1,)), support=support)['status'] == 'proved'
    assert same_channel(left, right, d, columns=support.columns)
    wrong = check_factored_phase(left, right, d, (), support=support)
    assert wrong['status'] == 'not_proved' and wrong['obligation'] == 'candidate_value'


@pytest.mark.sat
def test_source_feedback_offsets_and_mutations_are_not_hidden_by_factors():
    left, right, d, _support = small_mixed((0, 1, 2, 3), (1, 2), 0)
    support = AffineSupport(4, 1, (1, 6))
    good = discover_factored_phase(left, right, d, support=support)
    assert good['status'] == 'proved'
    assert same_channel(left, right, d, offset=1, columns=(1, 6))
    d.cz_if(0, 0, 1)  # cancel the first effective signature, not just a slot label
    refused = check_factored_phase(left, right, d, good['certificate'], support=support)
    assert refused['status'] == 'not_proved'
    assert refused['source_sha256'] != good['source_sha256']
    left, right, d, support = small_mixed((0, 1, 2, 3))
    good = discover_factored_phase(left, right, d, support=support)
    left.phase(0, Fraction(1, 4))
    bad = check_factored_phase(left, right, d, good['certificate'], support=support)
    assert bad['status'] == 'not_proved' and not same_channel(left, right, d, columns=support.columns)
    left.x(0)
    assert discover_factored_phase(left, right, d, support=support)['status'] == 'different'


@pytest.mark.sat
def test_source_snapshot_and_proposal_fresh_check_boundaries(monkeypatch):
    left, right, d, support = mixed_family(3)
    real_prepare = phase_discovery._prepare

    def mutate(*args):
        problem = real_prepare(*args)
        left.gates.clear()
        d.ops.clear()
        return problem

    with monkeypatch.context() as context:
        context.setattr(phase_discovery, '_prepare', mutate)
        assert discover_factored_phase(left, right, d, support=support)['status'] == 'proved'
    left, right, d, support = mixed_family(3)
    with monkeypatch.context() as context:
        context.setattr(phase_factored, '_propose', lambda *args: ((), {}))
        with pytest.raises(InternalInconsistency):
            discover_factored_phase(left, right, d, support=support)
    with monkeypatch.context() as context:
        context.setattr(phase_factored, '_fresh', lambda *args: {'status': 'proved'})
        with pytest.raises(InternalInconsistency):
            discover_factored_phase(left, right, d, support=support)
    for status in ('inconclusive', 'unsupported'):
        with monkeypatch.context() as context:
            context.setattr(phase_factored, '_fresh', lambda *args, value=status: {'status': value})
            result = discover_factored_phase(left, right, d, support=support)
            assert result['status'] == status and not result['fresh_verified']
            assert result['certificate'] is None


def test_closed_certificate_resource_and_dependency_refusals(monkeypatch):
    left, right, d, support = small_mixed((0, 1, 2, 3))
    invalid = ([], ((True, ()),), ((-1, ()),), ((4, ()),), ((1, []),),
               ((1, ((True,),)),), ((1, ((-1,),)),), ((1, ((8,),)),))
    for candidate in invalid:
        with pytest.raises(ValueError):
            check_factored_phase(left, right, d, candidate, support=support)
    assert discover_factored_phase(left, right, d, support=support, max_items=1)['status'] == 'inconclusive'
    assert discover_factored_phase(left, right, d, support=support,
                                   budget=Budget(max_seconds=1e-12))['status'] == 'inconclusive'
    with VerificationSession(Budget(max_terms=1)):
        assert discover_factored_phase(left, right, d, support=support)['status'] == 'inconclusive'
    with VerificationSession(Budget(max_bytes=1)), pytest.raises(ValueError):
        discover_factored_phase(left, right, d, support=support)

    def unavailable():
        raise SatUnavailable('injected missing solver')

    monkeypatch.setattr(kraus_graph, '_new_solver', unavailable)
    assert check_factored_phase(left, right, d, (), support=support)['status'] == 'unsupported'


@pytest.mark.sat
def test_deadline_after_fresh_proof_revokes_decisive_result(monkeypatch):
    left, right, d, support = mixed_family(3)
    real_fresh, real_clock = phase_factored._fresh, Guard.check_time
    expired = [False]

    def clock(self):
        if expired[0]:
            raise ResourceLimitExceeded('late expiry', 1, 2)
        return real_clock(self)

    def expire(*args):
        result = real_fresh(*args)
        expired[0] = True
        return result

    monkeypatch.setattr(phase_factored, '_fresh', expire)
    monkeypatch.setattr(Guard, 'check_time', clock)
    result = discover_factored_phase(left, right, d, support=support)
    assert result['status'] == 'inconclusive' and not result['fresh_verified']
    assert result['certificate'] is None and result['witness'] is None
