"""Seeded fuzzing of the native C core: random valid work, and random invalid calls.

``tests/test_zdd_native.py`` names the cases that were thought of. This file covers the ones that
were not, with fixed seeds so that a failure is reproducible from its seed alone. It runs in the
ordinary suite and, through ``tools/sanitize_native.py``, under AddressSanitizer and
UndefinedBehaviorSanitizer, where a memory error aborts the run instead of going unnoticed.

Two properties:

* **Differential.** On random circuits -- every width class up to 128 wires, with both sides of
  the 64-wire word boundary, random variable orders and cache modes -- the native core gives the
  same polynomials and the same node count as the pure-Python ZDD it mirrors. Under a random
  small budget it either gives that same result or raises ``ResourceLimitExceeded``; for node
  and term budgets the Python backend must make the same choice. After a refusal the manager is
  still usable.
* **Raw interface.** Whatever arguments the methods of ``NativeZDDManager`` are called with --
  out-of-range or foreign node ids, truncated or inconsistent gate arrays, huge or negative
  integers, wrong types -- the only outcomes are a return value or one of a short list of
  exceptions, and polynomials built beforehand are unchanged.
"""
from __future__ import annotations

import array
import random

import pytest

from symq import Budget, Circuit, ResourceLimitExceeded
from symq.backends import NativeZDDAlgebra, NativeZDDWideAlgebra, ZDDAlgebra, simulate
from symq.generators import random_circuit

pytestmark = pytest.mark.native

WIDTHS = (1, 2, 3, 5, 8, 12, 31, 32, 33, 63, 64, 65, 100, 127, 128)
CACHE_LIMITS = (None, 1, 2, 64, 4096)
SAFETY = {"max_seconds": 20.0, "max_nodes": 200_000}
"""Ceiling for the reference run: a case that needs more is not a fuzz case, it is a benchmark."""

DIFFERENTIAL_SEEDS = range(240)
RAW_SEEDS = range(40)
RAW_CALLS_PER_SEED = 150


def fuzz_case(seed: int) -> tuple[random.Random, Circuit, list[int] | None, int | None, bool]:
    rng = random.Random(seed)
    width = WIDTHS[seed % len(WIDTHS)]
    gates = rng.randint(0, 24 if width <= 12 else 10)
    controls = rng.choice([0, 1, 2, 3, min(width - 1, 6)])
    circuit = random_circuit(width, gates, rng, max_controls=min(controls, width - 1))
    order = None
    if rng.random() < 0.5:
        order = list(range(width))
        rng.shuffle(order)
    wide = width > 64 or rng.random() < 0.3
    return rng, circuit, order, rng.choice(CACHE_LIMITS), wide


def native_algebra(width: int, wide: bool, budget: Budget, order, cache_limit):
    cls = NativeZDDWideAlgebra if wide else NativeZDDAlgebra
    return cls(width, budget.start(), order=order, cache_limit=cache_limit)


def outcome(algebra, circuit: Circuit):
    """``("ok", ANFs, node count)`` or ``("refused", resource)``."""
    try:
        values = simulate(circuit, algebra)
        return "ok", tuple(algebra.to_anf(value) for value in values), algebra.node_count
    except ResourceLimitExceeded as refusal:
        return "refused", refusal.resource


def still_usable(algebra) -> None:
    """After a refusal the tables must be consistent: the basic operations still work."""
    algebra.bind_guard(Budget().start())
    variable = algebra.variable(0)
    assert algebra.to_anf(algebra.xor(variable, variable)) == algebra.to_anf(algebra.zero())
    assert algebra.terms(algebra.xor(variable, algebra.one())) == 2


@pytest.mark.parametrize("seed", DIFFERENTIAL_SEEDS)
def test_native_and_python_zdd_agree_on_a_random_case(seed):
    rng, circuit, order, cache_limit, wide = fuzz_case(seed)
    width = circuit.width
    reference = outcome(ZDDAlgebra(width, Budget(**SAFETY).start(), order=order), circuit)
    if reference[0] != "ok":
        pytest.fail(f"seed {seed}: the reference run exceeded the fuzz ceiling ({reference})")
    native = outcome(native_algebra(width, wide, Budget(**SAFETY), order, cache_limit), circuit)
    assert native == reference

    # The same case under a budget small enough to refuse part of the time.
    kind = rng.choice(["nodes", "terms", "bytes"])
    limit = {"nodes": rng.randint(1, 80), "terms": rng.randint(1, 24),
             "bytes": rng.choice([1, 1 << 12, 1 << 16, 1 << 20])}[kind]
    budget = Budget(**{f"max_{kind}": limit}, max_seconds=20.0)
    try:
        bounded = native_algebra(width, wide, budget, order, cache_limit)
    except ResourceLimitExceeded as refusal:  # the tables themselves exceed a tiny max_bytes
        assert kind == "bytes" and refusal.resource == "bytes"
        return
    bounded_outcome = outcome(bounded, circuit)
    if bounded_outcome[0] == "ok":
        assert bounded_outcome == reference
    else:
        assert bounded_outcome == ("refused", kind)
        still_usable(bounded)
    if kind != "bytes":  # max_bytes exists only for the native tables
        python = outcome(ZDDAlgebra(width, budget.start(), order=order), circuit)
        assert python[0] == bounded_outcome[0], (kind, limit, python, bounded_outcome)


