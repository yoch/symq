"""The optional C core of the ZDD backend must be indistinguishable from the Python one."""
import random

import pytest

from symq import Budget, Circuit, ResourceLimitExceeded, check_equivalence, make_algebra, simulate
from symq.anf import ANF
from symq.backends import ZDDAlgebra
from symq.generators import equivalent_variant, mutate, random_circuit

native_module = pytest.importorskip(
    "symq.backends._zdd", reason="the native core is not built (no C compiler or headers)"
)
from symq.backends.zdd_native import MAX_WIDTH, NativeZDDAlgebra

SEEDS = range(40)


def pairs(seed):
    rng = random.Random(seed)
    width = rng.randint(1, 8)
    return width, random_circuit(width, rng.randint(0, 60), rng, max_controls=5)


@pytest.mark.parametrize("seed", SEEDS)
def test_same_outputs_as_the_python_zdd(seed):
    width, circuit = pairs(seed)
    python, native = ZDDAlgebra(width), NativeZDDAlgebra(width)
    expected = simulate(circuit, python)
    got = simulate(circuit, native)
    assert [native.to_anf(v) for v in got] == [python.to_anf(v) for v in expected]
    assert [native.terms(v) for v in got] == [python.terms(v) for v in expected]
    assert [native.size(v) for v in got] == [python.size(v) for v in expected]
    assert [native.min_monomial(v) for v in got] == [python.min_monomial(v) for v in expected]
    assert native.node_count == python.node_count
    assert native.stats.peak_terms == python.stats.peak_terms
    if circuit.gates:
        assert native.stats.seconds > 0 and python.stats.seconds > 0


def test_peak_terms_tracks_intermediate_monomial_expansion():
    """Peak terms must capture intermediate gate volume, not just the final outputs."""
    c = Circuit(4).x(0).x(1).x(2)
    c.mcx(0, 1, 2, 3)
    c.mcx(0, 1, 2, 3)
    py_alg, nat_alg = ZDDAlgebra(4), NativeZDDAlgebra(4)
    simulate(c, py_alg)
    simulate(c, nat_alg)
    assert py_alg.stats.peak_terms == nat_alg.stats.peak_terms
    assert nat_alg.stats.peak_terms == 9
    assert nat_alg.stats.seconds > 0 and py_alg.stats.seconds > 0


@pytest.mark.parametrize("seed", range(200))
def test_ring_operations_match_the_reference(seed):
    rng = random.Random(10_000 + seed)
    width = 6
    left = frozenset(rng.randrange(1 << width) for _ in range(rng.randint(0, 8)))
    right = frozenset(rng.randrange(1 << width) for _ in range(rng.randint(0, 8)))
    algebra = NativeZDDAlgebra(width)
    a, b = algebra.from_anf(ANF(left)), algebra.from_anf(ANF(right))
    assert algebra.to_anf(a) == ANF(left) and algebra.to_anf(b) == ANF(right)
    assert algebra.to_anf(algebra.xor(a, b)) == ANF(left) ^ ANF(right)
    assert algebra.to_anf(algebra.product([a, b])) == ANF(left) * ANF(right)
    assert algebra.to_anf(algebra.product([])) == ANF.constant(1)
    assert algebra.equal(algebra.xor(a, a), algebra.zero())
    witness = algebra.min_monomial(a)
    assert (witness is None) == (not left)
    if witness is not None:
        assert ANF(left).evaluate(witness) == 1


@pytest.mark.parametrize("order", ["reversed", "shuffled"])
def test_variable_order_changes_size_not_result(order):
    rng = random.Random(3)
    width = 9
    circuit = random_circuit(width, 40, rng, max_controls=4)
    permutation = list(range(width))
    if order == "reversed":
        permutation.reverse()
    else:
        rng.shuffle(permutation)
    algebra = NativeZDDAlgebra(width, order=permutation)
    assert [algebra.to_anf(v) for v in simulate(circuit, algebra)] == list(circuit.symbolic())


