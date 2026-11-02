"""Graph/CNF truth tables, actual SAT, negative replay and hostile solver outcomes."""
from __future__ import annotations

import random
from itertools import product

import pytest

from benchmarks.anchored_kraus import (
    contract,
    ideal,
    image,
    program,
    random_source,
    states,
)
from benchmarks.anchored_stream import dense_case
from symq.errors import InternalInconsistency, SatUnavailable
from symq.labs import kraus_graph
from symq.labs.anchored_stream import verify_stream
from symq.labs.kraus_graph import Graph
from symq.resources import Budget, Guard


def test_signed_dag_truth_tables_and_every_generated_clause():
    for op in ('xor', 'mul'):
        for sa, sb in product((-1, 1), repeat=2):
            graph = Graph(Guard(Budget(max_seconds=5)))
            a, b = graph.var(0), graph.var(1)
            root = getattr(graph, op)(sa * a, sb * b)
            for av, bv in product((False, True), repeat=2):
                assignment = int(av) | int(bv) << 1
                aa, bb = av != (sa < 0), bv != (sb < 0)
                expected = aa != bb if op == 'xor' else aa and bb
                assert graph.evaluate(root, assignment) == expected
                values = {1: True}
                values.update({i: graph.evaluate(i, assignment) for i in range(2, len(graph.nodes))})
                for i in range(2, len(graph.nodes)):
                    for clause in graph._clauses_for(i):
                        assert any(values[abs(lit)] != (lit < 0) for lit in clause)
                # Flipping a defined internal node invalidates at least one defining clause.
                if graph.nodes[abs(root)][0] != 'var':
                    wrong = {**values, abs(root): not values[abs(root)]}
                    assert not all(any(wrong[abs(lit)] != (lit < 0) for lit in c)
                                   for c in graph._clauses_for(abs(root)))


@pytest.mark.sat
def test_sat_channel_agreement_and_witnesses():
    rng = random.Random(933)
    for _ in range(60):
        src = random_source(rng)
        images = {(x, y): image(src, x, y) for x, y in product(range(8), repeat=2)}
        for table in product(range(2), repeat=2):
            for legal in ((0,), (1,), (0, 1)):
                spec = contract(table=table, legal=legal)
                inputs = states(spec)
                expected = all(images[x, y] == {(ideal(spec, x), ideal(spec, y)): 1}
                               for x, y in product(inputs, repeat=2))
                result = verify_stream(src, spec, backend='sat')
                assert result['status'] in ('equivalent', 'not_proved')
                assert (result['status'] == 'equivalent') == expected
                if not expected:
                    witness = result['witness']
                    x = witness['input']
                    y = x if result['obligation'] == 'outputs' else witness['anchor']
                    assert images[x, y] != {(ideal(spec, x), ideal(spec, y)): 1}


@pytest.mark.sat
def test_sat_decides_dense_anf_frontier_both_directions():
    for mutant in (False, True):
        src, spec = dense_case(32, mutant)
        assert verify_stream(src, spec, max_terms=5000)['status'] == 'inconclusive'
        result = verify_stream(src, spec, backend='sat', max_terms=5000)
        assert result['status'] == ('not_proved' if mutant else 'equivalent')
        assert result['graph_nodes'] <= 161 and result['cnf_clauses'] <= 319
        assert result['sat_calls'] == 1


def test_missing_solver_and_resource_limits_are_not_proofs(monkeypatch):
    def unavailable():
        raise SatUnavailable('injected dependency absence')

    monkeypatch.setattr(kraus_graph, '_new_solver', unavailable)
    src, spec = dense_case(3, True)
    assert verify_stream(src, spec, backend='sat')['status'] == 'unsupported'
    assert verify_stream(src, spec, backend='sat', max_graph_nodes=2)['status'] == 'inconclusive'


def test_unknown_or_fake_sat_model_cannot_refute(monkeypatch):
    class Solver:
        answer = None

        def add_clause(self, clause):
            pass

        def clear_interrupt(self):
            pass

        def interrupt(self):
            pass

        def delete(self):
            pass

        def get_model(self):
            return [1]  # all user inputs false: cannot satisfy a nonzero AND

        def solve_limited(self, **kwargs):
            return self.answer

    monkeypatch.setattr(kraus_graph, '_new_solver', Solver)
    src, spec = dense_case(3, True)
    assert verify_stream(src, spec, backend='sat')['status'] == 'inconclusive'
    Solver.answer = True
    with pytest.raises(InternalInconsistency):
        verify_stream(src, spec, backend='sat')


def test_invalid_backend_is_not_fallback():
    with pytest.raises(ValueError):
        verify_stream(program(3, 1), contract(), backend='auto')
