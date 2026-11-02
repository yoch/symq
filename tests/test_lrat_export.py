"""Solver output is untrusted; conversion and checking are separate algorithms."""
from __future__ import annotations

import hashlib
import random
from typing import ClassVar

import pytest

from symq.errors import InternalInconsistency, ResourceLimitExceeded
from symq.labs import lrat_export as producer
from symq.labs import lrat_rup as kernel
from symq.resources import Budget, Guard, VerificationSession
from tests.test_lrat_rup import dimacs, resolution_trace, satisfying


def check(cnf, proof):
    return kernel.check_lrat(cnf, proof,
                             expected_cnf_sha256=hashlib.sha256(cnf.encode()).hexdigest())


def test_resolution_logs_elaborate_to_independently_checked_rup():
    rng = random.Random(167)
    count = 0
    for _ in range(200):
        clauses = [tuple((i + 1) * rng.choice((-1, 1)) for i in range(4) if rng.randrange(2))
                   for _ in range(rng.randrange(2, 16))]
        cnf = dimacs(4, clauses)
        resolution = resolution_trace(clauses)
        if resolution is None:
            assert satisfying(4, clauses)
            continue
        drup = []
        for line in resolution.splitlines():
            tokens = line.split()
            stop = tokens.index('0')
            drup.append(' '.join(tokens[1:stop + 1]))
        actual = producer.elaborate_drup(cnf, drup)
        assert check(cnf, actual)['verified_unsat']
        count += 1
    assert count > 100


def test_deletions_cannot_create_authority_and_non_rup_refused():
    cnf = dimacs(2, [(1, 2), (-1, 2), (1, -2), (-1, -2)])
    proof = producer.elaborate_drup(cnf, ['d 1 2 0', '2 0', '0'])
    assert check(cnf, proof)['verified_unsat']
    with pytest.raises(producer.NonRupProof):
        producer.elaborate_drup(dimacs(1, [(1,)]), ['-1 0', '0'])
    with pytest.raises(producer.NonRupProof):
        producer.elaborate_drup(dimacs(1, [(1,)]), [])
    # Unit-inconsistent input admits an explicit trace even without learned clauses.
    cnf = dimacs(1, [(1,), (-1,)])
    assert check(cnf, producer.elaborate_drup(cnf, []))['verified_unsat']


@pytest.mark.sat
def test_real_glucose_proof_and_literal_model():
    from pysat.examples.genhard import PHP

    formula = PHP(nof_holes=3)
    cnf = dimacs(formula.nv, formula.clauses)
    result = producer.prove_cnf(cnf)
    assert result['status'] == 'proof_checked', result
    assert check(cnf, result['lrat'])['verified_unsat']
    assert result['proof_steps'] > 1
    sat = producer.prove_cnf(dimacs(2, [(1, 2), (-1, 2)]))
    assert sat['status'] == 'satisfiable' and 2 in sat['model']


class FakeSolver:
    answer = False
    proof: ClassVar = []
    model: ClassVar = [1]

    def add_clause(self, clause):
        pass

    def clear_interrupt(self):
        pass

    def interrupt(self):
        pass

    def delete(self):
        pass

    def solve_limited(self, **kwargs):
        return self.answer

    def get_proof(self):
        return self.proof

    def get_model(self):
        return self.model


def test_fake_unsat_missing_proofs_and_unknown_never_succeed(monkeypatch):
    monkeypatch.setattr(producer, '_new_solver', FakeSolver)
    cnf = dimacs(1, [(1,)])  # SAT; proof must fail despite the malicious solver's UNSAT.
    for proof in ([], ['0'], ['-1 0', '0'], None):
        monkeypatch.setattr(FakeSolver, 'proof', proof)
        result = producer.prove_cnf(cnf)
        assert result['status'] == 'proof_rejected' and not result['independent_unsat_checked']
        assert 'lrat' not in result
    monkeypatch.setattr(FakeSolver, 'answer', None)
    assert producer.prove_cnf(cnf)['status'] == 'inconclusive'
    monkeypatch.setattr(FakeSolver, 'answer', True)
    monkeypatch.setattr(FakeSolver, 'model', [-1])
    with pytest.raises(InternalInconsistency):
        producer.prove_cnf(cnf)


def test_success_revoked_after_solver_cleanup_and_session_limits(monkeypatch):
    cnf = dimacs(1, [(1,), (-1,)])
    monkeypatch.setattr(producer, '_new_solver', FakeSolver)
    monkeypatch.setattr(FakeSolver, 'proof', [])
    expired = [False]
    clock = Guard.check_time

    def late(self):
        if expired[0]:
            raise ResourceLimitExceeded('after cleanup', 1, 2)
        return clock(self)

    monkeypatch.setattr(Guard, 'check_time', late)
    monkeypatch.setattr(FakeSolver, 'delete', lambda self: expired.__setitem__(0, True))
    result = producer.prove_cnf(cnf)
    assert result['status'] == 'inconclusive' and not result['independent_unsat_checked']
    assert 'lrat' not in result and 'cnf_sha256' not in result
    expired[0] = False
    with VerificationSession(Budget(max_bytes=1)), pytest.raises(ValueError):
        producer.prove_cnf(cnf)
    with pytest.raises(TypeError):
        producer.prove_cnf(cnf, budget=0)