def test_equivalence_verdicts_and_witnesses():
    width, circuit = 7, random_circuit(7, 30, random.Random(11), max_controls=3)
    assert check_equivalence(circuit, circuit, backend="zdd-native").equivalent
    assert check_equivalence(
        circuit, circuit.__class__(width, list(reversed(circuit.gates))), backend="zdd-native"
    ).equivalent is False
    mutant = circuit.__class__(width, list(circuit.gates) + [])
    mutant.append("x", width - 1)
    result = check_equivalence(circuit, mutant, backend="zdd-native")
    assert not result.equivalent and result.backend == "zdd-native"
    assert circuit.run(result.witness) != mutant.run(result.witness)


def test_same_node_tables_as_the_python_backend_on_the_corpus():
    from pathlib import Path

    from symq.corpus import load_corpus

    manifest = Path(__file__).resolve().parents[1] / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json"
    for entry in load_corpus(manifest).entries:
        if not entry.supported:
            continue
        circuit = entry.load()
        python, native = ZDDAlgebra(circuit.width), NativeZDDAlgebra(circuit.width)
        expected = simulate(circuit, python)
        got = simulate(circuit, native)
        assert [native.to_anf(v) for v in got] == [python.to_anf(v) for v in expected], entry.name
        assert native.node_count == python.node_count, entry.name


def test_budgets_raise_the_same_errors():
    circuit = random_circuit(9, 80, random.Random(7), max_controls=4)
    with pytest.raises(ResourceLimitExceeded) as nodes:
        simulate(circuit, make_algebra("zdd-native", 9, Budget(max_nodes=16)))
    assert nodes.value.resource == "nodes"
    with pytest.raises(ResourceLimitExceeded) as seconds:
        simulate(circuit, make_algebra("zdd-native", 9, Budget(max_seconds=1e-9)))
    assert seconds.value.resource == "seconds"
    algebra = make_algebra("zdd-native", circuit.width)
    last = simulate(circuit, algebra)[-1]
    assert algebra.terms(last) > 8
    bounded = make_algebra("zdd-native", 9, Budget(max_terms=8))
    nine = bounded.from_terms({1 << i for i in range(9)})
    assert bounded.terms(nine) == 9
    with pytest.raises(ResourceLimitExceeded) as terms:
        bounded.to_anf(nine)
    assert terms.value.resource == "terms"


def test_width_limits_and_validation():
    with pytest.raises(ResourceLimitExceeded):
        NativeZDDAlgebra(MAX_WIDTH + 1)
    with pytest.raises(ValueError):
        NativeZDDAlgebra(4, order=[0, 0, 1, 2])
    with pytest.raises(ValueError):
        make_algebra("zdd-native", 2).from_anf(ANF.variable(5))


@pytest.mark.parametrize("width", (1, 2, 31, 32, 63, 64))
def test_monomials_up_to_the_full_width_are_accepted(width):
    """At width 64 ``term >> width`` was a shift by the word size (undefined behaviour) and
    every non-zero monomial was rejected."""
    algebra = NativeZDDAlgebra(width)
    full = (1 << width) - 1
    terms = {0, 1, 1 << (width - 1), full}
    value = algebra.from_terms(terms)
    assert algebra.to_anf(value) == ANF.from_terms(terms)
    assert algebra.terms(value) == len(terms)
    assert algebra.min_monomial(value) == 0


@pytest.mark.parametrize("width", (1, 2, 31, 32, 63, 64))
def test_monomials_beyond_the_width_are_rejected(width):
    algebra = NativeZDDAlgebra(width)
    with pytest.raises(ValueError, match="outside algebra width"):
        algebra.from_terms({1 << width})
    with pytest.raises(ValueError, match="outside algebra width"):
        algebra.from_terms({(1 << (width + 1)) - 1})
    with pytest.raises(ValueError, match="outside algebra width"):
        algebra.from_terms({-1})


