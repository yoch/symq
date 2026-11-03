"""Exhaustive tiny-CNF soundness, independent resolution proofs and hostile traces."""
from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

# The normal installed test path imports the public module. The local command below
# may import this file by path to demonstrate the kernel needs no SymQ installation.
from symq.labs import lrat_rup as kernel


def digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def dimacs(n, clauses):
    return f'p cnf {n} {len(clauses)}\n' + ''.join(' '.join(map(str, c)) + ' 0\n' for c in clauses)


def satisfying(n, clauses):
    return any(all(any(bool(x >> (abs(lit) - 1) & 1) == (lit > 0) for lit in c)
                   for c in clauses) for x in range(1 << n))


def resolution_trace(clauses):
    """Independent proof builder: binary resolution, not unit-propagation search."""
    database = [frozenset(c) for c in clauses]
    ids = {c: i + 1 for i, c in enumerate(database)}
    if frozenset() in ids:
        return f'{len(database) + 1} 0 {ids[frozenset()]} 0\n'
    proof = []
    while True:
        added = False
        for i, a in enumerate(list(database)):
            for j, b in enumerate(list(database)):
                for pivot in sorted(a):
                    if -pivot not in b:
                        continue
                    c = (a - {pivot}) | (b - {-pivot})
                    if c in ids or any(-lit in c for lit in c):
                        continue
                    database.append(c)
                    ids[c] = len(database)
                    proof.append(f'{len(database)} ' + ' '.join(map(str, sorted(c)))
                                 + f' 0 {i + 1} {j + 1} 0\n')
                    if not c:
                        return ''.join(proof)
                    added = True
        if not added:
            return None


def test_all_cnf_subsets_on_two_variables():
    count = 0
    for n in range(3):
        clauses = [tuple(sign * (i + 1) for i, sign in enumerate(signs) if sign)
                   for signs in itertools.product((0, 1, -1), repeat=n)]
        for subset in range(1 << len(clauses)):
            formula = [c for i, c in enumerate(clauses) if subset >> i & 1]
            cnf = dimacs(n, formula)
            trace = resolution_trace(formula)
            sat = satisfying(n, formula)
            assert (trace is None) == sat
            if trace is not None:
                result = kernel.check_lrat(cnf, trace, expected_cnf_sha256=digest(cnf))
                assert result['verified_unsat'], (formula, trace, result)
            # A naked empty clause/UNSAT label is never sufficient for a SAT input.
            forged = f'{len(formula) + 1} 0 1 0\n'
            check = kernel.check_lrat(cnf, forged, expected_cnf_sha256=digest(cnf))
            assert not sat or check['status'] == 'invalid'
            count += 1
    assert count == 522


def test_real_multi_step_resolution_and_every_single_token_mutation():
    clauses = [(1, 2), (-1, 2), (1, -2), (-1, -2)]
    cnf = dimacs(2, clauses)
    proof = resolution_trace(clauses)
    assert proof and kernel.check_lrat(cnf, proof, expected_cnf_sha256=digest(cnf))['verified_unsat']
    # Not every mutation must fail (some reorderings are alternative proofs).
    # Every accepted mutation still belongs to this truly UNSAT formula.
    for sat_clauses in (clauses[:-1], clauses[1:], []):
        altered_cnf = dimacs(2, sat_clauses)
        assert satisfying(2, sat_clauses)
        assert kernel.check_lrat(altered_cnf, proof,
                                 expected_cnf_sha256=digest(altered_cnf))['status'] == 'invalid'


@pytest.mark.parametrize('proof', [
    '', 'UNSAT', '3 0 0\n', '3 0 3 0\n', '3 0 99 0\n', '3 0 -1 0\n',
    '3 d 1 0\n', '3 1 0 2 0\n', '2 0 1 2 0\n', '3 0 1 2 1 0\n',
    '3 1 1 0 2 0\n', '3 1 -1 0 1 0\n', '3 0 1 2 0\n4 0 3 0\n',
    '3 0 1 2 0\ntrailing', '3 0 1 2 0\n#hidden', '3 0 +1 2 0\n',
    '3 0 01 2 0\n', '3 0 1 2 -0\n', '3 0 1 2 0 0\n', '3 0 ١ 2 0\n',
])
def test_strict_invalid_proof_shapes(proof):
    cnf = 'p cnf 1 2\n1 0\n-1 0\n'
    assert kernel.check_lrat(cnf, proof, expected_cnf_sha256=digest(cnf))['status'] == 'invalid'


