"""Research-pilot checks against actual SymQ sources and an independent oracle."""
from __future__ import annotations

import copy

import pytest

from benchmarks.anchored_kraus import campaign, chain, contract, image, operation, program
from symq.experimental.serialization import program_to_dict
from symq.labs.anchored_kraus import verify
from symq.labs.hmr_table_contract import and_uncompute_example, check_hmr_table_xor


def test_actual_symq_source_and_contract_documents():
    source, spec = and_uncompute_example()
    assert check_hmr_table_xor(source, spec).equivalent
    result = verify(program_to_dict(source), spec.to_dict())
    assert result['status'] == 'equivalent'
    assert result['portable_certificate'] is False
    source.ops.pop()
    assert not check_hmr_table_xor(source, spec).equivalent
    assert verify(program_to_dict(source), spec.to_dict())['status'] == 'not_proved'


def test_independent_rational_density_campaign():
    report = campaign(programs=100, seed=159)
    assert report['passed'] and report['differential_cases'] == 1200
    assert report['checked_witnesses'] == report['refutations']


def test_high_event_count_without_explicit_branch_enumeration():
    source, spec = chain(256)
    result = verify(source, spec)
    assert result['status'] == 'equivalent'
    assert result['hmr_events'] == 256
    assert result['peak_terms'] < 1000
    source['ops'].pop()
    assert verify(source, spec)['status'] == 'not_proved'


def test_restricted_input_domain_and_nonzero_anchor():
    source = program(3, 1, [operation('cx', 1, 2)])
    spec = contract(table=(0, 0), legal=(1,), targets=(0,))
    assert verify(source, spec)['status'] == 'equivalent'
    spec['target_values'] = None
    result = verify(source, spec)
    assert result['status'] == 'not_proved'
    witness = result['witness']['input']
    assert image(source, witness, witness) != {(witness, witness): 1}


def test_strict_admissibility_and_budget_statuses():
    source, spec = chain(1)
    for key, value in [('legal_addresses', []), ('width', True), ('records', 'visible')]:
        altered = copy.deepcopy(spec)
        altered[key] = value
        with pytest.raises(ValueError):
            verify(source, altered)
    assert verify(source, spec, max_seconds=1e-12)['status'] == 'inconclusive'
    with pytest.raises(ValueError):
        campaign(programs=0)


def test_joint_modular_cancellation_is_not_predicatewise_factorization():
    # h=ab, p=a, q=a XOR ab. Neither p nor q factors through h, but 2p+2q=2h mod 4.
    zero_fibre = []
    for a in (0, 1):
        for b in (0, 1):
            h, p = a * b, a
            q = a ^ h
            assert (2 * p + 2 * q) % 4 == 2 * h
            if not h:
                zero_fibre.append((p, q))
    assert len({p for p, _q in zero_fibre}) == 2
    assert len({q for _p, q in zero_fibre}) == 2