def test_values_are_plain_int_node_ids():
    algebra = NativeZDDAlgebra(3)
    value = algebra.from_anf(ANF.from_terms([0b101, 0]))
    assert isinstance(value, int)
    assert algebra.equal(value, algebra.from_terms({0b101, 0}))
    assert algebra.to_anf(value) == ANF.from_terms([0b101, 0])


def test_repeated_use_does_not_leak_nodes_into_the_python_backend():
    """Each algebra owns its table: mixing ids from two instances must be impossible."""
    first, second = NativeZDDAlgebra(4), NativeZDDAlgebra(4)
    a = first.from_anf(ANF.from_terms([0b0011]))
    b = second.from_anf(ANF.from_terms([0b1100]))
    assert a == b  # the same canonical id, but interpreted in its own manager
    assert first.to_anf(a) != second.to_anf(b)
    with pytest.raises(ValueError):
        first.xor(a, 10_000)


def test_invalid_node_ids_are_rejected_without_corruption():
    algebra = NativeZDDAlgebra(3)
    manager = algebra.manager
    value = algebra.from_anf(ANF.from_terms([0b011]))
    for call in (
        lambda: manager.xor(value, 10**6),
        lambda: manager.product(-1, value),
        lambda: manager.anf(10**6),
        lambda: manager.min_monomial(99999),
        lambda: manager.from_terms([16]),
        lambda: manager.from_terms(["x"]),
    ):
        with pytest.raises((ValueError, TypeError, OverflowError)):
            call()
    assert algebra.to_anf(value) == ANF.from_terms([0b011])


def test_repeated_runs_release_their_tables():
    """Each run owns its manager; dropping the algebra must not keep nodes alive."""
    import gc

    for _ in range(50):
        algebra = NativeZDDAlgebra(6)
        simulate(random_circuit(6, 20, random.Random(1), max_controls=3), algebra)
        del algebra
    gc.collect()
    fresh = NativeZDDAlgebra(6)
    assert fresh.node_count == 0


def _all_subsets_plus_target(width: int) -> Circuit:
    """Output ``width - 1`` is ``x_t + prod_{i < width-1} (1 + x_i)``: 2**(width-1) + 1 terms."""
    circuit = Circuit(64)
    for wire in range(width - 1):
        circuit.x(wire)
    circuit.mcx(*range(width - 1), 63)
    return circuit


def test_term_counts_below_int64_are_exact():
    algebra = NativeZDDAlgebra(64)
    outputs = simulate(_all_subsets_plus_target(63), algebra)
    assert algebra.terms(outputs[63]) == 2**62 + 1
    assert algebra.size(outputs[63]) < 200


def test_term_counts_saturate_instead_of_wrapping():
    """2**63 + 1 monomials used to wrap to a negative count and bypass max_terms."""
    algebra = NativeZDDAlgebra(64)
    outputs = simulate(_all_subsets_plus_target(64), algebra)
    assert algebra.terms(outputs[63]) == 2**63 - 1
    with pytest.raises(OverflowError):
        algebra.to_anf(outputs[63])
    budgeted = make_algebra("zdd-native", 64, Budget(max_terms=10**6))
    values = simulate(_all_subsets_plus_target(64), budgeted)
    with pytest.raises(ResourceLimitExceeded) as caught:
        budgeted.to_anf(values[63])
    assert caught.value.resource == "terms"


def test_saturated_families_keep_exact_verdicts_and_witnesses():
    circuit = _all_subsets_plus_target(64)
    assert check_equivalence(circuit, circuit, backend="zdd-native").equivalent
    mutant = Circuit(64, [*circuit.gates[1:]])
    result = check_equivalence(circuit, mutant, backend="zdd-native")
    assert not result.equivalent
    assert circuit.run(result.witness) != mutant.run(result.witness)


HEAVY = random_circuit(12, 70, random.Random(5), max_controls=4)
"""About a second of native work on 12 wires, long enough to observe from another thread."""


