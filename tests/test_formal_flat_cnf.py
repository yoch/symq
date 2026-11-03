"""Adversarial conformance of physical Graph clause IDs, assumptions and pins.

Independent brute-force over auxiliary nodes. These *tests* compare Python
against scalar graph semantics; Lean's formal flat-CNF theorem is separate.
"""
from __future__ import annotations

import itertools
import random

import pytest

from symq.labs.kraus_graph import Graph
from symq.resources import Budget, Guard


def formula_true(clauses, values):
    return all(any(values[abs(lit)] == (lit > 0) for lit in clause) for clause in clauses)


def manual_gate_clauses(node, record):
    kind = record[0]
    if kind == "var":
        return []
    a, b = record[1:]
    if kind == "and":
        return [[-node, a], [-node, b], [node, -a, -b]]
    assert kind == "xor"
    return [[-a, -b, -node], [a, b, -node],
            [a, -b, node], [-a, b, node]]


def graph_formula(graph):
    clauses = [[1]]  # The runtime's initial SAT constant clause.
    for node in range(2, len(graph.nodes)):
        actual = graph._clauses_for(node)
        assert actual == manual_gate_clauses(node, graph.nodes[node])
        clauses.extend(actual)
    return clauses


def all_extensions(graph, state, clauses):
    variable_ids = set(graph.variables.values())
    auxiliary = [i for i in range(2, len(graph.nodes)) if i not in variable_ids]
    pins = [[node if (state >> bit) & 1 else -node]
            for bit, node in sorted(graph.variables.items())]
    answers = []
    for assignment in itertools.product((False, True), repeat=len(auxiliary)):
        values = {1: True}
        values.update({node: bool(state >> bit & 1) for bit, node in graph.variables.items()})
        values.update(zip(auxiliary, assignment))
        if formula_true(clauses + pins, values):
            answers.append(values)
    return answers


def build_graph(seed):
    rng = random.Random(seed)
    g = Graph(Guard(Budget(max_seconds=10)))
    a, b = g.var(0), g.var(1)
    nodes = [a, b]
    for step in range(5):
        if step == 2:
            nodes.append(g.var(2))  # input created AFTER early internal gates
        x, y = rng.sample(nodes, 2)
        x *= rng.choice((-1, 1))
        y *= rng.choice((-1, 1))
        nodes.append(g.xor(x, y) if step & 1 else g.mul(x, y))
    return g, nodes


def test_complete_auxiliary_assignment_unique_for_every_fixed_input():
    total = 0
    for seed in range(36):
        graph, nodes = build_graph(seed)
        formula = graph_formula(graph)
        # The true-constant clause and unit input pins are distinct; the
        # runtime itself normally leaves source inputs free.
        assert formula[0] == [1]
        assert all(not c or all(abs(x) < len(graph.nodes) for x in c) for c in formula)
        for input_word in range(8):
            extensions = all_extensions(graph, input_word, formula)
            assert len(extensions) == 1, (seed, input_word, extensions)
            values = extensions[0]
            for node, record in enumerate(graph.nodes[2:], 2):
                if record[0] == "var":
                    assert values[node] == bool(input_word >> record[1] & 1)
                else:
                    assert values[node] == graph.evaluate(node, input_word)
            for root in nodes + [-nodes[-1], 1, -1]:
                expected = graph.evaluate(root, input_word)
                # An additional [root] clause is logically equivalent to an
                # SAT assumption; it is NOT a claim of the same emitted bytes.
                satisfies_root = [v for v in extensions
                                  if formula_true([[root]], v)]
                assert len(satisfies_root) == int(expected)
                total += 1
    assert total >= 36 * 8 * 5


def test_true_constant_and_signed_root_assumptions_are_essential():
    graph = Graph(Guard(Budget(max_seconds=5)))
    x, y = graph.var(0), graph.var(1)
    root = graph.xor(x, -y)
    clauses = graph_formula(graph)
    for input_word in range(4):
        ext = all_extensions(graph, input_word, clauses)
        assert len(ext) == 1
        correct = graph.evaluate(root, input_word)
        assert formula_true([[root if correct else -root]], ext[0])
        assert not formula_true([[-root if correct else root]], ext[0])
    # With the [1] true-constant unit removed, [-1] can coexist with empty
    # gate constraints: this demonstrates why the constant must be pinned.
    assert formula_true([[-1]], {1: False})
    assert not formula_true([[1], [-1]], {1: True})


def test_mutated_xor_clause_no_longer_matches_truth_table():
    graph = Graph(Guard(Budget(max_seconds=5)))
    x, y = graph.var(0), graph.var(1)
    root = graph.xor(x, y)
    clauses = manual_gate_clauses(root, graph.nodes[root])
    mutant = [list(c) for c in clauses]
    mutant[0][0] *= -1
    observed = 0
    for a, b, z in itertools.product((False, True), repeat=3):
        values = {1: True, x: a, y: b, root: z}
        expected = (z == (a != b))
        assert formula_true(clauses, values) == expected
        if formula_true(mutant, values) != expected:
            observed += 1
    assert observed > 0


def test_duplicate_input_key_reuses_one_physical_node():
    graph = Graph(Guard(Budget(max_seconds=5)))
    x = graph.var(0)
    assert graph.var(0) == x
    assert graph.variables == {0: x}
    assert graph.xor(x, x) == graph.zero
    assert len(graph.nodes) == 3


@pytest.mark.sat
def test_incremental_solver_matches_existential_source_semantics():
    # This uses actual Glucose via Graph.witness, not a mocked solver.
    # The tested property is SAT iff some source input produces the root.
    for seed in range(12):
        graph, nodes = build_graph(seed)
        for root in (nodes[-1], -nodes[-1], nodes[-2]):
            expected = any(graph.evaluate(root, x) for x in range(8))
            found = graph.witness(root)
            assert (found is not None) == expected, (seed, root, expected, found)
            if found is not None:
                assert graph.evaluate(root, found)

def test_unique_logical_input_names_even_with_late_creation():
    for seed in range(24):
        graph, _ = build_graph(seed)
        physical = [i for i, rec in enumerate(graph.nodes) if rec and rec[0] == "var"]
        names = [graph.nodes[i][1] for i in physical]
        assert len(names) == len(set(names))
        assert {graph.variables[name] for name in names} == set(physical)
        for name in names:
            old = len(graph.nodes)
            assert graph.var(name) == graph.variables[name]
            assert len(graph.nodes) == old
