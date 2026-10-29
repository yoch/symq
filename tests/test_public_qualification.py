"""Self-contained public oracle sanity tests; no other repo or branch required."""
from research.public_qualification.field_hmr_reference import (
    coherence_coefficient,
    multiply,
    verify,
)


def test_field_moduli_and_products():
    # GF4: alpha^2 == alpha+1; GF8: alpha^3 == alpha+1.
    assert multiply(2, 2, 2, 0b111) == 3
    assert multiply(2, 2, 3, 0b1011) == 4
    assert multiply(2, 4, 3, 0b1011) == 3


def test_corrected_channel_and_uncorrected_coherence_loss():
    assert coherence_coefficient(0, 5, 2, 0b111, True) == 1
    assert coherence_coefficient(0, 5, 2, 0b111, False) == 0
    for degree, polynomial in ((2, 0b111), (3, 0b1011)):
        result = verify(degree, polynomial, samples=40)
        assert result["all_data_basis_inputs_checked"] == 1 << (3 * degree)
        assert result["kernel_counterexample"]["corrected"] == 1
