"""Research: wide XOR-table contracts with symbolic affine target correlations.

Targets are the injective image z=offset XOR B*u, not an enumerated value list.
All physical outputs are retained. Preparation at an external cut is not proved.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from symq.errors import ResourceLimitExceeded, SatUnavailable
from symq.labs import anchored_kraus as reference
from symq.labs import anchored_stream as stream
from symq.labs.resource_report import resource_report
from symq.resources import Budget, Guard, intersect_budgets


@dataclass(frozen=True)
class _TargetSpace:
    wires: tuple[int, ...]
    offset: int
    columns: tuple[int, ...]
    pivots: tuple[tuple[int, int], ...]

    def decode(self, parameters):
        word = self.offset
        for q, column in zip(self.wires, self.columns):
            if parameters >> q & 1:
                word ^= column
        mask = sum(1 << q for q in self.wires)
        return (parameters & ~mask) | sum(((word >> i & 1) << q)
                                          for i, q in enumerate(self.wires))

    def contains_physical(self, value):
        word = sum(((value >> q & 1) << i) for i, q in enumerate(self.wires)) ^ self.offset
        for pivot, vector in self.pivots:
            if word >> pivot & 1:
                word ^= vector
        return word == 0

    def initialize(self, initial, algebra):
        variables = [algebra.var(q) for q in self.wires[:len(self.columns)]]
        for i, q in enumerate(self.wires):
            value = algebra.one if self.offset >> i & 1 else algebra.zero
            for column, variable in zip(self.columns, variables):
                if column >> i & 1:
                    value = algebra.xor(value, variable)
            initial[q] = value


def _space(document, wires, guard):
    reference._object(document, 'kind offset columns')
    if document['kind'] != 'affine_image':
        raise ValueError('affine_image target space required')
    width = len(wires)
    reference._integer(document['offset'], 0, (1 << width) - 1)
    columns = document['columns']
    if type(columns) is not list or len(columns) > width:
        raise ValueError('at most target_width independent columns required')
    pivots = {}
    for column in columns:
        guard.check_time()
        reference._integer(column, 1, (1 << width) - 1)
        vector = column
        while vector:
            pivot = vector.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = vector
                break
            vector ^= pivots[pivot]
        if not vector:
            raise ValueError('target columns must be linearly independent')
    guard.check_terms(sum(c.bit_count() for c in columns))
    return _TargetSpace(tuple(wires), document['offset'], tuple(columns),
                        tuple(sorted(pivots.items(), reverse=True)))


def affine_target_from_equations(width, equations, *, budget=None):
    """Convert exact parity equations [mask, rhs] into an affine image over GF(2).

    A zero-dimensional image is one legal word; inconsistent equations are rejected.
    This converts a declared assumption, not a proof of how callers prepare it.
    """
    reference._integer(width, 1, 256)
    guard = Guard(budget)
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError('node/byte budgets unsupported')
    equations = stream._snapshot(equations, guard, 20000, [0])
    if type(equations) is not list or len(equations) > 4096:
        raise ValueError('at most 4096 parity equations required')
    pivots = {}
    for row in equations:
        guard.check_time()
        if type(row) is not list or len(row) != 2:
            raise ValueError('each parity equation is [mask, rhs]')
        mask, rhs = row
        reference._integer(mask, 0, (1 << width) - 1)
        reference._integer(rhs, 0, 1)
        while mask:
            bit = (mask & -mask).bit_length() - 1
            if bit not in pivots:
                pivots[bit] = (mask, rhs)
                break
            pm, pr = pivots[bit]
            mask, rhs = mask ^ pm, rhs ^ pr
        if not mask and rhs:
            raise ValueError('inconsistent equations: empty target domain')
        guard.check_terms(sum(m.bit_count() for m, _ in pivots.values()))
    free = [i for i in range(width) if i not in pivots]

    def solve(value, homogeneous):
        for bit, (mask, rhs) in sorted(pivots.items(), reverse=True):
            guard.check_time()
            wanted = ((mask & ~(1 << bit) & value).bit_count() & 1) ^ (0 if homogeneous else rhs)
            value = (value & ~(1 << bit)) | (wanted << bit)
        return value

    result = {'kind': 'affine_image', 'offset': solve(0, False),
              'columns': [solve(1 << i, True) for i in free]}
    guard.check_time()
    return result


def _table_words(spec, initial, algebra, guard):
    """Table-only Shannon construction; no candidate program or emitter is inspected."""
    width = len(spec['target_wires'])
    rows = tuple(0 if x is None else x for x in spec['table'])

    def visit(values, level):
        guard.check_time()
        first = values[0]
        if all(value == first for value in values):
            return tuple(algebra.one if first >> j & 1 else algebra.zero for j in range(width))
        half = len(values) // 2
        low = visit(values[:half], level - 1)
        high = visit(values[half:], level - 1)
        bit = initial[spec['address_wires'][level]]
        result = tuple(algebra.xor(a, algebra.mul(bit, algebra.xor(a, b)))
                       for a, b in zip(low, high))
        algebra.retained([*low, *high, *result])
        return result

    return visit(rows, len(spec['address_wires']) - 1)


def verify_affine_table(source, contract, *, backend='anf', table_style='shannon',
                        budget=None, max_terms=100000, max_products=1000000,
                        max_seconds=10.0, max_operations=100000, max_json_items=1000000,
                        max_graph_nodes=100000, max_clauses=500000):
    """Version-2 contract: wide affine targets without enumerating their legal values.

    Explicit ANF/SAT selection; strict caller-declared domain, detached sources,
    all outputs checked, physical witnesses replayed. No proof receipt authority.
    """
    for cap in (max_terms, max_products, max_operations, max_json_items, max_graph_nodes, max_clauses):
        reference._integer(cap, 1)
    if type(backend) is not str or backend not in ('anf', 'sat'):
        raise ValueError('backend must be anf or sat')
    if type(table_style) is not str or table_style not in ('shannon', 'minterms'):
        raise ValueError('table_style must be shannon or minterms')
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError('finite positive seconds required')
    if budget is not None and type(budget) is not Budget:
        raise TypeError('Budget or None required')
    guard = Guard(intersect_budgets(Budget(max_terms=max_terms, max_seconds=max_seconds), budget or Budget()))
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError('node/byte budgets unsupported')
    work = stream.Algebra(guard, max_products)
    if backend == 'sat':
        from symq.labs.kraus_graph import Graph

        work = Graph(guard, max_graph_nodes, max_clauses)
    started = time.perf_counter()
    result = {'status': 'inconclusive', 'witness': None, 'obligation': None,
              'proof_kind': f'affine_target_kraus_{backend}', 'portable_certificate': False}
    try:
        source = stream._snapshot(source, guard, max_json_items, [0])
        external = stream._snapshot(contract, guard, max_json_items, [0])
        reference._object(external, 'kind schema_version width address_wires target_wires clean_wires borrowed_wires table legal_addresses target_space bit_order records outputs')
        if (external['kind'] != 'symq_affine_hmr_table_contract'
                or type(external['schema_version']) is not int or external['schema_version'] != 2):
            raise ValueError('exact version-2 affine target contract required')
        normalized = {k: v for k, v in external.items() if k != 'target_space'}
        normalized.update(kind='symq_hmr_table_contract', schema_version=1, target_values=None)
        source, spec = reference._freeze(source, normalized, max_operations, max_target_bits=256,
                                         check_capacity=False)
        space = _space(external['target_space'], spec['target_wires'], guard)
        reference._capacity(spec, 256)
        result.update(source_sha256=reference._hash(source), contract_sha256=reference._hash(external),
                      target_width=len(space.wires), target_dimension=len(space.columns),
                      legal_basis_states=str(len(spec['legal_addresses']) * (1 << (len(space.columns) + len(spec['borrowed_wires'])))))
        result.update(stream._execute(source, spec, work, guard, True,
                                      target_space=space, table_style=table_style))
        work.close()
        guard.check_time()
    except (reference.Limit, ResourceLimitExceeded) as error:
        result.update(status='inconclusive', obligation='resources', witness=None, reason=str(error))
        result.update(resource_report(error, stream._limits(
            guard, backend, max_products, max_operations, max_json_items, max_graph_nodes,
            max_clauses)))
    except reference.Capacity as error:
        result.update(status='unsupported', obligation='capacity', witness=None, reason=str(error))
    except SatUnavailable as error:
        result.update(status='unsupported', obligation='backend', witness=None, reason=str(error))
    finally:
        work.close()
    result.update(work.metrics(), seconds=time.perf_counter() - started)
    return result
