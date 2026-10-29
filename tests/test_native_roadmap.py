"""Differential checks for the explicit experimental native capabilities."""
from __future__ import annotations

import random
import time

import pytest

from symq import ANF, Budget, Circuit, PhaseProgram, ResourceLimitExceeded, check_equivalence
from symq.backends import has_native, make_algebra
from symq.resources import Guard, VerificationSession

pytestmark = pytest.mark.skipif(not has_native(), reason="native extension not built")


@pytest.mark.parametrize("order", [None, [3, 1, 2, 0]])
def test_rename_many_preserves_per_root_support_and_collisions(order):
    algebra = make_algebra("zdd-native", 4, order=order)
    # Maps act on levels, including when variable order is not the identity.
    variables = [algebra.variable(q) for q in algebra.order]
    roots = [variables[0], variables[1], algebra.product(variables[:2]),
             algebra.xor(variables[0], variables[1]), 0, 1]
    collision = [2, 2, 0, 1]
    batched = algebra.rename_many(roots, collision)
    assert batched == tuple(algebra.manager.rename(root, collision) for root in roots)
    assert batched[2] == variables[2]
    assert batched[3] == 0  # x+x cancels after the collision.
    # The combined support reverses, but each root is individually admissible.
    reverse = [1, 0, 2, 3]
    assert algebra.rename_many(roots[:2], reverse) == (variables[1], variables[0])
    before = algebra.node_count
    with pytest.raises(ValueError, match="not order preserving"):
        algebra.rename_many([roots[0], roots[2]], reverse)
    assert algebra.node_count == before  # Validation completes before transformations.


@pytest.mark.parametrize("width", [64, 65, 66, 127, 128])
@pytest.mark.parametrize("reversed_order", [False, True])
def test_wide_ring_import_export_and_witness_matches_python(width, reversed_order):
    order = list(reversed(range(width))) if reversed_order else None
    wide = make_algebra("zdd-native-wide", width, order=order)
    python = make_algebra("zdd", width, order=order)
    rng = random.Random(411 + width)
    for _ in range(10):
        terms = []
        for _ in range(2):
            masks = {sum(1 << q for q in rng.sample(range(width), rng.randrange(5)))
                     for _ in range(7)}
            terms.append(ANF(frozenset(masks)))
        a, b = (wide.from_anf(value) for value in terms)
        x, y = (python.from_anf(value) for value in terms)
        for observed, expected in [(a, x), (wide.xor(a, b), python.xor(x, y)),
                                   (wide.product((a, b)), python.product((x, y)))]:
            expected_anf = python.to_anf(expected)
            assert wide.to_anf(observed) == expected_anf
            # Compare external masks directly: variable ordering may break ties
            # differently in the Python backend's level-based witness traversal.
            assert wide.min_monomial(observed) == min(
                expected_anf.terms, key=lambda mask: (mask.bit_count(), mask), default=None,
            )
    high = wide.variable(width - 1)
    assert wide.min_monomial(high) == 1 << (width - 1)
    assert wide.to_anf(high) == ANF(frozenset({1 << (width - 1)}))


def test_wide_is_explicit_and_returns_a_high_bit_counterexample():
    with pytest.raises(ResourceLimitExceeded, match="width"):
        make_algebra("zdd-native", 65)
    with pytest.raises(ResourceLimitExceeded, match="width"):
        make_algebra("zdd-native-wide", 129)
    left = Circuit(128)
    right = Circuit(128).cx(127, 0)
    result = check_equivalence(left, right, backend="zdd-native-wide")
    assert result.equivalent is False
    assert result.witness == 1 << 127
    assert left.run(result.witness) != right.run(result.witness)
    algebra = make_algebra("zdd-native-wide", 65)
    for bad in [-1, 1 << 65, 1 << 128]:
        with pytest.raises(ValueError, match="outside algebra width"):
            algebra.manager.from_terms([bad])


