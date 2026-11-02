"""Wide affine targets: independent finite oracle, strict boundaries and real resets."""
from __future__ import annotations

import copy
import random
from itertools import product

import pytest

from benchmarks.affine_table import physical_inputs, run, v2, wide_fixture
from benchmarks.anchored_kraus import contract, ideal, image, operation, program
from symq.labs import anchored_stream
from symq.labs.affine_table import affine_target_from_equations, verify_affine_table
from symq.labs.anchored_kraus import verify as old_verify
from symq.resources import Budget, VerificationSession


def test_parity_conversion_matches_independent_enumeration():
    rng = random.Random(35040)
    for width in range(1, 7):
        for _ in range(80):
            rows = [[rng.randrange(1 << width), rng.randrange(2)] for _ in range(rng.randrange(7))]
            solutions = {z for z in range(1 << width)
                         if all((z & m).bit_count() % 2 == rhs for m, rhs in rows)}
            if not solutions:
                with pytest.raises(ValueError, match='inconsistent'):
                    affine_target_from_equations(width, rows)
                continue
            space = affine_target_from_equations(width, rows)
            image_values = []
            for u in range(1 << len(space['columns'])):
                value = space['offset']
                for j, column in enumerate(space['columns']):
                    if u >> j & 1:
                        value ^= column
                image_values.append(value)
            assert set(image_values) == solutions
            assert len(image_values) == len(solutions)  # verified injectivity, no duplicate coverage


def test_independent_small_density_oracle():
    report = run(programs=20, backends=('anf',))
    assert report['passed']
    assert report['differential']['anf']['cases'] == 120
    assert report['differential']['anf']['witnesses'] == report['differential']['anf']['negative']


@pytest.mark.parametrize('backend', ['anf', pytest.param('sat', marks=pytest.mark.sat)])
def test_40_physical_targets_35_independent_89_resets(backend):
    src, spec = wide_fixture()
    result = verify_affine_table(src, spec, backend=backend, max_seconds=30)
    assert result['status'] == 'equivalent', result
    assert result['target_width'] == 40 and result['target_dimension'] == 35
    assert result['legal_basis_states'] == str(1363 * (1 << 35))
    assert result['hmr_events'] == result['eliminated_events'] == 89
    unrestricted = copy.deepcopy(spec)
    unrestricted['target_space'] = affine_target_from_equations(40, [])
    refusal = verify_affine_table(src, unrestricted, backend=backend, max_seconds=30)
    assert refusal['status'] == 'not_proved'
    assert refusal['contract_sha256'] != result['contract_sha256']
    assert refusal['witness']['input'] != refusal['witness']['anchor']


def test_89_zero_resets_need_no_exponential_support():
    source = program(3, 1, [operation('reset', 3) for _ in range(89)])
    spec = contract(table=(0, 0))
    assert old_verify(source, spec, max_terms=5000)['status'] == 'inconclusive'
    actual = anchored_stream.verify_stream(source, spec, max_terms=5000)
    assert actual['status'] == 'equivalent'
    assert actual['eliminated_events'] == 89 and actual['peak_terms'] == 4


@pytest.mark.parametrize('backend', ['anf', pytest.param('sat', marks=pytest.mark.sat)])
def test_nonzero_offset_uses_coordinate_anchor_not_physical_offset(backend):
    # Target words 01,10. q1 XOR q2 is a constant one, not an input-dependent leak.
    spec = v2(contract(4, address=(0,), target=(1, 2), clean=(3,), borrowed=(), table=(0, 0)),
              {'kind': 'affine_image', 'offset': 1, 'columns': [3]})
    src = program(3, 1, [operation('cx', 1, 3), operation('cx', 2, 3), operation('reset', 3)])
    result = verify_affine_table(src, spec, backend=backend)
    assert result['status'] == 'equivalent', result
    assert result['anchor'] == 2
    for x, y in product(physical_inputs(spec), repeat=2):
        assert image(src, x, y) == {(x, y): 1}
    src['ops'].append(operation('z', 1))
    fail = verify_affine_table(src, spec, backend=backend)
    assert fail['status'] == 'not_proved'
    x, y = fail['witness']['input'], fail['witness']['anchor']
    assert x in physical_inputs(spec) and y in physical_inputs(spec)
    assert image(src, x, y) != {(x, y): 1}