def _gate_arrays(circuit):
    indices, offsets, targets = [], [0], []
    for gate in circuit.gates:
        indices.extend(gate.qubits[:-1])
        offsets.append(len(indices))
        targets.append(gate.qubits[-1])
    return indices, offsets, targets


def _fingerprint(manager, state):
    return [manager.terms(v) for v in state], manager.node_count()


def test_independent_managers_simulate_in_parallel_threads():
    from concurrent.futures import ThreadPoolExecutor

    circuits = [random_circuit(6, 25, random.Random(seed), max_controls=3) for seed in range(8)]
    expected = [simulate(c, NativeZDDAlgebra(6)) for c in circuits]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: simulate(c, NativeZDDAlgebra(6)), circuits))
    assert results == expected


def test_every_method_of_a_busy_manager_raises():
    """While one thread simulates without the GIL, any other call on that manager is refused."""
    import threading

    algebra = NativeZDDAlgebra(12)
    manager = algebra.manager
    x = algebra.variable(0)
    calls = {
        "variable": lambda: manager.variable(0),
        "xor": lambda: manager.xor(x, x),
        "product": lambda: manager.product(x, x),
        "simulate": lambda: manager.simulate(None, [], [0], []),
        "terms": lambda: manager.terms(x),
        "anf": lambda: manager.anf(x),
        "from_terms": lambda: manager.from_terms([1]),
        "min_monomial": lambda: manager.min_monomial(x),
        "size": lambda: manager.size(x),
        "node_count": lambda: manager.node_count(),
    }
    refused = dict.fromkeys(calls, 0)
    finished, outputs = threading.Event(), []

    def simulate_heavy():
        try:
            outputs.append(algebra.simulate(HEAVY))
        finally:
            finished.set()

    worker = threading.Thread(target=simulate_heavy)
    worker.start()
    try:
        while not finished.is_set():
            for name, call in calls.items():
                try:
                    call()
                except RuntimeError as error:
                    assert "another thread" in str(error)
                    refused[name] += 1
    finally:
        worker.join()
    assert all(refused.values()), refused
    reference = NativeZDDAlgebra(12)
    expected = reference.simulate(HEAVY)
    assert _fingerprint(manager, outputs[0]) == _fingerprint(reference.manager, expected)
    assert list(outputs[0]) == list(expected)
    assert manager.node_count() == reference.manager.node_count()


def test_buffers_are_copied_before_the_gil_is_released():
    """Mutating the caller's arrays during the run must neither crash nor change the result."""
    import array
    import threading

    indices, offsets, targets = _gate_arrays(HEAVY)
    reference = NativeZDDAlgebra(12)
    expected = reference.manager.simulate(None, indices, offsets, targets)
    algebra = NativeZDDAlgebra(12)
    manager = algebra.manager
    c_indices, c_offsets, c_targets = (array.array("I", values) for values in (indices, offsets, targets))
    finished = threading.Event()

    def mutate():
        while True:
            try:
                manager.node_count()
            except RuntimeError:
                break
            if finished.is_set():
                return
        while not finished.is_set():
            for array_ in (c_indices, c_offsets, c_targets):
                for position in range(len(array_)):
                    array_[position] = 10**6

    mutator = threading.Thread(target=mutate)
    mutator.start()
    try:
        result = manager.simulate(None, c_indices, c_offsets, c_targets)
    finally:
        finished.set()
        mutator.join()
    assert result == expected


@pytest.mark.parametrize("typecode", ["I", "i", "q", "Q", "H", "B"])
def test_other_buffer_formats_give_the_list_result(typecode):
    import array

    circuit = random_circuit(6, 30, random.Random(3), max_controls=3)
    indices, offsets, targets = _gate_arrays(circuit)
    expected = NativeZDDAlgebra(6).manager.simulate(None, indices, offsets, targets)
    assert max([*indices, *offsets, *targets, 0]) < 255
    got = NativeZDDAlgebra(6).manager.simulate(
        None, *(array.array(typecode, values) for values in (indices, offsets, targets))
    )
    assert got == expected