def test_the_differential_cases_cover_what_they_claim():
    """A fuzz that never refuses, or never crosses 64 wires, would prove less than it says."""
    cases = [fuzz_case(seed) for seed in DIFFERENTIAL_SEEDS]
    widths = {circuit.width for _rng, circuit, _order, _cache, _wide in cases}
    assert widths == set(WIDTHS)
    assert any(order is not None for _rng, _circuit, order, _cache, _wide in cases)
    assert {cache for _rng, _circuit, _order, cache, _wide in cases} == set(CACHE_LIMITS)
    assert any(wide and circuit.width <= 64 for _rng, circuit, _order, _cache, wide in cases)
    assert any(len(gate.qubits) > 3 for _rng, circuit, _order, _cache, _wide in cases
               for gate in circuit.gates)


# --- raw interface -------------------------------------------------------------------------------

ALLOWED = (TypeError, ValueError, OverflowError, BufferError, ResourceLimitExceeded)
"""What an invalid call may raise. Anything else -- or a crash -- is a defect."""

INTEGERS = (-(2**63) - 1, -(2**31), -2, -1, 0, 1, 2, 3, 7, 8, 63, 64, 127, 128, 255, 2**16,
            2**31 - 1, 2**31, 2**32 - 2, 2**32 - 1, 2**32, 2**63 - 1, 2**63, 2**64, 10**30)
ARITIES = {
    "variable": 1, "xor": 2, "product": 2, "terms": 1, "anf": 1, "from_terms": 1,
    "min_monomial": 1, "size": 1, "rename": 2, "rename_many": 2, "clone_roots": 1,
    "memory_info": 0, "bind_budget": 6, "reachable_union": 1, "node_count": 0, "cache_info": 0,
    "simulate": 4, "simulate_hmr": 7,
}


def scalar(rng: random.Random, nodes: list[int]):
    choice = rng.random()
    if choice < 0.35:
        return rng.choice(nodes)
    if choice < 0.75:
        return rng.choice(INTEGERS)
    return rng.choice([None, True, 1.5, float("nan"), float("inf"), -0.0, "x", b"\x00\x01",
                       object(), (), [], {}, 3 + 4j])


def sequence(rng: random.Random, nodes: list[int]):
    items = [scalar(rng, nodes) if rng.random() < 0.3 else rng.choice(nodes + [0, 1, 2, 3, 7])
             for _ in range(rng.randint(0, 9))]
    shape = rng.random()
    if shape < 0.5:
        return items
    if shape < 0.65:
        return tuple(items)
    small = [item for item in items if type(item) is int and 0 <= item < 2**32]
    if shape < 0.85:
        return array.array("I", small)
    if shape < 0.9:
        return array.array("B", [item % 256 for item in small])
    if shape < 0.95:
        return bytes(item % 256 for item in small)
    return iter(items)


def argument(rng: random.Random, nodes: list[int]):
    return sequence(rng, nodes) if rng.random() < 0.45 else scalar(rng, nodes)


def gate_arrays(rng: random.Random, width: int):
    """A gate description that is valid most of the time, so the simulation itself is reached."""
    indices, offsets, targets = [], [0], []
    for _ in range(rng.randint(0, 5)):
        wires = rng.sample(range(width), rng.randint(1, min(width, 4)))
        indices.extend(wires[:-1])
        offsets.append(len(indices))
        targets.append(wires[-1])
    damage = rng.random()
    if damage < 0.15 and offsets:
        offsets[rng.randrange(len(offsets))] = rng.choice(INTEGERS)
    elif damage < 0.3 and indices:
        indices[rng.randrange(len(indices))] = rng.choice(INTEGERS)
    elif damage < 0.4:
        targets.append(rng.choice(INTEGERS))
    elif damage < 0.5:
        offsets.pop()
    wrap = rng.choice([list, tuple, "array"])
    if wrap == "array":
        try:
            return tuple(array.array("I", values) for values in (indices, offsets, targets))
        except (OverflowError, TypeError):
            return indices, offsets, targets
    return wrap(indices), wrap(offsets), wrap(targets)


