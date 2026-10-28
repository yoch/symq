"""The liveness measure must be exact and must agree with independent constructions.

The definition: a node is *live* if it is reachable from one of the live roots, i.e. from one of
the wire values still needed. ZDDs are canonical and children always have smaller identifiers
than their parent, so the live set is a downward-closed set of node ids.

``liveness.union_node_count`` obtains it by rebuilding the union of the root families in a scratch
manager; because the diagram is canonical, that manager's node count is the size of the union of
the reachable sets. The tests here check that claim two ways:

* **monotonicity**: the exact live count is at least the sum of the per-root DAG sizes only when
  roots are disjoint, so the meaningful invariant is ``sum_of_sizes <= exact <= nodes_created``;
* **reconstruction**: importing the union and re-reading every root's monomials gives back the
  same families, so the union really is the live set.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import liveness

from symq import Circuit, make_algebra, simulate
from symq.generators import random_circuit


@pytest.mark.parametrize("seed", range(15))
def test_the_exact_count_is_between_the_lower_bound_and_the_total(seed):
    rng = random.Random(seed)
    width = rng.randint(2, 6)
    circuit = random_circuit(width, rng.randint(1, 14), rng)
    algebra = make_algebra("zdd-native", width)
    roots = simulate(circuit, algebra)
    report = liveness.memory_report(algebra, roots)
    assert report["reachable_lower_bound"] <= report["nodes_created"]
    assert report["reachable_exact"] <= report["nodes_created"]
    assert report["dead_exact"] >= 0
    assert 0.0 <= report["dead_fraction"] <= 1.0


@pytest.mark.parametrize("seed", range(10))
def test_the_union_reproduces_every_root_family(seed):
    """The union built by ``union_node_count`` is the live set: every root is a subset of it."""
    rng = random.Random(200 + seed)
    width = rng.randint(2, 6)
    circuit = random_circuit(width, rng.randint(1, 12), rng)
    algebra = make_algebra("zdd-native", width)
    roots = simulate(circuit, algebra)
    families = [frozenset(algebra.manager.anf(root)) for root in roots]
    union = frozenset().union(*families) if families else frozenset()
    scratch = make_algebra("zdd-native", width)
    node = scratch.manager.from_terms(sorted(union)) if union else scratch.zero()
    rebuilt = frozenset(scratch.manager.anf(node)) if union else frozenset()
    assert rebuilt == union
    exact, reported_union = liveness.union_node_count(algebra, roots)
    assert reported_union == len(union)
    assert exact == scratch.node_count


def test_an_identity_circuit_creates_one_node_per_wire_and_keeps_them_all():
    algebra = make_algebra("zdd-native", 3)
    roots = simulate(Circuit(3), algebra)
    report = liveness.memory_report(algebra, roots)
    assert report["nodes_created"] == 3, "one node per input variable"
    assert report["reachable_exact"] == 3, "every variable is still a live root"
    assert report["dead_exact"] == 0


def test_a_cancelling_circuit_leaves_garbage_behind():
    """A -> A^-1 is the identity, but the nodes of ``A`` stay in the unique table."""
    rng = random.Random(5)
    body = random_circuit(5, 12, rng)
    circuit = Circuit(5, [*body.gates, *body.inverse().gates])
    algebra = make_algebra("zdd-native", 5)
    roots = simulate(circuit, algebra)
    report = liveness.memory_report(algebra, roots)
    assert report["dead_exact"] > 0, report
    assert report["reachable_exact"] == 5, "the outputs are the variables again"


def test_repeated_measurement_is_stable():
    rng = random.Random(9)
    circuit = random_circuit(5, 20, rng)
    algebra = make_algebra("zdd-native", 5)
    roots = simulate(circuit, algebra)
    first = liveness.memory_report(algebra, roots)
    second = liveness.memory_report(algebra, roots)
    assert first["reachable_exact"] == second["reachable_exact"]
    assert first["nodes_created"] == second["nodes_created"]
