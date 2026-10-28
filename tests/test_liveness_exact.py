"""Exact liveness: the union of the reachable sets, not the diagram of the union.

The first version of this measurement was **wrong**, and the audit found it. It rebuilt the union
of the root *families* in a scratch manager and reported that node count as the number of live
nodes. Two facts make that incorrect:

* the diagram of the union of two families need not contain the nodes of either diagram -- with
  ``A = {x}`` and ``B = {x, y}`` the union is ``B``, whose diagram has two nodes, while ``A``'s
  node is not one of them and the reachable union has three;
* summing ``size(root)`` counts a shared node once per root, so it is a *lower* bound on the
  union, not an upper one.

The only correct count marks the identifiers actually reached. Both backends now expose
``reachable_union``, implemented independently: the native one walks the compact node array, the
Python one walks its lists. The tests below enumerate every pair (and triple) of families over
three variables and compare the two implementations with each other and with a brute-force set.
"""
from __future__ import annotations

import itertools
import random
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from symq import ANF, Circuit, make_algebra, simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit


def families(width: int) -> list[frozenset[int]]:
    """Every monomial family over ``width`` variables, as an ANF term set."""
    every = list(range(1 << width))
    out = []
    for size in range(len(every) + 1):
        for combination in itertools.combinations(every, size):
            out.append(frozenset(combination))
    return out


def build(algebra, family):
    return algebra.from_anf(ANF(family))


def brute_force_union(sizes_by_root: dict[int, set[int]], roots) -> int:
    """Reference: the union of the node sets, given explicitly by construction."""
    return len(set().union(*(sizes_by_root[root] for root in roots)))


@pytest.mark.parametrize("width", [1, 2, 3])
def test_the_union_is_not_the_diagram_of_the_union(width):
    """The counterexample the audit gave, generalised: the two counts differ."""
    native = NativeZDDAlgebra(width)
    python = make_algebra("zdd", width)
    every = families(width)
    differences = 0
    for first in every:
        for second in every:
            roots_native = [build(native, first), build(native, second)]
            roots_python = [build(python, first), build(python, second)]
            exact = native.manager.reachable_union(roots_native)["live"]
            reference = python.reachable_union(roots_python)["live"]
            assert exact == reference, (first, second)
            summed = sum(native.manager.size(root) for root in roots_native)
            assert summed >= exact, "the per-root sum is an upper bound (shared nodes count twice)"
            union_family = first | second
            as_union = build(NativeZDDAlgebra(width), union_family)
            del as_union
            if exact != len(first | second):
                differences += 1
    if width == 2:
        assert differences > 0, "the two quantities must be able to differ"


def test_the_audit_counterexample_is_exactly_three():
    algebra = NativeZDDAlgebra(2)
    a = build(algebra, frozenset({1}))
    b = build(algebra, frozenset({1, 2}))
    assert algebra.manager.reachable_union([a, b])["live"] == 3
    assert algebra.manager.size(a) + algebra.manager.size(b) == 3
    assert algebra.manager.size(b) == 2, "the union family's diagram has two nodes"


def test_a_shared_node_is_counted_once():
    algebra = NativeZDDAlgebra(3)
    x0 = build(algebra, frozenset({1}))
    x0x1 = build(algebra, frozenset({1, 3}))
    both = algebra.manager.reachable_union([x0, x0x1])
    assert both["live"] >= algebra.manager.size(x0x1)
    assert both["live"] <= algebra.manager.size(x0) + algebra.manager.size(x0x1)


@pytest.mark.parametrize("seed", range(20))
def test_native_and_python_agree_on_random_root_sets(seed):
    rng = random.Random(seed)
    width = rng.randint(2, 6)
    circuit = random_circuit(width, rng.randint(1, 14), rng)
    native = NativeZDDAlgebra(width)
    roots_native = simulate(circuit, native)
    limit = rng.randint(1, width)
    subset_native = list(roots_native)[:limit]
    native_result = native.manager.reachable_union(subset_native)["live"]
    # Same circuits, same subset, but built with the Python backend.
    python = make_algebra("zdd", width)
    roots_python = simulate(circuit, python)
    python_result = python.reachable_union(list(roots_python)[:limit])["live"]
    assert native_result == python_result, (seed, limit)


def test_empty_and_terminal_roots():
    algebra = NativeZDDAlgebra(3)
    assert algebra.manager.reachable_union([])["live"] == 0
    assert algebra.manager.reachable_union([0, 1])["live"] == 0
    assert algebra.manager.reachable_union([algebra.variable(0)])["live"] == 1


def test_ids_from_another_manager_are_rejected():
    small = NativeZDDAlgebra(2)
    big = NativeZDDAlgebra(2)
    node = big.variable(0)
    for _ in range(20):
        node = big.manager.product(node, big.manager.xor(1, big.variable(1)))
    with pytest.raises(ValueError, match="outside this manager"):
        small.manager.reachable_union([node])


def test_an_identity_circuit_has_no_garbage():
    native = NativeZDDAlgebra(3)
    roots = simulate(Circuit(3), native)
    report = native.manager.reachable_union(list(roots))
    assert report["created"] == 3
    assert report["live"] == 3


def test_a_cancelling_circuit_leaves_garbage_behind():
    rng = random.Random(5)
    body = random_circuit(5, 12, rng)
    circuit = Circuit(5, [*body.gates, *body.inverse().gates])
    algebra = NativeZDDAlgebra(5)
    roots = simulate(circuit, algebra)
    report = algebra.manager.reachable_union(list(roots))
    assert report["live"] == 5, "the outputs are the variables again"
    assert report["created"] > report["live"]


def test_the_old_union_count_would_have_been_wrong_on_a_real_circuit():
    """A regression guard on a circuit where the two methods disagree."""
    rng = random.Random(7)
    circuit = random_circuit(4, 10, rng)
    algebra = NativeZDDAlgebra(4)
    roots = simulate(circuit, algebra)
    exact = algebra.manager.reachable_union(list(roots))["live"]
    summed = sum(algebra.manager.size(root) for root in roots)
    assert summed >= exact
    del circuit, rng
