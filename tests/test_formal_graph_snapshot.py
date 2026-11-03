"""Adversarial contract tests for the development-only Python→Lean data seam."""
from __future__ import annotations

import copy
import random

import pytest

from symq.labs import kraus_graph
from symq.labs.anchored_kraus import Limit
from symq.labs.kraus_graph import Graph
from symq.resources import Budget, Guard
from tools.formal_graph_snapshot import (
    InvalidGraphSnapshot,
    evaluate_snapshot,
    validate_graph_shape,
)


def example_graph():
    graph = Graph(Guard(Budget(max_seconds=10)))
    a = graph.var(0)
    b = graph.var(1)
    p = graph.mul(a, -b)
    c = graph.var(2)  # A late source input is legal.
    root = graph.xor(p, c)
    return graph, root


def test_snapshot_canonical_and_independent_scalar_replay():
    for seed in range(80):
        rng = random.Random(seed + 17101)
        graph, root = example_graph()
        refs = [graph.var(i) for i in range(3)] + [root]
        for _ in range(7):
            a, b = rng.sample(refs, 2)
            a *= rng.choice((-1, 1))
            b *= rng.choice((-1, 1))
            refs.append(graph.mul(a, b) if rng.randrange(2) else graph.xor(a, b))
        for candidate in (*refs, -refs[-1], 1, -1):
            snapshot, identity = validate_graph_shape(
                graph.nodes, graph.variables, graph.unique, candidate
            )
            snapshot2, identity2 = validate_graph_shape(
                graph.nodes, graph.variables, graph.unique, candidate
            )
            assert identity == identity2 and snapshot == snapshot2
            assert snapshot["clauses"][0] == [1]
            assert snapshot["assumption"] == candidate
            for source in range(8):
                assert evaluate_snapshot(snapshot, source) == graph.evaluate(candidate, source)


def test_forged_graph_forms_are_rejected_before_any_claim():
    graph, root = example_graph()
    cases = []
    n = copy.deepcopy(graph.nodes)
    n[1] = ("false",)
    cases.append((n, graph.variables, graph.unique, root))
    n = copy.deepcopy(graph.nodes)
    n[3] = ("var", 0)  # duplicate logical input
    cases.append((n, graph.variables, graph.unique, root))
    n = copy.deepcopy(graph.nodes)
    n[3] = ("var", -1)
    cases.append((n, graph.variables, graph.unique, root))
    n = copy.deepcopy(graph.nodes)
    n[3] = ("and", -3, 2)  # self/future reference
    cases.append((n, graph.variables, graph.unique, root))
    n = copy.deepcopy(graph.nodes)
    n[3] = ("and", True, 2)  # bool is not a wire index
    cases.append((n, graph.variables, graph.unique, root))
    n = copy.deepcopy(graph.nodes)
    n[3] = ("reset", 2)
    cases.append((n, graph.variables, graph.unique, root))
    n = copy.deepcopy(graph.nodes)
    n[3] = ("xor", -2, 3)
    cases.append((n, graph.variables, graph.unique, root))
    cases.append((graph.nodes, {}, graph.unique, root))
    cases.append((graph.nodes, graph.variables, {}, root))
    cases.append((graph.nodes, graph.variables, graph.unique, 0))
    cases.append((graph.nodes, graph.variables, graph.unique, len(graph.nodes)))
    cases.append((graph.nodes, graph.variables, graph.unique, True))
    for nodes, variables, unique, candidate in cases:
        with pytest.raises(InvalidGraphSnapshot):
            validate_graph_shape(nodes, variables, unique, candidate)


def test_snapshot_rejects_python_bool_and_duplicate_key_aliases():
    graph, root = example_graph()
    graph.var(True)
    with pytest.raises(InvalidGraphSnapshot):
        validate_graph_shape(graph.nodes, graph.variables, graph.unique, root)
    graph2, root2 = example_graph()
    graph2.var(-1)
    with pytest.raises(InvalidGraphSnapshot):
        validate_graph_shape(graph2.nodes, graph2.variables, graph2.unique, root2)


def test_snapshot_matches_real_incremental_solver_clause_stream(monkeypatch):
    class RecordingSolver:
        def __init__(self):
            self.clauses = []
            self.assumptions = []

        def add_clause(self, clause):
            self.clauses.append(list(clause))

        def clear_interrupt(self):
            pass

        def interrupt(self):
            pass

        def solve_limited(self, *, assumptions, expect_interrupt):
            assert expect_interrupt
            self.assumptions.append(list(assumptions))
            return None  # deliberate inconclusive, never a false proof

        def delete(self):
            pass

    recorded = RecordingSolver()
    monkeypatch.setattr(kraus_graph, "_new_solver", lambda: recorded)
    graph, root = example_graph()
    snapshot, _ = validate_graph_shape(graph.nodes, graph.variables, graph.unique, root)
    with pytest.raises(Limit):
        graph.witness(root)
    assert recorded.clauses == snapshot["clauses"]
    assert recorded.assumptions == [[root]]

    later = graph.xor(root, -graph.var(0))
    snapshot2, _ = validate_graph_shape(graph.nodes, graph.variables, graph.unique, later)
    with pytest.raises(Limit):
        graph.witness(later)
    assert recorded.clauses == snapshot2["clauses"]
    assert recorded.assumptions == [[root], [later]]
    graph.close()