def test_bytes_and_misaligned_buffers():
    import array

    circuit = random_circuit(6, 30, random.Random(4), max_controls=3)
    indices, offsets, targets = _gate_arrays(circuit)
    expected = NativeZDDAlgebra(6).manager.simulate(None, indices, offsets, targets)

    def misaligned(values):
        raw = bytearray(1) + bytearray(array.array("I", values).tobytes())
        return memoryview(raw)[1:].cast("I")

    got = NativeZDDAlgebra(6).manager.simulate(
        None, *(misaligned(values) for values in (indices, offsets, targets))
    )
    assert got == expected
    assert NativeZDDAlgebra(6).manager.simulate(
        None, bytes(indices), bytes(offsets), bytes(targets)
    ) == expected
    big = NativeZDDAlgebra(6).manager.simulate(
        None, *(memoryview(array.array("q", values)) for values in (indices, offsets, targets))
    )
    assert big == expected


def test_malformed_gate_descriptions_are_rejected():
    manager = NativeZDDAlgebra(4).manager
    with pytest.raises(ValueError, match="control outside"):
        manager.simulate(None, [-1], [0, 1], [1])
    with pytest.raises(ValueError, match="control outside"):
        manager.simulate(None, [4], [0, 1], [1])
    with pytest.raises(ValueError, match="gate description"):
        manager.simulate(None, [0], [0, 1], [4])
    with pytest.raises(ValueError, match="gate description"):
        manager.simulate(None, [0, 1], [1, 2], [2])
    with pytest.raises(ValueError, match="gate description"):
        manager.simulate(None, [0, 2], [0, 2], [2])
    with pytest.raises(ValueError, match="gate description"):
        manager.simulate(None, [0], [0, 2], [1])
    with pytest.raises(ValueError, match="one more entry"):
        manager.simulate(None, [0], [0], [1])
    with pytest.raises(ValueError, match="outside this manager"):
        manager.simulate([0, 1, 2, 10**6], [], [0], [])
    with pytest.raises(ValueError, match="state length"):
        manager.simulate([0, 1], [], [0], [])
    with pytest.raises(TypeError):
        manager.simulate(None, 3, [0], [])


def test_more_than_64_controls_through_the_list_api():
    manager = NativeZDDAlgebra(4).manager
    state, _, products = manager.simulate(None, [0] * 70, [0, 70], [1])
    assert products == 1
    assert manager.anf(state[1]) == frozenset({0b10, 0b01})


def test_min_monomial_follows_the_table_as_it_grows():
    rng = random.Random(8)
    native, python = NativeZDDAlgebra(8), ZDDAlgebra(8)
    values = []
    for _ in range(60):
        terms = frozenset(rng.randrange(1, 256) for _ in range(rng.randint(0, 6)))
        left, right = native.from_terms(terms), python.from_terms(terms)
        values.append((left, right))
        if len(values) > 1:
            (a1, b1), (a2, b2) = rng.sample(values, 2)
            if rng.random() < 0.5:
                values.append((native.product([a1, a2]), python.product([b1, b2])))
            else:
                values.append((native.xor(a1, a2), python.xor(b1, b2)))
        for left, right in rng.sample(values, min(3, len(values))):
            assert native.min_monomial(left) == python.min_monomial(right)


def test_time_budget_counts_from_the_guard_not_from_the_manager():
    import time

    guard = Budget(max_seconds=0.4).start()
    time.sleep(0.3)
    algebra = NativeZDDAlgebra(12, guard)
    with pytest.raises(ResourceLimitExceeded) as caught:
        algebra.simulate(HEAVY)
    assert caught.value.resource == "seconds"
    assert time.perf_counter() - guard.started < 0.7


# ------------------------------------------------------------------ cache_limit (lossy cache)

TINY_LIMITS = (1, 2, 3, 4, 16, 256)


