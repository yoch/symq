"""The optional C core of the ZDD backend must be indistinguishable from the Python one."""
import random

import pytest

from symq import Budget, Circuit, ResourceLimitExceeded, check_equivalence, make_algebra, simulate
from symq.anf import ANF
from symq.backends import ZDDAlgebra
from symq.generators import random_circuit

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


def test_multithreaded_concurrent_simulation():
    """Simulating circuits concurrently across threads must be thread-safe and correct."""
    from concurrent.futures import ThreadPoolExecutor

    circuits = [
        random_circuit(6, 25, random.Random(seed), max_controls=3)
        for seed in range(8)
    ]
    expected = [simulate(c, NativeZDDAlgebra(6)) for c in circuits]

    def run_sim(c):
        return simulate(c, NativeZDDAlgebra(6))

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(run_sim, circuits))

    assert results == expected
