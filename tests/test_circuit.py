import pytest
from hypothesis import given, strategies as st
from symq import Circuit, UnsupportedOperation


@given(st.integers(min_value=0, max_value=255))
def test_symbolic_matches_concrete(x):
    c = Circuit(8).x(0).cx(0, 1).ccx(1, 2, 7).mcx(0, 1, 2, 6)
    result = c.run(x)
    symbolic = sum(expr.evaluate(x) << i for i, expr in enumerate(c.symbolic()))
    assert symbolic == result
    assert c.inverse().run(result) == x


def test_equivalence_and_mutation():
    identity = Circuit(3)
    double = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    mutated = Circuit(3).ccx(0, 1, 2)
    assert identity.equivalent(double)
    assert not identity.equivalent(mutated)


def test_unsupported():
    with pytest.raises(UnsupportedOperation):
        Circuit(2).append("h", 0)
    with pytest.raises(ValueError):
        Circuit(3).ccx(0, 0, 2)
    with pytest.raises(ValueError):
        Circuit(17).equivalent(Circuit(17))
