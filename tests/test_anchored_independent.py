"""Audit #164: all Kraus routes against an independent generator and matrix oracle."""
from __future__ import annotations

import random
from fractions import Fraction

import pytest

from symq.labs.anchored_kraus import verify as reference
from symq.labs.anchored_stream import verify_stream
from tests.testkit.kraus_loader_cases import gen, ideal, truth

ROUTES = [('reference', lambda s, c: reference(s, c)),
          ('anf', lambda s, c: verify_stream(s, c)),
          pytest.param('sat', lambda s, c: verify_stream(s, c, backend='sat'), marks=pytest.mark.sat)]


@pytest.mark.parametrize('name,route', ROUTES)
def test_independent_cohort_agrees_and_witnesses_are_real(name, route):
    rng = random.Random(16400)
    positives = 0
    for _ in range(40):
        src, spec = gen(rng)
        holds, images, xs = truth(src, spec)
        positives += holds
        result = route(src, spec)
        assert result['status'] in ('equivalent', 'not_proved'), result
        assert (result['status'] == 'equivalent') == holds, (src, spec, result)
        if not holds and name != 'reference':
            witness = result['witness']
            x = witness['input']
            y = x if result['obligation'] == 'outputs' else witness['anchor']
            assert x in xs and y in xs
            assert images[x, y] != {(ideal(spec, x), ideal(spec, y)): Fraction(1)}
    assert positives >= 20    # the cohort is not negative-dominated
