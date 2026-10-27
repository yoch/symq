"""Displayed identities of the manuscript, checked on small counterexamples.

The alternative product formula once appeared in the paper without its low term; with
P0 = Q0 = 1 and P1 = Q1 = 0 the high part alone is 0 while the product is 1. Both the correct
three-product recursion and the two-product recurrence are checked here against explicit
enumeration over monomial families, so a transcription error cannot survive the test suite.
"""
from __future__ import annotations

from symq import make_algebra
from symq.anf import ANF

WIDTH = 3


def families(width: int) -> list[frozenset[int]]:
    every = list(range(1 << width))
    return [frozenset(every[::step]) for step in (1, 2, 3, 5)]


def split(terms: frozenset[int], variable: int) -> tuple[frozenset[int], frozenset[int]]:
    """``P = P0 + v P1`` for the monomial family ``terms``."""
    bit = 1 << variable
    low = frozenset(m for m in terms if not m & bit)
    high = frozenset(m ^ bit for m in terms if m & bit)
    return low, high


def multiply(left: frozenset[int], right: frozenset[int]) -> frozenset[int]:
    """Product in the Boolean ring: pairwise unions, with parity cancellation."""
    result: set[int] = set()
    for a in left:
        for b in right:
            mask = a | b
            result ^= {mask}
    return frozenset(result)


def add(left: frozenset[int], right: frozenset[int]) -> frozenset[int]:
    return left ^ right


def lift(terms: frozenset[int], variable: int) -> frozenset[int]:
    return frozenset(m | 1 << variable for m in terms)


def three_product(left, right, variable):
    low_l, high_l = split(left, variable)
    low_r, high_r = split(right, variable)
    low_part = multiply(low_l, low_r)
    high_part = add(add(multiply(low_l, high_r), multiply(high_l, low_r)),
                    multiply(high_l, high_r))
    return add(low_part, lift(high_part, variable))


def two_product(left, right, variable):
    low_l, high_l = split(left, variable)
    low_r, high_r = split(right, variable)
    low_part = multiply(low_l, low_r)
    sums = multiply(add(low_l, high_l), add(low_r, high_r))
    return add(low_part, lift(add(sums, low_part), variable))


def test_the_three_product_recursion_is_the_ring_product():
    for left in families(WIDTH):
        for right in families(WIDTH):
            expected = ANF(left) * ANF(right)
            assert ANF(three_product(left, right, 0)) == expected
            assert ANF(three_product(left, right, 1)) == expected


def test_the_two_product_recurrence_is_the_ring_product():
    for left in families(WIDTH):
        for right in families(WIDTH):
            for variable in range(WIDTH):
                assert two_product(left, right, variable) == three_product(left, right, variable)


def test_the_high_part_alone_is_not_the_product():
    """P0 = Q0 = 1, P1 = Q1 = 0: the product is 1, while v((P0+P1)(Q0+Q1) + P0Q0) is 0."""
    one = frozenset({0})
    low_l, high_l = split(one, 0)
    low_r, high_r = split(one, 0)
    assert (low_l, high_l, low_r, high_r) == (one, frozenset(), one, frozenset())
    high_part = add(multiply(add(low_l, high_l), add(low_r, high_r)), multiply(low_l, low_r))
    assert high_part == frozenset()
    assert multiply(one, one) == one


def test_the_backends_reproduce_the_enumeration():
    algebra = make_algebra("zdd", WIDTH)
    for left in families(WIDTH):
        for right in families(WIDTH):
            value = algebra.product([algebra.from_anf(ANF(left)),
                                     algebra.from_anf(ANF(right))])
            assert algebra.to_anf(value) == ANF(multiply(left, right))
