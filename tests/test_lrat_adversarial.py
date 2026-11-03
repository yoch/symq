"""Adversarial campaign of audit #171 against the LRAT path, kept as regression tests.

Soundness property: no positive result (``verified_unsat``, ``proof_checked``,
``proved``) for a satisfiable formula, a forged proof or mismatched sources.
The full audit ran 1500 formulas and 23,750 mutants; this keeps a seeded subset.
"""
from __future__ import annotations

import hashlib
import random
import time

import pytest

from symq.labs import lrat_rup as kernel
from tests.test_lrat_rup import dimacs


def pin(text):
    return hashlib.sha256(text.encode('ascii')).hexdigest()


def check(cnf, proof, **kwargs):
    return kernel.check_lrat(cnf, proof, expected_cnf_sha256=pin(cnf), **kwargs)


def satisfiable(n, clauses):
    return any(all(any((bits >> (abs(l) - 1) & 1) == (l > 0) for l in c) for c in clauses)
               for bits in range(1 << n))


SQUARE = dimacs(2, [(1, 2), (1, -2), (-1, 2), (-1, -2)])
GOOD = '5 1 0 1 2 0\n6 0 5 3 4 0\n'

ATTACKS = {
    'sat_cnf_fake_empty': (dimacs(2, [(1, 2)]), '2 0 1 0\n'),
    'sat_cnf_fake_chain': (dimacs(2, [(1, 2), (-1, 2)]), '3 2 0 1 2 0\n4 0 3 0\n'),
    'truncated': (SQUARE, '5 1 0 1 2 0\n'),
    'empty_proof': (SQUARE, ''),
    'unknown_hint': (SQUARE, '5 1 0 1 9 0\n6 0 5 3 4 0\n'),
    'forward_hint': (SQUARE, '5 1 0 6 2 0\n6 0 5 3 4 0\n'),
    'self_hint': (SQUARE, '5 1 0 5 0\n6 0 5 3 4 0\n'),
    'negative_rat_hint': (SQUARE, '5 1 0 1 -2 0\n6 0 5 3 4 0\n'),
    'deletion_line': (SQUARE, '5 d 1 0\n5 1 0 1 2 0\n6 0 5 3 4 0\n'),
    'tautology': (SQUARE, '5 1 -1 0 1 0\n6 0 5 3 4 0\n'),
    'duplicate_literal': (SQUARE, '5 1 1 0 1 2 0\n6 0 5 3 4 0\n'),
    'id_not_increasing': (SQUARE, '5 1 0 1 2 0\n5 0 5 3 4 0\n'),
    'id_collides_input': (SQUARE, '4 1 0 1 2 0\n6 0 4 3 4 0\n'),
    'trailing_after_empty': (SQUARE, GOOD + '7 1 0 1 2 0\n'),
    'hints_after_conflict': (SQUARE, '5 1 0 1 2 3 0\n6 0 5 3 4 0\n'),
    'no_conflict': (SQUARE, '5 1 0 1 0\n6 0 5 3 4 0\n'),
    'literal_out_of_range': (SQUARE, '5 3 0 1 2 0\n6 0 5 3 4 0\n'),
    'noncanonical_plus': (SQUARE, '5 +1 0 1 2 0\n6 0 5 3 4 0\n'),
    'noncanonical_zero_pad': (SQUARE, '5 01 0 1 2 0\n6 0 5 3 4 0\n'),
    'non_ascii': (SQUARE, '5 1 0 1 2 0\n6 0 5 3 4 0 \n'),
    'two_clauses_one_line': ('p cnf 1 2\n1 0 -1 0\n', '3 0 1 2 0\n'),
    'clause_count_mismatch': ('p cnf 1 3\n1 0\n-1 0\n', '3 0 1 2 0\n'),
    'missing_header': ('1 0\n-1 0\n', '3 0 1 2 0\n'),
    'satlib_percent_trailer': ('p cnf 1 2\n1 0\n-1 0\n%\n0\n', '3 0 1 2 0\n'),
    'huge_token': (SQUARE, '5 1 0 1 99999999999 0\n6 0 5 3 4 0\n'),
}


def test_honest_square_is_verified():
    assert check(SQUARE, GOOD)['status'] == 'verified_unsat'


@pytest.mark.parametrize('name', sorted(ATTACKS))
def test_kernel_attacks_are_invalid(name):
    cnf, proof = ATTACKS[name]
    result = check(cnf, proof)
    assert result['status'] == 'invalid' and not result['verified_unsat'], name
    assert 'cnf_sha256' not in result and 'lrat_sha256' not in result


@pytest.mark.parametrize('pin_value', ['0' * 64, pin(SQUARE).upper(), pin(dimacs(2, [(1, 2)]))])
def test_wrong_or_foreign_pins_are_invalid(pin_value):
    assert kernel.check_lrat(SQUARE, GOOD, expected_cnf_sha256=pin_value)['status'] == 'invalid'