@pytest.mark.parametrize('cnf', [
    '', 'p cnf 1 2\n1 0\n', 'p cnf -1 0\n', 'p cnf 1 1\n2 0\n',
    'p cnf 1 1\n1 1 0\n', 'p cnf 1 1\n1 -1 0\n', 'p cnf 1 1\n0 0\n',
    'p cnf 1 1\n1\n0\n', 'p cnf 1 0\np cnf 1 0\n',
])
def test_strict_formula_parser(cnf):
    result = kernel.check_lrat(cnf, '2 0 1 0\n', expected_cnf_sha256=digest(cnf))
    assert result['status'] == 'invalid' and not result['verified_unsat']


def test_pins_and_resource_failure_revoke_all_authority(monkeypatch):
    cnf, proof = 'p cnf 1 2\n1 0\n-1 0\n', '3 0 1 2 0\n'
    assert kernel.check_lrat(cnf, proof, expected_cnf_sha256='0' * 64)['status'] == 'invalid'
    for limits in (kernel.Limits(max_seconds=1e-12), kernel.Limits(max_visits=1),
                   kernel.Limits(max_clauses=2), kernel.Limits(max_bytes=10)):
        result = kernel.check_lrat(cnf, proof, expected_cnf_sha256=digest(cnf), limits=limits)
        assert result['status'] == 'inconclusive' and not result['verified_unsat']
        assert 'cnf_sha256' not in result and 'lrat_sha256' not in result
    clock, ticks = kernel.time.perf_counter, [0]

    def count():
        ticks[0] += 1
        return 0.0

    monkeypatch.setattr(kernel.time, 'perf_counter', count)
    assert kernel.check_lrat(cnf, proof, expected_cnf_sha256=digest(cnf))['verified_unsat']
    total = ticks[0]
    for expiry in range(1, total):
        calls = [0]

        def expire(calls=calls, expiry=expiry):
            calls[0] += 1
            return 0.0 if calls[0] <= expiry else 100.0

        monkeypatch.setattr(kernel.time, 'perf_counter', expire)
        result = kernel.check_lrat(cnf, proof, expected_cnf_sha256=digest(cnf))
        assert result['status'] == 'inconclusive' and not result['verified_unsat']
        assert 'cnf_sha256' not in result
    monkeypatch.setattr(kernel.time, 'perf_counter', clock)


def test_cli_works_under_isolation_without_symq_or_solver(tmp_path):
    cnf, proof = 'p cnf 1 2\n1 0\n-1 0\n', '3 0 1 2 0\n'
    source = Path(kernel.__file__).read_text()
    target = tmp_path / 'isolated_kernel.py'
    target.write_text(source)
    (tmp_path / 'problem.cnf').write_text(cnf)
    (tmp_path / 'proof.lrat').write_text(proof)
    result = subprocess.run([sys.executable, '-I', str(target), str(tmp_path / 'problem.cnf'),
                             str(tmp_path / 'proof.lrat'), '--expected-cnf-sha256', digest(cnf)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['verified_unsat']
    # It really is a standard-library module with no imports from the producer/project.
    assert 'from symq' not in source and 'import pysat' not in source


def test_negative_31_bit_literals_are_canonical_tokens():
    # Review finding: the 10-digit bound was applied to the sign too.
    meter = kernel.Meter(kernel.Limits())
    assert kernel._integer('-2147483647', meter) == -2147483647
    assert kernel._integer('-1000000000', meter) == -1000000000
    for bad in ('-2147483648', '-10000000000', '--1', '-01'):
        with pytest.raises(kernel.InvalidProof):
            kernel._integer(bad, meter)