def _hmr_reference(program, algebra, offset):
    state = [algebra.variable(offset + q) if q < program.data else 0
             for q in range(program.width)]
    phase = 0
    coefficients = []
    for op in program.ops:
        if op.kind == "hmr":
            coefficients.append(state[op.qubits[0]])
            state[op.qubits[0]] = 0
        else:
            factors = op.qubits[:-1] if op.kind == "mcx" else op.qubits
            value = algebra.product([state[q] for q in factors])
            if op.kind == "mcx":
                target = op.qubits[-1]
                state[target] = algebra.xor(state[target], value)
            elif op.kind == "mcz":
                phase = algebra.xor(phase, value)
            else:
                coefficients[op.outcome] = algebra.xor(coefficients[op.outcome], value)
    return tuple(state), phase, tuple(coefficients)


@pytest.mark.parametrize("seed", range(16))
@pytest.mark.parametrize("wide", [False, True])
def test_fused_hmr_matches_python_reference_and_observes_mutations(seed, wide):
    rng = random.Random(901 + seed)
    program = PhaseProgram(3, 7)  # Physical wires deliberately exceed symbolic width.
    for _ in range(18):
        qubits = rng.sample(range(program.width), rng.randrange(1, 4))
        kind = rng.randrange(4)
        if kind == 0:
            program.mcx(*qubits)
        elif kind == 1:
            program.mcz(*qubits)
        elif kind == 2 or not program.measurements:
            program.hmr(qubits[0])
        else:
            program.mcz_if(rng.randrange(program.measurements), *qubits)
    width, offset = (128, 65) if wide else (6, 3)
    native = make_algebra("zdd-native-wide" if wide else "zdd-native", width)
    python = make_algebra("zdd", width)
    expected = _hmr_reference(program, python, offset)
    observed = native.simulate_hmr(program, offset)
    for native_roots, python_roots in zip((observed[0], [observed[1]], observed[2]),
                                         (expected[0], [expected[1]], expected[2])):
        assert [native.to_anf(r) for r in native_roots] == [python.to_anf(r) for r in python_roots]
    # An output X after the original program must change that physical output.
    prior = observed[0][0]
    program.x(0)
    mutated = native.simulate_hmr(program, offset)
    assert native.xor(prior, mutated[0][0]) == 1
    assert native.stats.gates == 2 * len(program.ops) - 1


def test_hmr_low_level_rejects_bad_events_buffers_and_budget():
    algebra = make_algebra("zdd-native", 2)
    x = algebra.variable(0)
    manager = algebra.manager
    with pytest.raises(ValueError, match="fresh"):
        manager.simulate_hmr([x, 0, 0], 0, [], [2], [0], [0, 1], [1])
    with pytest.raises(ValueError, match="feedback"):
        manager.simulate_hmr([x, 0, 0], 0, [], [3], [0], [0, 1], [0])
    with pytest.raises(ValueError, match="opcode"):
        manager.simulate_hmr([x], 0, [], [4], [0], [0, 1], [0xFFFFFFFF])
    with pytest.raises(ValueError, match="physical"):
        manager.simulate_hmr([x], 0, [], [0], [2], [0, 1], [0xFFFFFFFF])
    small = make_algebra("zdd-native", 2, Budget(max_nodes=1))
    with pytest.raises(ResourceLimitExceeded, match="nodes"):
        small.simulate_hmr(PhaseProgram(2).cx(0, 1))


def test_clone_live_dag_does_not_expand_exponential_family():
    algebra = make_algebra("zdd-native-wide", 128, Budget(max_terms=1))
    family = 1
    for q in range(128):
        family = algebra.product((family, algebra.xor(1, algebra.variable(q))))
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        algebra.to_anf(family)
    before = algebra.reachable_union([family])
    old_manager = algebra.manager
    (copied,) = algebra.collect_roots([family])
    assert algebra.manager is not old_manager
    assert algebra.node_count == before["live"] == 128
    assert algebra.terms(copied) == 2**63 - 1
    assert algebra.min_monomial(copied) == 0
    assert algebra.memory_info()["collections"] == 1
    assert old_manager.terms(family) == algebra.terms(copied)


