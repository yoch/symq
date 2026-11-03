"""Independent Python mirror of the formal AND/XOR gate-to-CNF contract.

Not a formal equivalence between Python's code and Lean's model: this is the
cross-language conformance check accompanying the universal Lean theorem.
"""
from __future__ import annotations

import random
from itertools import product

from symq.labs.kraus_graph import Graph
from symq.resources import Budget, Guard


def clauses_for(node, kind, a, b):
    if kind == "and":
        return [[-node, a], [-node, b], [node, -a, -b]]
    assert kind == "xor"
    return [[-a, -b, -node], [a, b, -node], [a, -b, node], [-a, b, node]]


def literal(values, signed):
    return values[abs(signed)] if signed > 0 else not values[abs(signed)]


def sat(clauses, values):
    return all(any(literal(values, x) for x in c) for c in clauses)


def test_literal_polarity_and_gate_cnf_exact_for_all_small_truth_tables():
    count = 0
    for op, sa, sb in product(("and", "xor"), (-1, 1), (-1, 1)):
        graph = Graph(Guard(Budget(max_seconds=10)))
        a, b = graph.var(0), graph.var(1)
        if op == "and":
            graph.mul(sa * a, sb * b)
        else:
            graph.xor(sa * a, sb * b)
        node = len(graph.nodes) - 1
        kind, aa, bb = graph.nodes[node]
        assert kind == op
        assert graph._clauses_for(node) == clauses_for(node, kind, aa, bb)
        for x, y, z in product((False, True), repeat=3):
            values = {1: True, a: x, b: y, node: z}
            expected = (
                literal(values, aa) and literal(values, bb)
                if kind == "and" else literal(values, aa) != literal(values, bb)
            )
            assert sat(graph._clauses_for(node), values) == (z == expected)
            count += 1
    assert count == 64


def test_mixed_signed_graphs_match_independent_scalar_interpreter():
    rng = random.Random(31621)
    for _ in range(80):
        graph = Graph(Guard(Budget(max_seconds=10)))
        available = [graph.var(i) for i in range(4)]
        for _ in range(12):
            a, b = rng.sample(available, 2)
            a *= rng.choice((-1, 1))
            b *= rng.choice((-1, 1))
            result = graph.xor(a, b) if rng.randrange(2) else graph.mul(a, b)
            available.append(result)
        for state in range(16):
            values = {1: True}
            for node, key in enumerate(graph.nodes[2:], 2):
                if key[0] == "var":
                    values[node] = bool(state >> key[1] & 1)
                    assert graph._clauses_for(node) == []
                else:
                    kind, a, b = key
                    va, vb = literal(values, a), literal(values, b)
                    values[node] = va and vb if kind == "and" else va != vb
                    clauses = graph._clauses_for(node)
                    assert clauses == clauses_for(node, kind, a, b)
                    assert sat(clauses, values)
                    altered = {**values, node: not values[node]}
                    assert not sat(clauses, altered)
                assert graph.evaluate(node, state) == values[node]
            for root in available:
                assert graph.evaluate(root, state) == literal(values, root)


def test_reject_wrong_xor_polarity_and_output_assertion():
    graph = Graph(Guard(Budget(max_seconds=5)))
    a, b = graph.var(0), graph.var(1)
    r = graph.xor(a, b)
    clauses = graph._clauses_for(r)
    for x, y in product((False, True), repeat=2):
        expected = x != y
        values = {1: True, a: x, b: y, r: expected}
        assert sat(clauses, values)
        values[r] = not expected
        assert not sat(clauses, values)