def test_limits_and_expired_deadline_are_inconclusive():
    late = kernel.check_lrat(SQUARE, GOOD, expected_cnf_sha256=pin(SQUARE),
                             absolute_deadline=time.perf_counter() - 1)
    tiny = check(SQUARE, GOOD, limits=kernel.Limits(max_visits=5))
    assert late['status'] == tiny['status'] == 'inconclusive'
    assert not late['verified_unsat'] and not tiny['verified_unsat']


def _mutate(rng, clauses, lines):
    mc, mp = list(clauses), list(lines)
    kind = rng.randrange(6)
    if kind == 0 and len(mc) > 1:
        mc.pop(rng.randrange(len(mc)))
    elif kind == 1:
        i = rng.randrange(len(mc))
        c = list(mc[i])
        j = rng.randrange(len(c))
        c[j] = -c[j]
        mc[i] = tuple(c)
    elif kind == 2 and len(mp) > 1:
        mp.pop(rng.randrange(len(mp)))
    else:
        i = rng.randrange(len(mp))
        w = mp[i].split()
        z = w.index('0')
        if kind == 3 and len(w) > z + 2:
            w[rng.randrange(z + 1, len(w) - 1)] = str(rng.randint(1, len(mc) + len(mp)))
        elif kind == 4 and z > 1:
            k = rng.randint(1, z - 1)
            w[k] = str(-int(w[k]))
        else:
            hints = w[z + 1:-1]
            rng.shuffle(hints)
            w = w[:z + 1] + hints + ['0']
        mp[i] = ' '.join(w)
    return mc, mp


@pytest.mark.sat
def test_seeded_mutants_never_verify_a_satisfiable_formula():
    from symq.labs.lrat_export import prove_cnf

    rng = random.Random(20261103)
    produced = mutants = verified_unsat_mutants = 0
    for _ in range(150):
        n = rng.randint(1, 6)
        clauses = []
        for _ in range(rng.randint(1, 4 * n + 4)):
            variables = rng.sample(range(1, n + 1), rng.randint(1, min(3, n)))
            clauses.append(tuple(v if rng.random() < .5 else -v for v in variables))
        cnf = dimacs(n, clauses)
        result = prove_cnf(cnf)
        assert result['status'] in ('proof_checked', 'satisfiable'), result
        assert (result['status'] == 'satisfiable') == satisfiable(n, clauses)
        if result['status'] != 'proof_checked':
            continue
        produced += 1
        lines = result['lrat'].splitlines()
        for _ in range(10):
            mc, mp = _mutate(rng, clauses, lines)
            mutants += 1
            mutated = dimacs(n, mc)
            if check(mutated, '\n'.join(mp) + '\n')['verified_unsat']:
                verified_unsat_mutants += 1
                assert not satisfiable(n, mc), (mutated, mp)
    assert produced >= 50 and mutants >= 500 and verified_unsat_mutants > 0


@pytest.mark.sat
def test_bundle_tampering_and_mismatched_sources_are_refused():
    from symq.labs import phase_proof_bundle as bundle_api
    from tests.test_phase_proof_bundle import source_case

    case = source_case((0, 1, 2, 3))
    left, right, dephaser, candidate, support = case
    pins = bundle_api.describe_factored_obligation(left, right, dephaser, candidate, support=support)
    bundle = bundle_api.export_factored_proof(left, right, dephaser, candidate, support=support)['bundle']

    def consume(document, sources=case, source_pin=None, certificate_pin=None):
        l, r, d, c, s = sources
        return bundle_api.check_factored_proof(
            l, r, d, c, document, support=s,
            expected_source_sha256=source_pin or pins['source_sha256'],
            expected_certificate_sha256=certificate_pin or pins['certificate_sha256'])['status']

    assert consume(bundle) == 'proved'
    for key in sorted(set(bundle) - {'schema_version'}):
        assert consume({**bundle, key: bundle[key] + ' '}) == 'invalid', key
    assert consume({**bundle, 'extra': 'x'}) == 'invalid'
    assert consume({k: v for k, v in bundle.items() if k != 'lrat'}) == 'invalid'
    assert consume({**bundle, 'schema_version': True}) == 'invalid'
    truncated = '\n'.join(bundle['lrat'].splitlines()[:-1]) + '\n'
    assert consume({**bundle, 'lrat': truncated, 'lrat_sha256': pin(truncated)}) == 'invalid'
    other = source_case((3, 2, 0, 1))
    other_bundle = bundle_api.export_factored_proof(*other[:4], support=other[4])['bundle']
    assert consume(other_bundle) == 'invalid'
    assert consume(bundle, sources=(right, left, dephaser, candidate, support)) == 'invalid'
    assert consume(bundle, sources=(other[0], other[1], other[2], candidate, other[4])) == 'invalid'
    assert consume(bundle, source_pin='0' * 64) == 'invalid'
    assert consume(bundle, certificate_pin='0' * 64) == 'invalid'
