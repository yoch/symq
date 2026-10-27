import time

import pytest

from symq.backends._zdd import NativeZDDManager
from symq.resources import ResourceLimitExceeded


def saturated(manager: NativeZDDManager) -> int:
    """A compact family of 2**63 monomials over 63 variables."""
    product = 1
    for i in range(63):
        product = manager.product(product, manager.xor(1, manager.variable(i)))
    return product


def test_saturated_term_count_reports_no_undefined_behaviour():
    manager = NativeZDDManager(64, max_terms=10)
    node = saturated(manager)
    with pytest.raises(ResourceLimitExceeded) as info:
        manager.anf(node)
    error = info.value
    assert error.resource == "terms"
    assert error.observed >= 2**63 - 1
    assert error.observed >= 0
    assert "lower bound" in str(error)


def test_saturated_term_count_without_a_budget_is_an_overflow_error():
    manager = NativeZDDManager(64)
    node = saturated(manager)
    with pytest.raises(OverflowError):
        manager.anf(node)


def test_small_term_counts_are_exact():
    manager = NativeZDDManager(64)
    node = manager.from_terms([0, 1, 2, 3])
    assert manager.terms(node) == 4
    assert len(manager.anf(node)) == 4


def test_node_ids_beyond_the_platform_width_are_rejected():
    manager = NativeZDDManager(2)
    for bad in (1 << 64, -(1 << 64), 1 << 200, -1, 2**32):
        with pytest.raises(ValueError, match="node id outside this manager"):
            manager.xor(bad, 1)
        with pytest.raises(ValueError, match="node id outside this manager"):
            manager.product(1, bad)
    with pytest.raises(ValueError, match="node id outside this manager"):
        manager.anf(1 << 64)


def test_node_ids_of_another_manager_are_rejected():
    small = NativeZDDManager(2)
    big = NativeZDDManager(2)
    node = big.variable(0)
    for _ in range(50):
        node = big.product(node, big.xor(1, big.variable(1)))
    with pytest.raises(ValueError, match="node id outside this manager"):
        small.xor(node, 1)


def test_max_nodes_counts_internal_nodes_only():
    empty = NativeZDDManager(4, max_nodes=1)
    assert empty.node_count() == 0
    empty.variable(0)
    assert empty.node_count() == 1
    with pytest.raises(ResourceLimitExceeded) as info:
        empty.variable(1)
    assert info.value.resource == "nodes"
    assert info.value.observed == 2
    assert info.value.limit == 1


def test_expired_deadline_is_enforced_on_entry_and_during_extraction():
    manager = NativeZDDManager(4, deadline=time.perf_counter() - 1.0, started=0.0,
                               max_seconds=1.0)
    with pytest.raises(ResourceLimitExceeded) as info:
        manager.variable(0)
    assert info.value.resource == "seconds"


def test_one_gate_simulation_after_the_deadline_is_refused():
    manager = NativeZDDManager(2, deadline=time.perf_counter() - 1.0, started=0.0,
                              max_seconds=1.0)
    with pytest.raises(ResourceLimitExceeded):
        manager.simulate(None, [0], [0, 1], [1])


def test_extraction_and_conversion_stop_at_the_deadline():
    terms = list(range(4096))
    expired = NativeZDDManager(16, deadline=time.perf_counter() - 1.0, started=0.0,
                               max_seconds=1.0)
    with pytest.raises(ResourceLimitExceeded):
        expired.from_terms(terms)
    built = NativeZDDManager(16).from_terms(terms)
    with pytest.raises(ResourceLimitExceeded):
        expired.anf(built)
    with pytest.raises(ResourceLimitExceeded):
        expired.size(built)
    with pytest.raises(ResourceLimitExceeded):
        expired.min_monomial(built)