def arguments(rng: random.Random, name: str, nodes: list[int], width: int) -> tuple:
    count = ARITIES[name]
    if rng.random() < 0.08:
        count = max(0, count + rng.choice([-1, 1]))
    if name == "simulate" and count == 4 and rng.random() < 0.8:
        state = rng.choice([None, None, [rng.choice(nodes) for _ in range(width)],
                            sequence(rng, nodes)])
        return (state, *gate_arrays(rng, width))
    if name in {"rename", "rename_many"} and count == 2 and rng.random() < 0.7:
        mapping = sorted(rng.randrange(width) for _ in range(width))
        if rng.random() < 0.3:
            mapping[rng.randrange(width)] = rng.choice(INTEGERS)
        roots = rng.choice(nodes) if name == "rename" else [rng.choice(nodes) for _ in range(3)]
        return roots, mapping
    if name == "bind_budget" and count == 6 and rng.random() < 0.7:
        # No deadline and no cap, so the calls that follow are not all refused for time.
        return (0.0, 0.0, 0.0, rng.choice([0, 0, 10**6, -1]), rng.choice([0, 0, 10**6, -1]),
                rng.choice([0, 0, 2**40, -1]))
    return tuple(argument(rng, nodes) for _ in range(count))


@pytest.mark.parametrize("seed", RAW_SEEDS)
def test_invalid_calls_raise_and_corrupt_nothing(seed):
    rng = random.Random(10_000 + seed)
    width = rng.choice([1, 4, 8, 64, 100])
    algebra = (NativeZDDWideAlgebra if width > 64 else NativeZDDAlgebra)(
        width, Budget(max_seconds=30.0).start(), cache_limit=rng.choice(CACHE_LIMITS))
    manager = algebra.manager
    other = NativeZDDAlgebra(3)
    foreign = other.from_terms({1, 2, 4, 7})
    # Fixed polynomials whose ANFs must survive every call below.
    terms = [frozenset(rng.randrange(1 << min(width, 20)) for _ in range(rng.randint(1, 6)))
             for _ in range(4)]
    kept = [algebra.from_terms(group) for group in terms]
    expected = [algebra.to_anf(value) for value in kept]
    nodes = [0, 1, *kept, foreign, manager.node_count() + 1, manager.node_count() + 2]
    names = sorted(ARITIES)
    raised = returned = 0
    for _ in range(RAW_CALLS_PER_SEED):
        name = rng.choice(names)
        try:
            result = getattr(manager, name)(*arguments(rng, name, nodes, width))
        except ALLOWED:
            raised += 1
            continue
        returned += 1
        if type(result) is int and 0 <= result <= manager.node_count() + 1:
            # Often a node id (xor, product, variable...), sometimes a count or a mask that
            # happens to be small: either way a plausible argument for the calls that follow.
            nodes.append(result)
    assert raised > 0 and returned > 0
    algebra.bind_guard(Budget(max_seconds=30.0).start())
    assert [algebra.to_anf(value) for value in kept] == expected
    assert other.to_anf(foreign) == other.to_anf(other.from_terms({1, 2, 4, 7}))
    still_usable(algebra)


# --- defects found by the tests above, as named regressions -----------------------------------

@pytest.mark.parametrize("mapping", [iter([0, 1, 2, 3]), {}, {0: 0}.keys(), (i for i in range(4))])
def test_rename_many_reports_bad_roots_before_touching_the_map(mapping):
    """Found by seeds 5 and 11 of the raw-interface fuzz.

    ``rename_many`` converted its second argument while the ``TypeError`` of the first was still
    pending. With an iterator or a mapping as the map, that conversion called back into Python
    with an exception set, and the call ended in ``SystemError`` instead of ``TypeError``.
    """
    manager = NativeZDDAlgebra(4).manager
    for roots in (3 + 4j, 8, None, 1.5):
        with pytest.raises(TypeError, match="roots must be a sequence"):
            manager.rename_many(roots, mapping)
    assert manager.rename_many([manager.variable(0)], [0, 1, 2, 3]) == [manager.variable(0)]