def test_clone_preserves_sharing_pins_and_original_on_failure():
    algebra = make_algebra("zdd-native-wide", 80, order=list(reversed(range(80))))
    root = algebra.product((algebra.variable(0), algebra.variable(79)))
    other = algebra.xor(root, algebra.variable(64))
    expected = [algebra.to_anf(r) for r in [root, other, root, 0, 1]]
    roots = algebra.collect_roots([root, other, root, 0, 1])
    assert [algebra.to_anf(r) for r in roots] == expected
    assert roots[0] == roots[2]
    original = algebra.manager
    with pytest.raises(ValueError, match="outside this manager"):
        algebra.collect_roots([10**9])
    assert algebra.manager is original
    info = algebra.memory_info()
    assert info["manager_bytes"] >= sum(info[key] for key in
        ["nodes_bytes", "unique_bytes", "cache_bytes", "terms_bytes", "minimum_bytes", "order_bytes"])


def test_binding_guard_renews_deadline_and_keeps_roots():
    algebra = make_algebra("zdd-native", 2)
    x = algebra.variable(0)
    expired = Guard(Budget(max_seconds=0.001))
    # Deterministically expire this deadline, without relying on a timing race.
    expired._deadline = time.perf_counter() - 1
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        algebra.bind_guard(expired)
    algebra.bind_guard(Guard(Budget(max_seconds=10)))
    assert algebra.min_monomial(x) == 1
    algebra.bind_guard(Guard(Budget(max_nodes=1)))
    with pytest.raises(ResourceLimitExceeded, match="nodes"):
        algebra.variable(1)


def test_collection_reserves_old_and_new_live_nodes_in_one_session():
    algebra = make_algebra("zdd-native", 2)
    root = algebra.product((algebra.variable(0), algebra.variable(1)))
    original = algebra.manager
    live = algebra.reachable_union([root])["live"]
    before = algebra.node_count
    assert live <= before
    with VerificationSession(Budget(max_nodes=before)) as session:
        session.reserve(original, nodes=before)
        with pytest.raises(ResourceLimitExceeded, match="nodes"):
            algebra.collect_roots([root])
        assert algebra.manager is original
        assert session.reservation(original) == (before, 0)
    with VerificationSession(Budget(max_nodes=before + live)) as session:
        session.reserve(original, nodes=before)
        (copied,) = algebra.collect_roots([root])
        assert algebra.to_anf(copied) == ANF(frozenset({3}))
        assert session.peaks["resident_nodes"] == before + live
        assert session.reservation(original) is None
        assert session.reservation(algebra.manager)[0] == live


def test_native_batch_failures_leave_owned_roots_and_reservations_valid():
    algebra = make_algebra("zdd-native", 4, Budget(max_nodes=1))
    root = algebra.variable(0)
    with pytest.raises(ResourceLimitExceeded, match="nodes"):
        algebra.rename_many([root], [2, 1, 0, 3])
    assert algebra.to_anf(root) == ANF(frozenset({1}))

    algebra = make_algebra("zdd-native", 4)
    root = algebra.product((algebra.variable(0), algebra.variable(1)))
    original = algebra.manager
    algebra.bind_guard(Guard(Budget(max_nodes=1)))
    with VerificationSession(Budget(max_nodes=10)) as session:
        session.reserve(original, nodes=original.node_count())
        previous = session.reservation(original)
        with pytest.raises(ResourceLimitExceeded, match="nodes"):
            algebra.collect_roots([root])
        assert session.reservation(original) == previous
        assert algebra.manager is original
        assert algebra.collections == 0
        assert algebra.to_anf(root) == ANF(frozenset({3}))


def test_new_native_methods_refuse_a_busy_manager():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from symq.generators import random_circuit

    algebra = make_algebra("zdd-native", 12)
    x = algebra.variable(0)
    manager = algebra.manager
    finished = threading.Event()
    calls = [lambda: manager.rename_many([x], list(range(12))),
             lambda: manager.clone_roots([x]), lambda: manager.memory_info(),
             lambda: manager.bind_budget(0.0, 0.0, 0.0, 0, 0),
             lambda: manager.simulate_hmr([x], 0, [], [], [], [0], [])]
    refused = [False] * len(calls)

    def run():
        try:
            algebra.simulate(random_circuit(12, 70, random.Random(5), max_controls=4))
        finally:
            finished.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(run)
        try:
            while not finished.is_set() and not all(refused):
                for i, call in enumerate(calls):
                    try:
                        call()
                    except RuntimeError as error:
                        assert "another thread" in str(error)
                        refused[i] = True
        finally:
            worker.result()
    assert all(refused)
