"""Bounded hash-consed Boolean DAG and exact incremental Glucose queries.

Research algebra for anchored_stream: no ANF expansion or branch enumeration.
UNSAT trusts the encoding and solver (no LRAT claim). Every SAT assignment is
checked by a separate DAG evaluator, then the caller replays the real source.
"""
from __future__ import annotations

import time
from threading import Timer

from symq.errors import InternalInconsistency, SatUnavailable
from symq.labs.anchored_kraus import Limit


def _new_solver():
    try:
        from pysat.solvers import Glucose4
    except ImportError as error:
        raise SatUnavailable('install python-sat for the research SAT algebra') from error
    return Glucose4()


class Graph:
    # Signed node references are complemented edges. Node 1 is the true constant.
    one, zero = 1, -1

    def __init__(self, guard, max_nodes=100000, max_clauses=500000):
        self.guard, self.max_nodes, self.max_clauses = guard, max_nodes, max_clauses
        self.nodes = [None, ('one',)]
        self.unique, self.variables, self.anchored = {}, {}, {1: 1}
        self.anchor_context = None
        self.solver = None
        self.encoded, self.clauses, self.queries, self.sat_calls = 1, 0, 0, 0
        self.peak_roots = 0

    def check(self):
        self.guard.check_time()
        if len(self.nodes) - 1 > self.max_nodes:
            raise Limit('Boolean DAG nodes')

    def _node(self, key):
        self.check()
        known = self.unique.get(key)
        if known is not None:
            return known
        if len(self.nodes) > self.max_nodes:
            raise Limit('Boolean DAG nodes')
        result = len(self.nodes)
        self.nodes.append(key)
        self.unique[key] = result
        return result

    def var(self, index):
        node = self._node(('var', index))
        self.variables[index] = node
        return node

    def xor(self, a, b):
        self.check()
        if a == b:
            return self.zero
        if a == -b:
            return self.one
        if abs(a) == 1:
            return b if a == self.zero else -b
        if abs(b) == 1:
            return a if b == self.zero else -a
        sign = -1 if (a < 0) != (b < 0) else 1
        a, b = sorted((abs(a), abs(b)))
        # Common compute/uncompute cancellation, not a heuristic proof.
        for node, other in ((a, b), (b, a)):
            key = self.nodes[node]
            if key[0] == 'xor' and other in key[1:]:
                return sign * (key[2] if key[1] == other else key[1])
        return sign * self._node(('xor', a, b))

    def mul(self, a, b):
        self.check()
        if a == self.zero or b == self.zero or a == -b:
            return self.zero
        if a == self.one or a == b:
            return b
        if b == self.one:
            return a
        return self._node(('and', *sorted((a, b))))

    def all(self, values):
        result = self.one
        for value in values:
            result = self.mul(result, value)
        return result

    def anchor(self, value, width, basis):
        context = (width, basis)
        if self.anchor_context not in (None, context):
            raise ValueError('one physical anchor per graph')
        self.anchor_context = context
        # Original children precede parents, including across incremental calls.
        for node in range(2, abs(value) + 1):
            self.check()
            if node in self.anchored:
                continue
            key = self.nodes[node]
            if key[0] == 'var':
                index = key[1]
                self.anchored[node] = (self.one if basis >> index & 1 else self.zero) if index < width else node
            else:
                a, b = key[1:]
                aa = self.anchored[abs(a)] * (1 if a > 0 else -1)
                bb = self.anchored[abs(b)] * (1 if b > 0 else -1)
                self.anchored[node] = self.mul(aa, bb) if key[0] == 'and' else self.xor(aa, bb)
        return self.anchored[abs(value)] * (1 if value > 0 else -1)

    def retained(self, values):
        self.peak_roots = max(self.peak_roots, len(values))
        self.check()

    def _clauses_for(self, node):
        key = self.nodes[node]
        if key[0] == 'var':
            return []
        a, b = key[1:]
        if key[0] == 'and':
            return [[-node, a], [-node, b], [node, -a, -b]]
        return [[-a, -b, -node], [a, b, -node], [a, -b, node], [-a, b, node]]

    def _append(self, clauses):
        self.guard.check_time()
        self.guard.check_terms(self.clauses + len(clauses))
        if self.clauses + len(clauses) > self.max_clauses:
            raise Limit('CNF clauses')
        for clause in clauses:
            self.solver.add_clause(clause)
            self.clauses += 1
            self.guard.check_time()

    def evaluate(self, expression, assignment):
        values = [False, True]
        for key in self.nodes[2:abs(expression) + 1]:
            self.check()
            if key[0] == 'var':
                value = bool(assignment >> key[1] & 1)
            else:
                a, b = key[1:]
                aa, bb = values[abs(a)] != (a < 0), values[abs(b)] != (b < 0)
                value = aa and bb if key[0] == 'and' else aa != bb
            values.append(value)
        return values[abs(expression)] != (expression < 0)

    def witness(self, expression):
        self.check()
        self.queries += 1
        if expression == self.zero:
            return None
        if expression == self.one:
            return 0
        if self.solver is None:
            self.solver = _new_solver()
            self._append([[1]])
        for node in range(self.encoded + 1, len(self.nodes)):
            self._append(self._clauses_for(node))
            self.encoded = node
        self.check()
        self.solver.clear_interrupt()
        remaining = self.guard.deadline - time.perf_counter()
        if remaining <= 0:
            raise Limit('SAT deadline')
        timer = Timer(remaining, self.solver.interrupt)
        timer.daemon = True
        timer.start()
        try:
            self.sat_calls += 1
            answer = self.solver.solve_limited(assumptions=[expression], expect_interrupt=True)
            self.check()
            if answer is None:
                raise Limit('SAT undecided or interrupted')
            if answer is False:
                return None
            model = self.solver.get_model()
            if model is None:
                raise InternalInconsistency('SAT returned no model')
            positive = {lit for lit in model if lit > 0}
            assignment = sum(1 << i for i, node in self.variables.items() if node in positive)
            if not self.evaluate(expression, assignment):
                raise InternalInconsistency('SAT assignment failed DAG replay')
            self.check()
            return assignment
        finally:
            timer.cancel()
            timer.join()

    def close(self):
        if self.solver is not None:
            self.solver.delete()
            self.solver = None

    def metrics(self):
        return {'graph_nodes': len(self.nodes) - 1, 'cnf_clauses': self.clauses,
                'queries': self.queries, 'sat_calls': self.sat_calls,
                'peak_live_roots': self.peak_roots}
