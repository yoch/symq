"""Streaming Kraus: independent density checks, discarded slots, session budgets."""
from __future__ import annotations

import random
from itertools import product

import pytest

from benchmarks.anchored_kraus import (
    chain,
    contract,
    ideal,
    image,
    operation,
    program,
    random_source,
    states,
)
from symq.labs.anchored_kraus import verify as reference
from symq.labs.anchored_stream import verify_stream
from symq.resources import Budget, VerificationSession


def test_random_complete_coherence_agreement():
    rng = random.Random(311)
    for _ in range(100):
        src = random_source(rng)
        images = {(x, y): image(src, x, y) for x, y in product(range(8), repeat=2)}
        for table in product(range(2), repeat=2):
            for legal in ((0,), (1,), (0, 1)):
                spec = contract(table=table, legal=legal)
                inputs = states(spec)
                truth = all(images[x, y] == {(ideal(spec, x), ideal(spec, y)): 1}
                            for x, y in product(inputs, repeat=2))
                result = verify_stream(src, spec)
                assert result['status'] in ('equivalent', 'not_proved')
                assert (result['status'] == 'equivalent') == truth
                if not truth:
                    witness = result['witness']
                    x = witness['input']
                    y = x if result['obligation'] == 'outputs' else witness['anchor']
                    assert x in inputs and y in inputs
                    assert images[x, y] != {(ideal(spec, x), ideal(spec, y)): 1}


def test_early_leak_prevents_the_old_support_explosion():
    n = 12
    src = program(n + 1, ops=[operation('measure_z', q, slot=f'b{q}') for q in range(n)])
    spec = contract(n + 1, address=(0,), target=(n,), clean=(),
                    borrowed=tuple(range(1, n)), table=(0, 0))
    assert reference(src, spec, max_terms=5000)['status'] == 'inconclusive'
    result = verify_stream(src, spec, max_terms=5000)
    assert result['status'] == 'not_proved'
    assert result['obligation'] == 'irreversible_record'
    assert result['compiled_operations'] == 1
    assert result['peak_terms'] < 30
    # Forgetting/overwriting the classical slot and resetting later cannot un-leak it.
    src['ops'] += [operation('store', slot='b0', value=0), operation('reset', 0)]
    assert verify_stream(src, spec)['obligation'] == 'irreversible_record'


def test_input_independent_measurements_are_eliminated_not_enumerated():
    src = program(2, 1, [operation('measure_z', 2, slot=f'b{i}') for i in range(128)])
    spec = contract(3, borrowed=(), clean=(2,), table=(0, 0))
    assert reference(src, spec, max_terms=5000)['status'] == 'inconclusive'
    result = verify_stream(src, spec, max_terms=5000)
    assert result['status'] == 'equivalent' and result['eliminated_events'] == 128
    assert result['hmr_events'] == 0 and result['peak_terms'] < 10
    # Outcome is not necessarily constant: it may depend on preceding HMR randomness.
    src = program(2, 1, [operation('hmr', 2, slot='b0'),
                        operation('x', 2, condition='b0'),
                        operation('measure_z', 2, slot='b1'),
                        operation('x', 2, condition='b1')])
    assert verify_stream(src, spec)['status'] == 'equivalent'
    for x, y in product(states(spec), repeat=2):
        assert image(src, x, y) == {(x, y): 1}


def test_liveness_preserves_decisions_and_releases_dead_slot_values():
    src, spec = chain(256)
    live = verify_stream(src, spec)
    kept = verify_stream(src, spec, collect_slots=False)
    assert live['status'] == kept['status'] == 'equivalent'
    assert live['peak_live_slots'] == 1 and kept['peak_live_slots'] == 256
    assert live['peak_terms'] == 8 and kept['peak_terms'] == 262
    src['ops'].pop()
    assert verify_stream(src, spec)['status'] == 'not_proved'


def test_shared_budgets_and_closed_json():
    src, spec = chain(1)
    for cap in ({'max_nodes': 1}, {'max_bytes': 1}):
        with VerificationSession(Budget(**cap)), pytest.raises(ValueError):
            verify_stream(src, spec)
    with VerificationSession(Budget(max_terms=2)):
        assert verify_stream(src, spec)['status'] == 'inconclusive'
    assert verify_stream(src, spec, max_seconds=1e-12)['status'] == 'inconclusive'
    assert verify_stream(src, spec, max_json_items=10)['status'] == 'inconclusive'
    with pytest.raises(ValueError):
        verify_stream(src, spec, collect_slots=1)
    recursive = []
    recursive.append(recursive)
    with pytest.raises(ValueError):
        verify_stream(recursive, spec)


def test_original_documents_are_detached_before_compilation(monkeypatch):
    import symq.labs.anchored_stream as module

    src, spec = chain(2)
    expected = verify_stream(src, spec)
    execute = module._execute

    def mutate_originals(*args):
        src['ops'].clear()
        spec['legal_addresses'].clear()
        return execute(*args)

    monkeypatch.setattr(module, '_execute', mutate_originals)
    got = verify_stream(src, spec)
    assert got['status'] == 'equivalent'
    assert got['source_sha256'] == expected['source_sha256']
    assert got['contract_sha256'] == expected['contract_sha256']


def test_reference_route_honours_inherited_budgets_and_bounded_json():
    """Audit #164: the reference ANF route ignored the shared session (certified after expiry)."""
    import time

    from symq.errors import ResourceLimitExceeded

    src, spec = chain(2)
    assert reference(src, spec)['status'] == 'equivalent'
    try:
        with VerificationSession(Budget(max_seconds=0.05)):
            time.sleep(0.06)
            expired = reference(src, spec)
    except ResourceLimitExceeded:   # the session itself reports expiry on exit
        pass
    assert expired['status'] == 'inconclusive' and expired['obligation'] == 'resources'
    for cap in ({'max_nodes': 1}, {'max_bytes': 1}):
        with VerificationSession(Budget(**cap)), pytest.raises(ValueError):
            reference(src, spec)
    with VerificationSession(Budget(max_terms=2)):
        assert reference(src, spec)['status'] == 'inconclusive'
    assert reference(src, spec, budget=Budget(max_seconds=1e-12))['status'] == 'inconclusive'
    with pytest.raises(TypeError):
        reference(src, spec, budget={'max_seconds': 1})
    recursive = []
    recursive.append(recursive)
    with pytest.raises(ValueError):
        reference(recursive, spec)
    assert reference(src, spec, max_json_items=10)['status'] == 'inconclusive'
