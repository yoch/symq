"""Portable proof boundary: source binding, solver-free consumers and revoked success."""
from __future__ import annotations

import copy
import hashlib
from fractions import Fraction
from itertools import product

import pytest

from symq.errors import ResourceLimitExceeded
from symq.labs import kraus_graph, lrat_export, lrat_rup, phase_factored, phase_proof_bundle
from symq.labs.phase_proof_bundle import (
    check_factored_proof,
    describe_factored_obligation,
    export_factored_proof,
)
from symq.resources import Budget, Guard, VerificationSession
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import candidate, fixture


def source_case(values=(0, 1, 2, 3)):
    left, right, dephaser, support = fixture(values)
    planes = candidate(values)
    factored = tuple((1 << bit, tuple(tuple(1 << (j + 1) for j in range(2) if mask >> j & 1)
                                     for mask in polynomial))
                     for bit, polynomial in enumerate(planes))
    return left, right, dephaser, factored, support


def consumer(case, bundle, pins, **kwargs):
    left, right, dephaser, factored, support = case
    return check_factored_proof(left, right, dephaser, factored, bundle, support=support,
                                expected_source_sha256=pins['source_sha256'],
                                expected_certificate_sha256=pins['certificate_sha256'], **kwargs)


@pytest.mark.sat
@pytest.mark.parametrize('values', [(0, 1, 2, 3), (3, 2, 0, 1), (0, 0, 0, 1), (3, 3, 3, 3)])
def test_source_bound_proof_and_no_solver_or_search_in_consumer(values, monkeypatch):
    case = source_case(values)
    left, right, dephaser, factored, support = case
    pins = describe_factored_obligation(left, right, dephaser, factored, support=support)
    assert pins['status'] == 'ready' and pins['proved'] is False
    result = export_factored_proof(left, right, dephaser, factored, support=support)
    assert result['status'] == 'proved', result
    assert same_channel(left, right, dephaser, columns=support.columns)

    def forbidden(*args, **kwargs):
        raise AssertionError('portable consumer must not invoke SAT/search or old proof replay')

    monkeypatch.setattr(lrat_export, '_new_solver', forbidden)
    monkeypatch.setattr(kraus_graph.Graph, 'witness', forbidden)
    monkeypatch.setattr(phase_factored, 'check_factored_phase', forbidden)
    checked = consumer(case, result['bundle'], pins)
    assert checked['status'] == 'proved' and checked['independent_unsat_checked']
    assert checked['semantic_kernel_formally_verified'] is False


@pytest.mark.sat
def test_trivial_contradiction_cannot_replace_the_real_source_obligation():
    case = source_case()
    left, right, d, factored, support = case
    pins = describe_factored_obligation(left, right, d, factored, support=support)
    exported = export_factored_proof(left, right, d, factored, support=support)
    assert exported['status'] == 'proved'
    bundle = exported['bundle']
    replacements = {'source_sha256': '0' * 64, 'certificate_sha256': '0' * 64,
                    'cnf_sha256': '0' * 64, 'lrat_sha256': '0' * 64,
                    'encoder': 'other', 'theorem': 'controlled_unitary',
                    'schema_version': True, 'lrat': '', 'kind': 'untrusted'}
    for key, value in replacements.items():
        result = consumer(case, {**bundle, key: value}, pins)
        assert result['status'] == 'invalid' and not result['independent_unsat_checked'], (key, result)
    fake = copy.deepcopy(bundle)
    fake['cnf'] = 'p cnf 1 2\n1 0\n-1 0\n'
    fake['lrat'] = '3 0 1 2 0\n'
    fake['cnf_sha256'] = hashlib.sha256(fake['cnf'].encode()).hexdigest()
    fake['lrat_sha256'] = hashlib.sha256(fake['lrat'].encode()).hexdigest()
    assert lrat_rup.check_lrat(fake['cnf'], fake['lrat'],
                               expected_cnf_sha256=fake['cnf_sha256'])['verified_unsat']
    assert consumer(case, fake, pins)['status'] == 'invalid'
    class StringKey(str):
        pass

    spoofed_keys = {StringKey(key): value for key, value in bundle.items()}
    assert consumer(case, spoofed_keys, pins)['status'] == 'invalid'
    left.phase(0, Fraction(1, 4))
    assert consumer(case, bundle, pins)['status'] == 'invalid'