def _snapshot(algebra, outputs):
    """Everything observable except wall-clock time."""
    manager = algebra.manager
    return {
        "ids": tuple(outputs),
        "terms": [algebra.terms(v) for v in outputs],
        "sizes": [algebra.size(v) for v in outputs],
        "min_monomials": [algebra.min_monomial(v) for v in outputs],
        "node_count": algebra.node_count,
        "stats": (algebra.stats.gates, algebra.stats.products, algebra.stats.peak_terms),
        "table": manager.node_count(),
    }


def test_the_default_operation_cache_is_lossless():
    algebra = NativeZDDAlgebra(8)
    assert algebra.cache_info()["lossy"] is False
    simulate(random_circuit(8, 60, random.Random(3), max_controls=4), algebra)
    info = algebra.cache_info()
    assert info["lossy"] is False and info["capacity"] >= info["misses"]


@pytest.mark.parametrize("limit", (0, -1, 1.5, "8", True, 2**40))
def test_cache_limit_is_validated(limit):
    with pytest.raises((ValueError, TypeError)):
        NativeZDDAlgebra(4, cache_limit=limit)


@pytest.mark.parametrize("limit", TINY_LIMITS)
def test_capacity_is_the_largest_power_of_two_not_above_the_limit(limit):
    info = NativeZDDAlgebra(4, cache_limit=limit).cache_info()
    assert info["lossy"] is True
    assert info["capacity"] <= limit < 2 * info["capacity"]
    assert info["capacity"] & (info["capacity"] - 1) == 0


@pytest.mark.parametrize("limit", TINY_LIMITS)
@pytest.mark.parametrize("seed", range(12))
def test_forced_eviction_changes_work_but_not_results(seed, limit):
    """Differential against the lossless build of the same code and against the Python ZDD."""
    width, circuit = pairs(seed + 500)
    circuit = Circuit(width, list(circuit.gates) * 2)
    lossless = NativeZDDAlgebra(width)
    lossy = NativeZDDAlgebra(width, cache_limit=limit)
    python = ZDDAlgebra(width)
    expected = _snapshot(lossless, simulate(circuit, lossless))
    got = _snapshot(lossy, simulate(circuit, lossy))
    assert got == expected
    reference = simulate(circuit, python)
    assert [lossy.to_anf(v) for v in expected["ids"]] == [python.to_anf(v) for v in reference]
    assert lossy.cache_info()["misses"] >= lossless.cache_info()["misses"]


def test_a_tiny_cache_really_recomputes():
    circuit = random_circuit(10, 80, random.Random(11), max_controls=4)
    lossless, lossy = NativeZDDAlgebra(10), NativeZDDAlgebra(10, cache_limit=2)
    simulate(circuit, lossless)
    simulate(circuit, lossy)
    assert lossy.cache_info()["capacity"] == 2
    assert lossy.cache_info()["misses"] > 3 * lossless.cache_info()["misses"]
    assert lossy.node_count == lossless.node_count


@pytest.mark.parametrize("limit", (1, 4, 64))
@pytest.mark.parametrize("seed", range(10))
def test_ring_operations_under_a_tiny_cache(seed, limit):
    rng = random.Random(20_000 + seed)
    width = 7
    left = frozenset(rng.randrange(1 << width) for _ in range(rng.randint(0, 30)))
    right = frozenset(rng.randrange(1 << width) for _ in range(rng.randint(0, 30)))
    third = frozenset(rng.randrange(1 << width) for _ in range(rng.randint(0, 30)))
    algebra = NativeZDDAlgebra(width, cache_limit=limit)
    a, b, c = (algebra.from_anf(ANF(t)) for t in (left, right, third))
    product = algebra.product([a, b, c])
    assert algebra.to_anf(product) == ANF(left) * ANF(right) * ANF(third)
    assert algebra.to_anf(algebra.xor(a, b)) == ANF(left) ^ ANF(right)
    assert algebra.equal(algebra.product([a, b]), algebra.product([b, a]))


