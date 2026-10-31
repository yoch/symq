import time

import pytest

from symq.resources import ResourceLimitExceeded

try:
    from symq.backends._zdd import NativeZDDManager
except ImportError:  # the native core is optional; the ``native`` marker skips these tests
    NativeZDDManager = None

pytestmark = pytest.mark.native


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


def test_max_terms_bounds_every_wire_during_simulation():
    from symq import Budget, Circuit, make_algebra, simulate

    # The peak wire size is measured on the explicit backend, then the native one is held to it.
    circuit = Circuit(5).ccx(0, 1, 3).cx(2, 3).ccx(3, 0, 4).cx(1, 4).cx(2, 4)
    reference = make_algebra("sparse", 5)
    peak = max(len(reference.to_anf(v).terms) for v in simulate(circuit, reference))
    with pytest.raises(ResourceLimitExceeded) as caught:
        simulate(circuit, make_algebra("zdd-native", 5, Budget(max_terms=peak - 1)))
    assert caught.value.resource == "terms"
    simulate(circuit, make_algebra("zdd-native", 5, Budget(max_terms=peak)))


def test_max_bytes_bounds_the_native_arrays():
    import random

    from symq import Budget, check_equivalence, make_algebra, simulate
    from symq.generators import random_circuit

    circuit = random_circuit(10, 60, random.Random(3), max_controls=3)
    roomy = make_algebra("zdd-native", 10, Budget(max_bytes=1 << 30))
    simulate(circuit, roomy)
    used = roomy.memory_info()["manager_bytes"]
    with pytest.raises(ResourceLimitExceeded) as caught:
        simulate(circuit, make_algebra("zdd-native", 10, Budget(max_bytes=used // 2)))
    assert caught.value.resource == "bytes"
    assert caught.value.observed > used // 2
    with pytest.raises(ResourceLimitExceeded):
        make_algebra("zdd-native", 10, Budget(max_bytes=64))
    # The bound survives collection, which replaces the manager.
    result = check_equivalence(circuit, circuit, backend="zdd-native",
                               budget=Budget(max_bytes=1 << 30),
                               backend_options={"collect_every": 200})
    assert result.equivalent


def test_backends_that_cannot_measure_memory_refuse_max_bytes():
    from symq import Budget, make_algebra

    with pytest.raises(ValueError, match="cannot bound its memory"):
        make_algebra("zdd", 4, Budget(max_bytes=1 << 20))


def test_a_node_budget_stops_manager_methods_with_a_resource_error():
    """Node exhaustion is a ResourceLimitExceeded, never a wrapped id or a crash."""
    manager = NativeZDDManager(3, max_nodes=2)
    manager.variable(0)
    manager.variable(1)
    with pytest.raises(ResourceLimitExceeded):
        for i in range(3):
            manager.product(manager.variable(i), manager.variable((i + 1) % 3))
