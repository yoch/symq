"""Untrusted DRUP-to-positive-LRAT elaboration and fresh proof-logging SAT producer.

All positive output must pass lrat_rup, which imports none of this module.
Deletion instructions are validated but ignored: retaining more implied clauses
cannot invalidate a RUP derivation. General RAT-only additions are not supported.
"""
from __future__ import annotations

import hashlib
import time
from threading import Timer

from symq.labs import lrat_rup as kernel


class NonRupProof(ValueError):
    """A returned trace cannot be elaborated within the supported proof system."""


def _rup_hints(database, clause, meter):
    # Deliberately a clause-searching producer, separate from the ordered-hint kernel.
    values = {abs(literal): literal < 0 for literal in clause}
    hints = []
    while True:
        progress = False
        for identifier, row in enumerate(database, 1):
            meter.tick()
            satisfied = False
            unknown = []
            for literal in row:
                meter.tick()
                truth = values.get(abs(literal))
                if truth is None:
                    unknown.append(literal)
                elif truth == (literal > 0):
                    satisfied = True
                    break
            if satisfied:
                continue
            if not unknown:
                return hints + [identifier]
            if len(unknown) == 1:
                literal = unknown[0]
                values[abs(literal)] = literal > 0
                hints.append(identifier)
                progress = True
        if not progress:
            return None


def elaborate_drup(cnf: str, drup: list[str], *, limits: kernel.Limits | None = None,
                   absolute_deadline: float | None = None) -> str:
    """Propose a standard positive-hint LRAT trace; caller must check it independently."""
    meter = kernel.Meter(kernel.Limits() if limits is None else limits, absolute_deadline)
    variables, initial = kernel.parse_dimacs(cnf, meter)
    if type(drup) is not list:
        raise NonRupProof('proof logging did not return an exact list')
    if len(drup) > meter.limits.max_steps:
        raise kernel.ProofLimit('raw trace step limit')
    database = list(initial)
    lines = []
    size = 0
    consumed = 0
    finished = False
    for raw in drup:
        meter.text(raw)
        consumed += len(raw)
        if consumed > meter.limits.max_bytes:
            raise kernel.ProofLimit('raw trace byte limit')
        words = raw.split()
        if not words:
            raise NonRupProof('empty raw trace instruction')
        deletion = words[0] == 'd'
        tokens = [kernel._integer(token, meter) for token in words[int(deletion):]]
        if not tokens or tokens[-1] != 0 or 0 in tokens[:-1]:
            raise NonRupProof('malformed raw trace clause')
        clause = kernel._clause(tokens[:-1], variables, meter)
        if deletion:
            continue
        if finished:
            raise NonRupProof('raw addition after final contradiction')
        hints = _rup_hints(database, clause, meter)
        if hints is None:
            raise NonRupProof('trace addition is not RUP; general RAT is unsupported')
        identifier = len(database) + 1
        line = f'{identifier} ' + ' '.join(map(str, clause)) + ' 0 ' + ' '.join(map(str, hints)) + ' 0\n'
        size += len(line)
        if size > meter.limits.max_bytes or len(database) >= meter.limits.max_clauses:
            raise kernel.ProofLimit('elaborated proof size limit')
        lines.append(line)
        database.append(clause)
        finished = not clause
    if not finished:
        # Solvers may report no learned clauses when loading the CNF already
        # finds a unit conflict. Derive this step rather than trusting UNSAT.
        hints = _rup_hints(database, (), meter)
        if hints is None:
            raise NonRupProof('trace does not derive the empty clause')
        line = f'{len(database) + 1} 0 ' + ' '.join(map(str, hints)) + ' 0\n'
        size += len(line)
        if size > meter.limits.max_bytes or len(database) >= meter.limits.max_clauses:
            raise kernel.ProofLimit('final proof size limit')
        lines.append(line)
    proof = ''.join(lines)
    meter.tick()
    return proof


def _new_solver():
    from symq.errors import SatUnavailable

    try:
        from pysat.solvers import Glucose4
    except ImportError as error:
        raise SatUnavailable('python-sat is needed only for proof generation') from error
    return Glucose4(with_proof=True)