@pytest.mark.parametrize("limit", (1, 2, 8))
def test_equivalence_verdicts_and_witnesses_under_a_tiny_cache(limit):
    rng = random.Random(77)
    base = random_circuit(8, 40, rng, max_controls=3)
    same = equivalent_variant(base, rng, steps=40)
    other = mutate(base, rng, kind="insert")[0]
    for right, expected in ((same, True), (other, None)):
        lossless, lossy = NativeZDDAlgebra(8), NativeZDDAlgebra(8, cache_limit=limit)
        a0, b0 = simulate(base, lossless), simulate(right, lossless)
        a1, b1 = simulate(base, lossy), simulate(right, lossy)
        assert (a0, b0) == (a1, b1)
        verdict = [lossy.equal(x, y) for x, y in zip(a1, b1)]
        assert verdict == [lossless.equal(x, y) for x, y in zip(a0, b0)]
        if expected is True:
            assert all(verdict)
        for index, same_output in enumerate(verdict):
            if not same_output:
                witness = lossy.min_monomial(lossy.xor(a1[index], b1[index]))
                assert witness == lossless.min_monomial(lossless.xor(a0[index], b0[index]))
                assert base.run(witness) != right.run(witness)
                break


@pytest.mark.parametrize("limit", (1, 4, 1024))
def test_saturation_is_independent_of_the_cache(limit):
    circuit = _all_subsets_plus_target(64)
    reference = NativeZDDAlgebra(64)
    algebra = NativeZDDAlgebra(64, cache_limit=limit)
    expected = simulate(circuit, reference)
    outputs = simulate(circuit, algebra)
    assert outputs == expected
    assert algebra.terms(outputs[63]) == 2**63 - 1
    assert [algebra.terms(v) for v in outputs] == [reference.terms(v) for v in expected]
    with pytest.raises(OverflowError):
        algebra.to_anf(outputs[63])
    assert check_equivalence(
        circuit, circuit, backend=lambda_backend(limit)
    ).equivalent


def lambda_backend(limit):
    class Limited(NativeZDDAlgebra):
        def __init__(self, width, guard=None, **options):
            super().__init__(width, guard, cache_limit=limit, **options)

    return Limited


@pytest.mark.parametrize("limit", (1, 2, 4, 64))
def test_budgets_fire_at_the_same_point_under_a_tiny_cache(limit):
    circuit = random_circuit(9, 80, random.Random(7), max_controls=4)
    observed = []
    for cache_limit in (None, limit):
        algebra = make_algebra("zdd-native", 9, Budget(max_nodes=500), cache_limit=cache_limit)
        with pytest.raises(ResourceLimitExceeded) as caught:
            simulate(circuit, algebra)
        observed.append((caught.value.resource, caught.value.limit, caught.value.observed))
        assert algebra.node_count == algebra.manager.node_count()
    assert observed[0] == observed[1]
    bounded = make_algebra("zdd-native", 9, Budget(max_terms=8), cache_limit=limit)
    nine = bounded.from_terms({1 << i for i in range(9)})
    with pytest.raises(ResourceLimitExceeded) as terms:
        bounded.to_anf(nine)
    assert terms.value.resource == "terms"
    with pytest.raises(ResourceLimitExceeded) as seconds:
        simulate(circuit, make_algebra("zdd-native", 9, Budget(max_seconds=1e-9), cache_limit=limit))
    assert seconds.value.resource == "seconds"


def test_the_gate_loop_and_the_list_api_agree_under_a_tiny_cache():
    circuit = random_circuit(8, 50, random.Random(9), max_controls=4)
    fused = NativeZDDAlgebra(8, cache_limit=2)
    generic = make_algebra("zdd-native", 8, cache_limit=2)
    one_call = simulate(circuit, fused)
    state = [generic.variable(i) for i in range(8)]
    for gate in circuit.gates:
        state[gate.qubits[-1]] = generic.xor(
            state[gate.qubits[-1]], generic.product([state[q] for q in gate.qubits[:-1]])
        )
    assert tuple(state) == one_call
