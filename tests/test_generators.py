"""Public circuit generators: every circuit is checked against its integer reference."""
from __future__ import annotations

import random

import pytest

from symq import Budget, check_equivalence
from symq.generators import gf2n
from symq.generators.arithmetic import cuccaro_adder, cuccaro_expected_output, cuccaro_legal_inputs

METHODS = sorted(gf2n.DECOMPOSITIONS)


@pytest.mark.parametrize("n", sorted(gf2n.MODULI))
def test_every_pinned_modulus_is_irreducible(n):
    assert gf2n.is_irreducible(n)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("n", [2, 3, 4])
def test_multipliers_are_exact_on_every_input(n, method):
    circuit = gf2n.multiplier(n, method)
    assert circuit.width == 3 * n
    assert all(circuit.run(x) == gf2n.multiplier_expected_output(n, x)
               for x in range(1 << (3 * n)))


@pytest.mark.parametrize("n", [5, 8, 12, 16])
def test_the_three_decompositions_are_symbolically_equivalent(n):
    """Beyond exhaustive reach the decompositions are compared exactly with the ANF engine."""
    reference = gf2n.multiplier(n, "schoolbook")
    for method in ("karatsuba", "rank_floor"):
        result = check_equivalence(reference, gf2n.multiplier(n, method), backend="zdd",
                                   budget=Budget(max_seconds=60))
        assert result.equivalent, (n, method)
    rng = random.Random(n)
    for _ in range(32):
        x = rng.randrange(1 << (3 * n))
        assert reference.run(x) == gf2n.multiplier_expected_output(n, x)


def test_a_wrong_multiplier_has_a_replayed_witness():
    good = gf2n.multiplier(4, "karatsuba")
    bad = gf2n.multiplier(4, "karatsuba")
    bad.gates.pop()
    result = check_equivalence(good, bad, backend="zdd")
    assert not result.equivalent
    assert good.run(result.witness) != bad.run(result.witness)


def test_unknown_inputs_are_refused():
    with pytest.raises(ValueError, match="decomposition"):
        gf2n.multiplier(4, "fft")
    with pytest.raises(ValueError, match="modulus"):
        gf2n.multiplier_expected_output(9, 0)
    with pytest.raises(ValueError):
        gf2n.gf_mul(4, 16, 1)


@pytest.mark.parametrize("n", [1, 3, 5])
def test_cuccaro_adder_matches_integer_addition(n):
    circuit = cuccaro_adder(n)
    assert all(circuit.run(x) == cuccaro_expected_output(n, x) for x in cuccaro_legal_inputs(n))
