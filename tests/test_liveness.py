"""Liveness of the native manager, on the corrected definition.

This file replaces the version that shipped with the first pilots, which measured the diagram of
the *union of the families* and called it the reachable set. The audit showed that is wrong: the
diagram of a union need not contain the nodes of either diagram. The corrected measurement is
``reachable_union``, an explicit marking walk over node identifiers.

What is kept from the original file is its purpose -- checking the *properties* a liveness measure
must have, on circuits rather than on hand-made families. What changed is the function under test
and, with it, the direction of every bound.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

from symq import Circuit, simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit


def report(algebra: NativeZDDAlgebra, roots) -> dict:
    return algebra.manager.reachable_union(list(roots))


@pytest.mark.parametrize("seed", range(15))
def test_the_bounds_have_the_right_direction(seed):
    """``size`` summed over roots is an upper bound; the created count bounds it from above."""
    rng = random.Random(seed)
    circuit = random_circuit(rng.randint(2, 6), rng.randint(1, 14), rng)
    algebra = NativeZDDAlgebra(circuit.width)
    roots = simulate(circuit, algebra)
    live = report(algebra, roots)["live"]
    summed = sum(algebra.manager.size(root) for root in roots)
    assert live <= summed, "the per-root sum double counts shared nodes"
    assert live <= algebra.node_count


@pytest.mark.parametrize("seed", range(10))
def test_the_live_set_contains_every_root(seed):
    """A root that is an internal node must itself be reachable, so the count is at least one
    per distinct non-terminal root."""
    rng = random.Random(100 + seed)
    circuit = random_circuit(rng.randint(2, 5), rng.randint(1, 10), rng)
    algebra = NativeZDDAlgebra(circuit.width)
    roots = simulate(circuit, algebra)
    distinct = {root for root in roots if root > 1}
    assert report(algebra, roots)["live"] >= len(distinct)


def test_an_identity_circuit_keeps_all_its_nodes():
    algebra = NativeZDDAlgebra(3)
    roots = simulate(Circuit(3), algebra)
    payload = report(algebra, roots)
    assert payload["created"] == 3
    assert payload["live"] == 3


def test_a_cancelling_circuit_leaves_garbage_behind():
    """``A ; A^{-1}`` is the identity, so the outputs are the variables and the rest is garbage."""
    rng = random.Random(5)
    body = random_circuit(5, 12, rng)
    circuit = Circuit(5, [*body.gates, *body.inverse().gates])
    algebra = NativeZDDAlgebra(5)
    roots = simulate(circuit, algebra)
    payload = report(algebra, roots)
    assert payload["live"] == 5
    assert payload["created"] > payload["live"]


def test_repeated_measurement_is_stable():
    rng = random.Random(9)
    circuit = random_circuit(5, 20, rng)
    algebra = NativeZDDAlgebra(5)
    roots = simulate(circuit, algebra)
    first = report(algebra, roots)
    second = report(algebra, roots)
    assert first["live"] == second["live"]
    assert first["created"] == second["created"]


def test_the_edges_count_is_two_per_live_node():
    """Every internal node has exactly two children, so the walk sees ``2 * live`` edges."""
    rng = random.Random(3)
    circuit = random_circuit(4, 10, rng)
    algebra = NativeZDDAlgebra(4)
    roots = simulate(circuit, algebra)
    payload = report(algebra, roots)
    assert payload["edges"] == 2 * payload["live"]
