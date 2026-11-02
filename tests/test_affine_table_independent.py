"""Audit #164: affine-target checker against an independent cohort and targeted resets."""
from __future__ import annotations

import copy
import random
from fractions import Fraction
from itertools import product

import pytest

from benchmarks.affine_table import wide_fixture
from benchmarks.anchored_kraus import operation
from symq.labs.affine_table import verify_affine_table
from tests.testkit import table_channel_oracle as oracle
from tests.testkit.affine_loader_cases import gen, ideal, to_program

BACKENDS = ['anf', pytest.param('sat', marks=pytest.mark.sat)]


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('style', ['shannon', 'minterms'])
def test_independent_affine_cohort(backend, style):
    rng = random.Random(16462)
    positives = 0
    for _ in range(30):
        src, spec, xs = gen(rng)
        program = to_program(src)
        images = {(x, y): oracle.forgotten(program, {(x, y): Fraction(1)}) for x, y in product(xs, repeat=2)}
        holds = all(v == {(ideal(spec, x), ideal(spec, y)): Fraction(1)} for (x, y), v in images.items())
        positives += holds
        result = verify_affine_table(src, spec, backend=backend, table_style=style)
        assert result['status'] in ('equivalent', 'not_proved'), result
        assert (result['status'] == 'equivalent') == holds, (src, spec, result)
        if not holds:
            witness = result['witness']
            x = witness['input']
            y = x if result['obligation'] == 'outputs' else witness['anchor']
            assert x in xs and y in xs
            assert images[x, y] != {(ideal(spec, x), ideal(spec, y)): Fraction(1)}
    assert positives >= 10


@pytest.mark.parametrize('backend', BACKENDS)
def test_wide_fixture_resets_are_proved_from_the_relation_not_assumed(backend):
    src, spec = wide_fixture()
    # z6^z7 of word 1 (target positions 14,15 -> wires 25,26) is zero on the image: proved.
    clean = copy.deepcopy(src)
    clean['ops'][0:0] = [operation('cx', 25, 51), operation('cx', 26, 51), operation('reset', 51)]
    assert verify_affine_table(clean, spec, backend=backend, max_seconds=60)['status'] == 'equivalent'
    # z6^z8 crosses two words: input-dependent, so the reset is an irreversible record.
    leak = copy.deepcopy(src)
    leak['ops'][0:0] = [operation('cx', 17, 51), operation('cx', 19, 51), operation('reset', 51)]
    refused = verify_affine_table(leak, spec, backend=backend, max_seconds=60)
    assert refused['status'] == 'not_proved' and refused['obligation'] == 'irreversible_record'
    assert refused['witness']['operation_index'] == 2 and refused['witness']['wire'] == 51
    # Every one of the 40 outputs is observed, including the five sign copies.
    for word in range(5):
        dropped = copy.deepcopy(src)
        wire = 11 + 8 * word + 7
        index = next(i for i, o in enumerate(dropped['ops']) if o['kind'] == 'cx' and o['wires'][1] == wire)
        del dropped['ops'][index]
        result = verify_affine_table(dropped, spec, backend=backend, max_seconds=60)
        assert result['status'] == 'not_proved' and result['obligation'] == 'outputs'
        assert result['witness']['wire'] == wire
