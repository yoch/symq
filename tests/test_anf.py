from itertools import product

import pytest
from hypothesis import given
from hypothesis import strategies as st

from symq import ANF


@given(st.sets(st.integers(min_value=0, max_value=63)), st.sets(st.integers(min_value=0, max_value=63)), st.integers(min_value=0, max_value=63))
def test_ring_semantics(a, b, x):
    left, right = ANF(frozenset(a)), ANF(frozenset(b))
    assert (left ^ right).evaluate(x) == left.evaluate(x) ^ right.evaluate(x)
    assert (left * right).evaluate(x) == left.evaluate(x) & right.evaluate(x)
    assert (left * left) == left


def test_parity_and_identity():
    x = ANF.variable(0)
    one = ANF.constant(1)
    assert ANF.from_terms([1, 1, 0]) == one
    assert x * x == x
    assert x * one == x
    assert x ^ x == ANF()


@pytest.mark.parametrize("bits", list(product([0, 1], repeat=3)))
def test_three_variable_polynomial(bits):
    x, y, z = (ANF.variable(i) for i in range(3))
    assignment = sum(bit << i for i, bit in enumerate(bits))
    assert ((x * y) ^ z).evaluate(assignment) == ((bits[0] & bits[1]) ^ bits[2])


def test_bad_input_rejected():
    with pytest.raises(ValueError):
        ANF.from_terms([-1])
    with pytest.raises(ValueError):
        ANF.variable(-1)