@pytest.mark.sat
def test_bad_candidate_and_fake_producer_cannot_create_a_bundle(monkeypatch):
    left, right, d, _factored, support = source_case()
    # The two channels ARE equal; a false supplied certificate is not a difference verdict.
    assert same_channel(left, right, d, columns=support.columns)
    result = export_factored_proof(left, right, d, (), support=support)
    assert result['status'] == 'not_proved' and result['bundle'] is None
    monkeypatch.setattr(lrat_export, 'prove_cnf',
                        lambda *args, **kwargs: {'status': 'proof_checked', 'lrat': ''})
    result = export_factored_proof(left, right, d, (), support=support)
    assert result['status'] != 'proved' and result['bundle'] is None
    assert not result['independent_unsat_checked']


@pytest.mark.sat
def test_deadline_rejection_after_inner_kernel_success_clears_proof_fields(monkeypatch):
    case = source_case()
    left, right, d, factored, support = case
    pins = describe_factored_obligation(left, right, d, factored, support=support)
    bundle = export_factored_proof(left, right, d, factored, support=support)['bundle']
    original, clock = lrat_rup.check_lrat, Guard.check_time
    expired = [False]

    def late(self):
        if expired[0]:
            raise ResourceLimitExceeded('after independent check', 1, 2)
        return clock(self)

    def check_then_expire(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result['status'] == 'verified_unsat'
        expired[0] = True
        return result

    monkeypatch.setattr(Guard, 'check_time', late)
    monkeypatch.setattr(lrat_rup, 'check_lrat', check_then_expire)
    result = consumer(case, bundle, pins)
    assert result['status'] == 'inconclusive' and not result['independent_unsat_checked']
    assert 'checked_steps' not in result and 'lrat_sha256' not in result


def test_explicit_and_inherited_limits_before_preparation():
    left, right, d, factored, support = source_case()
    result = describe_factored_obligation(left, right, d, factored, support=support,
                                          limits=lrat_rup.Limits(max_seconds=1e-12))
    assert result['status'] == 'inconclusive' and not result['proved']
    with VerificationSession(Budget(max_bytes=1)), pytest.raises(ValueError):
        describe_factored_obligation(left, right, d, factored, support=support)
    with VerificationSession(Budget(max_terms=1)):
        assert describe_factored_obligation(left, right, d, factored, support=support)['status'] == 'inconclusive'


def test_new_tseitin_encoder_matches_every_signed_gate_truth_table():
    for operator in ('mul', 'xor'):
        for sa, sb in product((-1, 1), repeat=2):
            guard = Guard(Budget(max_seconds=5))
            graph = kraus_graph.Graph(guard)
            a, b = graph.var(0), graph.var(1)
            root = getattr(graph, operator)(sa * a, sb * b)
            cnf = phase_proof_bundle._encode_graph(graph, root, guard, lrat_rup.Limits())
            nv, clauses = lrat_rup.parse_dimacs(cnf, lrat_rup.Meter(lrat_rup.Limits()))
            for x in range(4):
                completions = 0
                for full in range(1 << nv):
                    if bool(full >> (a - 1) & 1) != bool(x & 1):
                        continue
                    if bool(full >> (b - 1) & 1) != bool(x >> 1 & 1):
                        continue
                    satisfied = all(any(bool(full >> (abs(lit) - 1) & 1) == (lit > 0)
                                        for lit in clause) for clause in clauses)
                    completions += satisfied
                assert completions == int(graph.evaluate(root, x))
