"""Exact GF24 tensor, mutation and weighted gate-count qualification.

No use of private DQI, a sealed holdout, floating-point or external oracle.
Only the pinned GF24 arithmetic model and source-confirmed compiler counts.
"""
from __future__ import annotations

import hashlib
import random

import pytest

from symq.generators.bilinear_optimization import certify_decomposition
from symq.generators.gf2n import Term, emit, karatsuba, schoolbook
from symq.labs.gf24_choice import choose_gf24
from symq.labs.gf24_tower import GF24_MODULUS, gf24_tower_factors

WIDTH = 24
MASK = (1 << WIDTH) - 1
FACTOR_SHA256 = "52cd951205360264ea57c80bd02000da9d2c57c9db7e58e97ac6e15d14c9f54c"


def _independent_product(a: int, b: int) -> int:
    """Independent bit convolution + polynomial long division."""
    product = 0
    for i in range(WIDTH):
        for j in range(WIDTH):
            if ((a >> i) & 1) and ((b >> j) & 1):
                product ^= 1 << (i + j)
    for degree in range(2 * WIDTH - 2, WIDTH - 1, -1):
        if product >> degree & 1:
            product ^= GF24_MODULUS << (degree - WIDTH)
    return product


def _expected_state(state: int) -> int:
    a, b, z = (state & MASK), (state >> WIDTH) & MASK, (state >> (2 * WIDTH)) & MASK
    return a | (b << WIDTH) | ((z ^ _independent_product(a, b)) << (2 * WIDTH))


def test_rank99_fingerprint_and_independent_tensor_certificate():
    terms = gf24_tower_factors()
    assert len(terms) == 11 * 9 == 99
    assert all(type(t) is Term for t in terms)
    packed = ";".join(f"{t.left:x},{t.right:x},{t.into:x}" for t in terms).encode("ascii")
    assert hashlib.sha256(packed).hexdigest() == FACTOR_SHA256
    # The independent oracle checks every coefficient pair of the 24x24 tensor.
    for i in range(WIDTH):
        for j in range(WIDTH):
            got = 0
            for factor in terms:
                if factor.left >> i & factor.right >> j & 1:
                    got ^= factor.into
            assert got == _independent_product(1 << i, 1 << j)
    certify_decomposition(WIDTH, terms, GF24_MODULUS)
    assert gf24_tower_factors() == terms


def test_negative_mutants_and_field_basis_error():
    factors = list(gf24_tower_factors())
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(WIDTH, factors[:-1], GF24_MODULUS)
    bad = list(factors)
    t = factors[0]
    bad[0] = Term(t.left, t.right, t.into ^ 1)
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(WIDTH, bad, GF24_MODULUS)
    with pytest.raises(ValueError, match="irreducible"):
        certify_decomposition(WIDTH, factors, 0x100001A)


def test_complete_72_wire_perm_with_independent_integer_oracle():
    emitted = emit(WIDTH, list(gf24_tower_factors()), strategy="pivot-scheduled")
    assert emitted.width == 3 * WIDTH == 72
    assert emitted.ccx == 99
    assert emitted.cx == 2896
    assert len(emitted.circuit.gates) == 2995
    assert all(g.name in ("cx", "ccx") for g in emitted.circuit.gates)

    rng = random.Random(0x20261101)
    examples = [0, (1 << 72) - 1, 1, 1 << 24, 1 << 48, MASK << 48]
    examples += [rng.randrange(1 << 72) for _ in range(256)]
    for state in examples:
        assert emitted.circuit.run(state) == _expected_state(state)


def test_pivot_cost_tradeoff_and_nonnegative_proxy_selection():
    school = emit(WIDTH, schoolbook(WIDTH))
    karat = emit(WIDTH, karatsuba(WIDTH), strategy="pivot-scheduled")
    tower = emit(WIDTH, list(gf24_tower_factors()), strategy="pivot-scheduled")
    assert (school.ccx, school.cx) == (1419, 0)
    assert (karat.ccx, karat.cx) == (162, 1856)
    assert (tower.ccx, tower.cx) == (99, 2896)

    assert choose_gf24(ccx_weight=1, cx_weight=100).method == "schoolbook-incidence"
    assert choose_gf24(ccx_weight=10, cx_weight=1).method == "karatsuba-pivot-scheduled"
    expensive_ccx = choose_gf24(ccx_weight=32, cx_weight=1)
    assert expensive_ccx.method == "tower-99-pivot-scheduled"
    assert expensive_ccx.cost.weighted == 99 * 32 + 2896
    assert len(expensive_ccx.alternatives) == 3
    for method, weights in (("schoolbook-incidence", (1, 100)),
                            ("karatsuba-pivot-scheduled", (10, 1)),
                            ("tower-99-pivot-scheduled", (32, 1))):
        chosen = choose_gf24(ccx_weight=weights[0], cx_weight=weights[1])
        assert chosen.method == method
        for x in (0, 1, (1 << 72) - 1, 0x123456789ABCDEF):
            assert chosen.circuit.run(x) == _expected_state(x)


@pytest.mark.parametrize("left,right", [(True, 1), (1, True), (-1, 2), (0, 0),
                                        (1.5, 2), (None, 1)])
def test_proxy_refuses_invalid_weights(left, right):
    with pytest.raises(ValueError, match="weights"):
        choose_gf24(ccx_weight=left, cx_weight=right)