def prove_cnf(cnf: str, *, budget=None, limits: kernel.Limits | None = None) -> dict:
    """Solve a fresh formula with ALL assumptions already present as CNF clauses.

    UNSAT is not exposed as success until LRAT checking succeeds. No incremental
    assumption proof, stale learned clauses or unlogged preprocessing is accepted.
    Proof preparation, solve, extraction, conversion, checking and cleanup share
    the caller deadline. Size/time limits are cooperative, not an OS memory cap.
    """
    from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
    from symq.resources import Budget, Guard, intersect_budgets

    bounds = kernel.Limits() if limits is None else limits
    if type(bounds) is not kernel.Limits:
        raise TypeError('exact Limits required')
    bounds.validate()
    if budget is not None and type(budget) is not Budget:
        raise TypeError('Budget or None required')
    guard = Guard(intersect_budgets(Budget(max_seconds=bounds.max_seconds), budget or Budget()))
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError('node/byte session limits unsupported; use explicit proof Limits')
    meter = kernel.Meter(bounds, guard.deadline)
    result = {'status': 'inconclusive', 'independent_unsat_checked': False}
    solver = timer = None
    started = time.perf_counter()
    try:
        variables, clauses = kernel.parse_dimacs(cnf, meter)
        guard.check_terms(sum(len(c) + 1 for c in clauses))
        digest = hashlib.sha256(cnf.encode('ascii')).hexdigest()
        solver = _new_solver()
        for clause in clauses:
            guard.check_time()
            solver.add_clause(clause)
        guard.check_time()
        solver.clear_interrupt()
        remaining = guard.deadline - time.perf_counter()
        if remaining <= 0:
            raise kernel.ProofLimit('SAT deadline')
        timer = Timer(remaining, solver.interrupt)
        timer.daemon = True
        timer.start()
        answer = solver.solve_limited(expect_interrupt=True)
        guard.check_time()
        if answer is True:
            raw = solver.get_model()
            if type(raw) is not list:
                raise InternalInconsistency('SAT answer without model')
            assignment = {}
            for literal in raw:
                meter.tick()
                if type(literal) is not int or literal == 0 or abs(literal) > variables:
                    raise InternalInconsistency('invalid SAT model literal')
                if abs(literal) in assignment and assignment[abs(literal)] != (literal > 0):
                    raise InternalInconsistency('conflicting SAT model')
                assignment[abs(literal)] = literal > 0
            for clause in clauses:
                meter.tick(len(clause) + 1)
                if not any(assignment.get(abs(lit), False) == (lit > 0) for lit in clause):
                    raise InternalInconsistency('SAT model fails literal formula replay')
            result.update(status='satisfiable', model=sorted((v if b else -v) for v, b in assignment.items()),
                          cnf_sha256=digest)
        elif answer is False:
            raw_proof = solver.get_proof()
            guard.check_time()
            if raw_proof is None:
                raise NonRupProof('UNSAT without a proof log')
            proof = elaborate_drup(cnf, raw_proof, limits=bounds, absolute_deadline=guard.deadline)
            guard.check_terms(sum(len(c) + 1 for c in clauses) + len(proof.split()))
            checked = kernel.check_lrat(cnf, proof, expected_cnf_sha256=digest,
                                        limits=bounds, absolute_deadline=guard.deadline)
            if checked['status'] == 'inconclusive':
                raise kernel.ProofLimit(checked.get('reason', 'proof check incomplete'))
            if checked['status'] != 'verified_unsat' or not checked['verified_unsat']:
                raise NonRupProof('independent kernel rejected the elaborated proof')
            result.update(status='proof_checked', lrat=proof, cnf_sha256=digest,
                          lrat_sha256=checked['lrat_sha256'], independent_unsat_checked=True,
                          proof_steps=checked['steps'], kernel_visits=checked['visits'])
        else:
            result.update(reason='SAT returned unknown or was interrupted')
    except (kernel.ProofLimit, ResourceLimitExceeded) as error:
        result = {'status': 'inconclusive', 'reason': str(error), 'independent_unsat_checked': False}
    except (kernel.InvalidProof, NonRupProof) as error:
        result = {'status': 'proof_rejected', 'reason': str(error), 'independent_unsat_checked': False}
    except SatUnavailable as error:
        result = {'status': 'unsupported', 'reason': str(error), 'independent_unsat_checked': False}
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        if solver is not None:
            solver.delete()
    try:
        guard.check_time()
        meter.tick()
    except (kernel.ProofLimit, ResourceLimitExceeded) as error:
        result = {'status': 'inconclusive', 'reason': str(error), 'independent_unsat_checked': False}
    result['seconds'] = time.perf_counter() - started
    return result
