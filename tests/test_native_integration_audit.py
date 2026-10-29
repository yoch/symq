"""Independent high-word substitution and owned-transfer integration checks."""
from itertools import product

import pytest

from symq import ANF, Budget, ResourceLimitExceeded
from symq.backends import has_native, make_algebra
from symq.resources import VerificationSession

pytestmark = pytest.mark.skipif(not has_native(), reason="native extension not built")


def _substitute(terms, variable_mapping):
    """Boolean monomial substitution, including idempotence and XOR cancellation."""
    result = set()
    for mask in terms:
        replaced = 0
        for variable, target in variable_mapping.items():
            if mask >> variable & 1:
                replaced |= 1 << target
        result.symmetric_difference_update((replaced,))
    return frozenset(result)


@pytest.mark.parametrize("width", (65, 96, 127, 128))
@pytest.mark.parametrize("ordering", ("identity", "reverse", "rotated"))
def test_high_word_collision_rename_and_cross_manager_transfer(width, ordering):
    if ordering == "identity":
        order = list(range(width))
    elif ordering == "reverse":
        order = list(reversed(range(width)))
    else:
        order = list(range(64, width)) + list(range(64))
    algebra = make_algebra("zdd-native-wide", width, order=order)
    levels = (0, 1, width // 2 - 1, width // 2, width - 2, width - 1)
    destinations = (0, 0, width // 2, width // 2, width - 1, width - 1)
    mapping = list(range(width))
    for source, target in zip(levels, destinations):
        mapping[source] = target
    variable_mapping = {order[level]: order[mapping[level]] for level in range(width)}
    masks = [1 << order[level] for level in levels]
    polynomials = [frozenset(masks), frozenset((masks[0] | masks[1],)),
                   frozenset((masks[2] | masks[3], masks[4], masks[5])),
                   frozenset((0, masks[0] | masks[-1])), frozenset(), frozenset((0,))]
    roots = [algebra.from_anf(ANF(terms)) for terms in polynomials]
    expected = [_substitute(terms, variable_mapping) for terms in polynomials]
    renamed = algebra.rename_many(roots + roots[:1], mapping)
    assert renamed[0] == renamed[-1]
    assert [algebra.to_anf(root).terms for root in renamed[:-1]] == expected

    # Exhaust the substituted coordinates, including physical bits in the high
    # word under the custom orders, and keep the original manager live.
    targets = sorted({variable_mapping[order[level]] for level in levels})
    for bits in product((0, 1), repeat=len(targets)):
        assignment = sum(bit << variable for variable, bit in zip(targets, bits))
        for actual, terms in zip(renamed, expected + expected[:1]):
            assert algebra.to_anf(actual).evaluate(assignment) == ANF(terms).evaluate(assignment)
    source = algebra.manager
    fresh, transferred = source.clone_roots(renamed)
    assert fresh is not source
    assert transferred[0] == transferred[-1]
    assert [fresh.anf(root) for root in transferred] == [source.anf(root) for root in renamed]
    for actual, terms in zip(transferred, expected + expected[:1]):
        assert fresh.min_monomial(actual) == min(
            terms, key=lambda mask: (mask.bit_count(), mask), default=None,
        )


@pytest.mark.parametrize("width", (65, 96, 127, 128))
def test_high_word_witness_ties_use_external_masks_after_transfer(width):
    algebra = make_algebra("zdd-native-wide", width, order=list(reversed(range(width))))
    high = 1 << (width - 1)
    low = 1 << 1
    root = algebra.from_anf(ANF(frozenset((high, low, high | 1))))
    assert algebra.min_monomial(root) == low
    (transferred,) = algebra.collect_roots((root,))
    assert algebra.min_monomial(transferred) == low
    high_only = algebra.from_anf(ANF(frozenset((high, high | 1))))
    assert algebra.min_monomial(high_only) == high


def test_wide_transfer_resource_failure_preserves_source_and_roots():
    algebra = make_algebra("zdd-native-wide", 128, order=list(reversed(range(128))))
    terms = frozenset((1 << 127, (1 << 127) | (1 << 64), 1))
    root = algebra.from_anf(ANF(terms))
    source = algebra.manager
    count = algebra.node_count
    with VerificationSession(Budget(max_nodes=count)) as session:
        session.reserve(source, nodes=count)
        before = session.reservation(source)
        with pytest.raises(ResourceLimitExceeded, match="nodes"):
            algebra.collect_roots((root, root, 0, 1))
        assert algebra.manager is source
        assert session.reservation(source) == before
        assert algebra.to_anf(root).terms == terms
    limited = make_algebra("zdd-native-wide", 128, Budget(max_terms=2))
    copied = limited.from_anf(ANF(terms))
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        limited.to_anf(copied)
    assert limited.min_monomial(copied) == 1