def test_zero_rank_and_layout_and_borrowed_workspace():
    for target in (0, 1, 2, 3):
        # Scrambled address/target locations; arbitrary borrowed q3 is preserved.
        spec = v2(contract(5, address=(2,), target=(1, 0), borrowed=(3,), clean=(4,), table=(0, 2)),
                  {'kind': 'affine_image', 'offset': target, 'columns': []})
        src = program(4, 1, [operation('cx', 2, 0), operation('reset', 4)])
        result = verify_affine_table(src, spec)
        assert result['status'] == 'equivalent'
        assert result['target_dimension'] == 0 and result['legal_basis_states'] == '4'
        for x, y in product(physical_inputs(spec), repeat=2):
            assert image(src, x, y) == {(ideal(spec, x), ideal(spec, y)): 1}
        src['ops'].append(operation('x', 3))
        assert verify_affine_table(src, spec)['status'] == 'not_proved'


def test_shannon_matches_literal_table_and_minterms_with_padding():
    rng = random.Random(1363)
    for _ in range(50):
        table = [rng.randrange(8) for _ in range(4)]
        c = contract(6, address=(1, 0), target=(3, 2, 4), borrowed=(), clean=(5,),
                     table=table, legal=(0, 2, 3))
        c['table'][1] = None
        spec = v2(c, affine_target_from_equations(3, [[3, 1]]))
        src = program(5, 1)
        for address in (0, 2, 3):
            inverted = [q for j, q in enumerate(spec['address_wires']) if not (address >> j & 1)]
            src['ops'].extend(operation('x', q) for q in inverted)
            src['ops'].extend(operation('ccx', 1, 0, q) for j, q in enumerate(spec['target_wires']) if table[address] >> j & 1)
            src['ops'].extend(operation('x', q) for q in reversed(inverted))
        assert verify_affine_table(src, spec, table_style='shannon')['status'] == 'equivalent'
        assert verify_affine_table(src, spec, table_style='minterms')['status'] == 'equivalent'
        for x, y in product(physical_inputs(spec), repeat=2):
            assert image(src, x, y) == {(ideal(spec, x), ideal(spec, y)): 1}
        spec['legal_addresses'] = [0, 1, 2, 3]
        with pytest.raises(ValueError):
            verify_affine_table(src, spec)  # newly legal None is never a zero-filled promise


def test_invalid_domain_and_malformed_suffix_and_inherited_budgets():
    source, spec = wide_fixture()
    for space in ({'kind': 'affine_image', 'offset': 0, 'columns': [1, 1]},
                  {'kind': 'affine_image', 'offset': 0, 'columns': [0]},
                  {'kind': 'affine_image', 'offset': True, 'columns': []},
                  {'kind': 'affine_image', 'offset': 0, 'columns': [1 << 40]},
                  {'kind': 'affine_image', 'offset': 0, 'columns': [True]}):
        altered = {**spec, 'target_space': space}
        with pytest.raises(ValueError):
            verify_affine_table(source, altered)
    invalid = copy.deepcopy(source)
    invalid['ops'].append(operation('h', 0))
    with pytest.raises(ValueError):
        verify_affine_table(invalid, spec)
    assert verify_affine_table(source, spec, max_seconds=1e-12)['status'] == 'inconclusive'
    assert verify_affine_table(source, spec, max_json_items=8)['status'] == 'inconclusive'
    with VerificationSession(Budget(max_terms=1)):
        assert verify_affine_table(source, spec)['status'] == 'inconclusive'
    with VerificationSession(Budget(max_bytes=1)), pytest.raises(ValueError):
        verify_affine_table(source, spec)


def test_snapshot_and_relation_hash_are_source_bound(monkeypatch):
    source, spec = wide_fixture()
    expected = verify_affine_table(source, spec)
    old = anchored_stream._execute

    def mutate_originals(*args, **kwargs):
        source['ops'].clear()
        spec['target_space']['columns'].clear()
        return old(*args, **kwargs)

    monkeypatch.setattr(anchored_stream, '_execute', mutate_originals)
    got = verify_affine_table(source, spec)
    assert got['status'] == 'equivalent'
    assert got['target_dimension'] == 35
    assert got['source_sha256'] == expected['source_sha256']
    assert got['contract_sha256'] == expected['contract_sha256']
