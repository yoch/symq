"""Targeted conformance checks for graph simplifications in the formal model.

Every positive result concerns the actual Python graph object; Lean's universal
Boolean identities are checked separately, without Lean at runtime.
"""
from __future__ import annotations

from itertools import product

from symq.labs.kraus_graph import Graph
from symq.resources import Budget, Guard


def scalar(ref, bits):
    node = abs(ref)
    return bits[node] if ref > 0 else not bits[node]


def test_xor_cancellation_with_all_signed_operands_and_truth_assignments():
    for sa, sb in product((-1, 1), repeat=2):
        g = Graph(Guard(Budget(max_seconds=5)))
        x, y = g.var(0), g.var(1)
        a, b = sa * x, sb * y
        n = g.xor(a, b)
        back_a = g.xor(n, b)
        back_b = g.xor(n, a)
        for xval, yval in product((False, True), repeat=2):
            assignment = int(xval) | (int(yval) << 1)
            assert g.evaluate(n, assignment) == (g.evaluate(a, assignment) != g.evaluate(b, assignment))
            assert g.evaluate(back_a, assignment) == g.evaluate(a, assignment)
            assert g.evaluate(back_b, assignment) == g.evaluate(b, assignment)
        # Hash-consing identical normalized inputs must not add nodes.
        count = len(g.nodes)
        assert g.xor(a, b) == n
        assert len(g.nodes) == count


def test_mul_shortcuts_are_semantically_exact():
    for sx, sy in product((-1, 1), repeat=2):
        g = Graph(Guard(Budget(max_seconds=5)))
        x, y = g.var(0), g.var(1)
        a, b = sx * x, sy * y
        roots = [
            (g.mul(a, b), lambda p, q: p and q),
            (g.mul(a, a), lambda p, q: p),
            (g.mul(a, -a), lambda p, q: False),
            (g.mul(a, g.one), lambda p, q: p),
            (g.mul(a, g.zero), lambda p, q: False),
        ]
        for p, q in product((False, True), repeat=2):
            assignment = int(p) | (int(q) << 1)
            va = g.evaluate(a, assignment)
            vb = g.evaluate(b, assignment)
            for root, fn in roots:
                assert g.evaluate(root, assignment) == fn(va, vb)


def test_late_input_registration_and_hashcons_are_not_quietly_assumed_ordered():
    g = Graph(Guard(Budget(max_seconds=5)))
    a, b = g.var(0), g.var(1)
    old = g.mul(a, b)
    late = g.var(2)
    root = g.xor(old, late)
    assert abs(late) > abs(old)  # variable creation may follow an AND gate
    for x, y, z in product((False, True), repeat=3):
        assignment = int(x) | (int(y) << 1) | (int(z) << 2)
        assert g.evaluate(root, assignment) == ((x and y) != z)
    assert g.mul(b, a) == old
