"""Independent Kraus-channel and adversarial qualification of reset-cache columns."""
from __future__ import annotations

import copy
from dataclasses import replace
from itertools import product

import pytest
from testkit.kraus_oracle import independent_kraus

from symq.experimental.hybrid import HOp, HybridProgram
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import HybridFragment
from symq.labs.reset_cache import CacheLimits, cache_request, prove_reset_cache, replay_reset_cache
from symq.labs.rewrite import ReceiptMismatch
from symq.labs.rewrite_request import fragment_from_dict
from symq.resources import Budget


def request():
    reference = HybridFragment(3, (HOp('ccx', (0, 1, 2)), HOp('x', (2,)),
                                   HOp('cz', (0, 2)), HOp('ccx', (0, 1, 2))))
    return cache_request(reference, (0, 3))


def prove(document, **kw):
    return prove_reset_cache(document, expected_request_sha256=canonical_sha256(document), **kw)


def test_all_columns_imply_same_channel_on_every_matrix_unit_and_dirty_fresh_input():
    document = request()
    result = prove(document)
    assert result['outcome'] == 'equivalent'
    assert result['checked_kraus_columns'] == 16
    assert result['measurement_version'] == 1
    assert not result['global_substitution_authorized']
    reference = fragment_from_dict(document['reference'])
    candidate = fragment_from_dict(document['candidate'])
    expected = HybridProgram(4, 0, [HOp('reset', (3,)), *reference.ops])
    actual = HybridProgram(4, 0, list(candidate.ops))
    # Includes coherent off-diagonals and arbitrary initial value/correlation of
    # the extra wire. The reference reset removes its incoming correlations.
    for x, y in product(range(16), repeat=2):
        assert independent_kraus(expected, x, y) == independent_kraus(actual, x, y)


def test_missing_hmr_correction_and_overwritten_product_are_semantic_failures():
    document = request()
    missing = copy.deepcopy(document)
    missing['candidate']['ops'].pop(-1)
    result = prove(missing)
    assert result['outcome'] == 'not_proved'
    assert result['failed_criterion'] == 'signed_column_identity_only'
    assert result['witness']['scope'] == 'local_column_only'
    overwritten = copy.deepcopy(document)
    overwritten['candidate']['ops'].insert(3, {'kind': 'x', 'wires': [0], 'slot': None, 'condition': None, 'source': None, 'value': None})
    assert prove(overwritten)['outcome'] == 'not_proved'
    # A syntax mutation may preserve semantics; fresh proof decides.
    equivalent = copy.deepcopy(document)
    op = {'kind': 'x', 'wires': [0], 'slot': None, 'condition': None, 'source': None, 'value': None}
    equivalent['candidate']['ops'][3:3] = [op, copy.deepcopy(op)]
    assert prove(equivalent)['outcome'] == 'equivalent'


def test_explicit_preparation_cannot_be_replaced_with_a_dirty_input_assumption():
    document = request()
    candidate = fragment_from_dict(document['candidate'])
    expected = HybridProgram(4, 0, [HOp('reset', (3,)), *fragment_from_dict(document['reference']).ops])
    dirty = HybridProgram(4, 0, list(candidate.ops[1:]))
    assert independent_kraus(expected, 8, 9) != independent_kraus(dirty, 8, 9)
    document['candidate']['ops'].pop(0)
    assert prove(document)['outcome'] == 'unsupported'


def test_measurement_read_before_definition_and_slot_reuse_fail_closed():
    document = request()
    early = copy.deepcopy(document)
    correction = early['candidate']['ops'].pop(-1)
    early['candidate']['ops'].insert(1, correction)
    assert prove(early)['outcome'] == 'unsupported'
    reuse = copy.deepcopy(document)
    reuse['candidate']['ops'].insert(-1, {'kind': 'store', 'wires': [], 'slot': 'b0', 'value': 0, 'condition': None, 'source': None})
    assert prove(reuse)['outcome'] == 'unsupported'


def test_arbitrary_classical_inputs_conditions_phases_and_slot_versions():
    reference = HybridFragment(3, (HOp('ccx', (0, 1, 2)), HOp('z', (2,), condition='!b1'),
                                   HOp('invert', slot='b1'), HOp('cz', (0, 2), condition='b1'),
                                   HOp('ccx', (0, 1, 2))), ('b1',))
    document = cache_request(reference, (0, 4), fresh_slot='b2')
    assert prove(document)['outcome'] == 'equivalent'
    mutation = copy.deepcopy(document)
    mutation['candidate']['ops'].append({'kind': 'invert', 'wires': [], 'slot': 'b1', 'condition': None, 'source': None, 'value': None})
    assert prove(mutation)['outcome'] == 'not_proved'


def test_global_phase_is_a_failed_column_criterion_not_channel_inequivalence():
    document = request()
    document['candidate']['ops'].append({'kind': 'neg', 'wires': []})
    result = prove(document)
    assert result['outcome'] == 'not_proved'
    assert result['failed_criterion'] == 'signed_column_identity_only'
    assert result['witness']['scope'] == 'local_column_only'
    reference = fragment_from_dict(document['reference'])
    candidate = fragment_from_dict(document['candidate'])
    expected = HybridProgram(4, 0, [HOp('reset', (3,)), *reference.ops])
    actual = HybridProgram(4, 0, list(candidate.ops))
    # A global sign changes every Kraus column but cancels in the channel.
    for x, y in product(range(16), repeat=2):
        assert independent_kraus(expected, x, y) == independent_kraus(actual, x, y)


def test_full_receipt_replay_request_drift_and_dependency_mutation():
    document = request()
    result = prove(document)
    pin = canonical_sha256(document)
    assert replay_reset_cache(document, result, expected_request_sha256=pin) == result
    for field, value in (('schema_version', True), ('global_substitution_authorized', True),
                         ('checked_kraus_columns', 1), ('dependencies', {})):
        changed = copy.deepcopy(result)
        changed[field] = value
        with pytest.raises(ReceiptMismatch):
            replay_reset_cache(document, changed, expected_request_sha256=pin)
    changed = copy.deepcopy(document)
    changed['fresh_slot'] = 'b99'
    with pytest.raises(ReceiptMismatch):
        prove_reset_cache(changed, expected_request_sha256=pin)


def test_limits_and_expiration_never_establish_a_resource_or_authorize_a_site(monkeypatch):
    import symq.labs.reset_cache as api
    from symq.errors import ResourceLimitExceeded

    document = request()
    for budget in (Budget(absolute_deadline=0),):
        assert prove(document, budget=budget)['outcome'] == 'inconclusive'
    limited = prove(document, limits=replace(CacheLimits(), max_column_steps=1))
    assert limited['outcome'] == 'inconclusive'
    assert 'clean_return' not in limited
    def expired(_):
        raise ResourceLimitExceeded('seconds', 1, 2)
    monkeypatch.setattr(api, '_dependencies', expired)
    result = prove(document)
    assert result['outcome'] == 'inconclusive'
    assert 'clean_entry' not in result
    assert not result['global_substitution_authorized']
