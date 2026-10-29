"""Exact outcome sums for modular-zero and nonzero event monomials."""
from fractions import Fraction
from itertools import product

import pytest

from symq.circuit import UnsupportedOperation
from symq.experimental.cyclotomic import Cyclotomic, affine_event_factor


def _outcome_sum(phase, events, data, *, k, normalize):
    """Enumerate every event assignment without the affine product formula."""
    field_k = max(3, k)
    total = Cyclotomic(field_k)
    for bits in product((0, 1), repeat=len(events)):
        assignment = data | sum(bit << event for bit, event in zip(bits, events))
        exponent = sum(value for mask, value in phase.items() if assignment & mask == mask)
        total += Cyclotomic.root(field_k, (exponent % (1 << k)) << (field_k - k))
    return total.scale(Fraction(1, 1 << len(events))) if normalize else total


@pytest.mark.parametrize("k", (2, 3, 4))
@pytest.mark.parametrize("events", ((0, 1), (1, 3), (0, 2, 4)))
@pytest.mark.parametrize("multiple", (-3, -1, 0, 1, 4))
def test_modular_zero_nonlinear_terms_vanish(k, events, multiple):
    phase = {sum(1 << event for event in events): multiple * (1 << k)}
    assert affine_event_factor(phase, events, k=k) == Cyclotomic.root(max(3, k))
    assert affine_event_factor(phase, events, k=k, normalize=False) == (
        Cyclotomic.root(max(3, k)).scale(1 << len(events))
    )


@pytest.mark.parametrize("k", (2, 3, 4))
def test_modular_normalization_matches_exhaustive_outcome_sums(k):
    modulus = 1 << k
    events = (1, 3, 4)
    # Every residue pair occurs, represented by both negative and oversized
    # integers. Constants and data-dependent coefficients exercise both inputs.
    for first, second in product(range(modulus), repeat=2):
        phase = {
            0: first - 2 * modulus,
            1: second + 3 * modulus,
            2: first - modulus,
            8: second + 2 * modulus,
            17: first + second - modulus,
            10: -3 * modulus,
            26: 2 * modulus,
            27: 0,
        }
        for data, normalize in product((0, 1), (False, True)):
            assert affine_event_factor(phase, events, data, k=k, normalize=normalize) == (
                _outcome_sum(phase, events, data, k=k, normalize=normalize)
            )


@pytest.mark.parametrize("k", (2, 3, 4))
def test_nonzero_nonlinear_coefficients_still_fail_closed(k):
    modulus = 1 << k
    for coefficient in range(-2 * modulus, 2 * modulus + 1):
        if coefficient % modulus:
            for data in (0, 1):
                with pytest.raises(UnsupportedOperation, match="nonlinear"):
                    affine_event_factor({7: coefficient}, (1, 2), data, k=k)
