"""Cross-check the bit-sliced phase accumulator against integer modular sums.

These are conformance tests for Python, not a formal Python-to-Lean refinement.
"""
from __future__ import annotations

import random

from symq.labs.kraus_graph import Graph
from symq.labs.nonlinear_phase_bits import _phase_bits
from symq.resources import Budget, Guard


def eval_predicate(polynomial, assignment):
    return sum(mask & assignment == mask for mask in polynomial) % 2


def test_phase_accumulator_carries_and_boolean_products():
    rng = random.Random(31622)
    cases = 0
    for k in (1, 2, 3, 4, 8, 12, 16):
        for _ in range(24):
            graph = Graph(Guard(Budget(max_seconds=10)))
            inputs = [graph.var(i) for i in range(3)]
            phase = {
                frozenset(rng.sample(range(8), rng.randrange(1, 9))):
                    rng.randrange(1 << k)
                for _ in range(6)
            }
            bits = _phase_bits(phase, inputs, k, graph)
            assert len(bits) == k
            for assignment in range(8):
                expected = sum(
                    coefficient * eval_predicate(polynomial, assignment)
                    for polynomial, coefficient in phase.items()
                ) % (1 << k)
                actual = sum(
                    int(graph.evaluate(node, assignment)) << i
                    for i, node in enumerate(bits)
                )
                assert actual == expected
                cases += 1
    assert cases == 7 * 24 * 8
