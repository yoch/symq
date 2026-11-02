"""Research: eliminate input-independent Z/reset events while checking an isometry.

A recorded prefix outcome that distinguishes legal inputs cannot be repaired by
any later trace-preserving suffix. Check that obligation BEFORE constructing a
branch-support product. If it vanishes, substitute the measured value at one
legal anchor; only genuinely random HMR events need symbolic variables.

The grammar/contract remain those of anchored_kraus. Not a generic channel
checker, observable-instrument theorem, stable API, or portable proof kernel.
"""
from __future__ import annotations

import math
import time

from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
from symq.labs import anchored_kraus as reference
from symq.resources import Budget, Guard, intersect_budgets


class Algebra(reference.Work):
    zero = reference.ZERO
    one = reference.ONE

    def __init__(self, guard, products):
        super().__init__(guard.budget.max_terms, products, guard.deadline)
        self.guard = guard
        self.queries = 0

    def check(self, count=0):
        self.guard.check_time()
        self.guard.check_terms(count)
        super().check(count)

    def var(self, index):
        self.check()
        return frozenset((1 << index,))

    def witness(self, expression):
        self.check()
        self.queries += 1
        return min(expression, key=lambda m: (m.bit_count(), m)) if expression else None

    def retained(self, values):
        self.check(sum(map(len, values)))

    def close(self):
        pass

    def metrics(self):
        return {'peak_terms': self.peak_terms, 'products': self.products,
                'queries': self.queries}


_snapshot = reference._snapshot


def _last_reads(ops):
    last = {}
    for i, op in enumerate(ops):
        if op['condition'] is not None:
            last[op['condition'].removeprefix('!')] = i
        if op['kind'] in ('invert', 'oxor'):
            last[op['slot']] = i
        if op['kind'] == 'oxor':
            last[op['source']] = i
    release = {}
    for slot, i in last.items():
        release.setdefault(i, []).append(slot)
    return last, release


def _condition(op, memory, w):
    name = op['condition']
    if name is None:
        return w.one
    value = memory[name.removeprefix('!')]
    return w.xor(w.one, value) if name.startswith('!') else value


def _selector(wires, value, state, w):
    return w.all(state[q] if value >> i & 1 else w.xor(w.one, state[q])
                 for i, q in enumerate(wires))


def _allowed(wires, values, state, w):
    if len(values) == 1 << len(wires):
        return w.one
    out = w.zero
    for value in values:
        out = w.xor(out, _selector(wires, value, state, w))
    return out


def _legal(spec, x):
    def read(wires):
        return sum(((x >> q & 1) << j) for j, q in enumerate(wires))
    return (0 <= x < 1 << spec['width'] and not read(spec['clean_wires'])
            and read(spec['address_wires']) in spec['legal_addresses']
            and (spec['target_values'] is None or read(spec['target_wires']) in spec['target_values']))


def _concrete(source, x, choices, stop, guard):
    """Scalar branch execution independent of Boolean-polynomial/graph algebra."""
    memory, sign, hmr = {}, 0, 0
    for i, op in enumerate(source['ops']):
        guard.check_time()
        if i == stop:
            return x, sign
        kind, qs, slot = op['kind'], op['wires'], op['slot']
        condition = op['condition']
        enabled = condition is None or bool(memory[condition.removeprefix('!')]
                                             ^ int(condition.startswith('!')))
        if kind == 'hmr':
            m = choices >> hmr & 1
            hmr += 1
            sign ^= m & (x >> qs[0] & 1)
            x &= ~(1 << qs[0])
            memory[slot] = m
        elif kind in ('measure_z', 'reset'):
            bit = x >> qs[0] & 1
            if kind == 'reset':
                x &= ~(1 << qs[0])
            else:
                memory[slot] = bit
        elif kind == 'store':
            memory[slot] = op['value']
        elif kind == 'invert':
            memory[slot] ^= int(enabled)
        elif kind == 'oxor':
            memory[slot] ^= memory[op['source']]
        elif enabled and kind in reference.SIGN:
            sign ^= int(all(x >> q & 1 for q in qs))
        elif enabled and kind in ('x', 'cx', 'ccx', 'mcx'):
            if all(x >> q & 1 for q in qs[:-1]):
                x ^= 1 << qs[-1]
        elif enabled and kind in ('swap', 'cswap'):
            a, b = qs[-2:]
            if (kind == 'swap' or x >> qs[0] & 1) and (x >> a ^ x >> b) & 1:
                x ^= (1 << a) | (1 << b)
    return x, sign


def _validate_witness(source, spec, witness, obligation, guard):
    x, anchor, m = witness['input'], witness['anchor'], witness['hmr_choices']
    if not _legal(spec, x) or not _legal(spec, anchor):
        raise InternalInconsistency('witness outside legal domain')
    stop = witness['operation_index'] if obligation == 'irreversible_record' else None
    a, phase_a = _concrete(source, x, m, stop, guard)
    b, phase_b = _concrete(source, anchor, m, stop, guard)
    if obligation == 'irreversible_record':
        valid = (a >> witness['wire'] & 1) != (b >> witness['wire'] & 1)
    elif obligation == 'outputs':
        address = sum(((x >> q & 1) << j) for j, q in enumerate(spec['address_wires']))
        word = spec['table'][address]
        expected = x ^ sum(((word >> j & 1) << q) for j, q in enumerate(spec['target_wires']))
        valid = a != expected
    else:
        valid = phase_a != phase_b
    if not valid:
        raise InternalInconsistency('symbolic refutation failed scalar branch replay')
    guard.check_time()


def _execute(source, spec, w, guard, collect_slots):
    width = spec['width']
    clean = set(spec['clean_wires'])
    initial = [w.zero if q in clean else w.var(q) for q in range(width)]
    target = 0 if spec['target_values'] is None else spec['target_values'][0]
    anchor = sum(((spec['legal_addresses'][0] >> i & 1) << q)
                 for i, q in enumerate(spec['address_wires']))
    anchor |= sum(((target >> i & 1) << q) for i, q in enumerate(spec['target_wires']))
    domain = _allowed(spec['address_wires'], spec['legal_addresses'], initial, w)
    if spec['target_values'] is not None:
        domain = w.mul(domain, _allowed(spec['target_wires'], spec['target_values'], initial, w))
    state, phase, memory = list(initial), w.zero, {}
    hmr, eliminated, peak_slots = 0, 0, 0
    last, release = _last_reads(source['ops'])
    result = {'status': 'equivalent', 'obligation': None, 'witness': None, 'anchor': anchor}

    def refute(obligation, expression, i=None, wire=None):
        assignment = w.witness(expression)
        if assignment is None:
            return False
        witness = {'input': assignment & ((1 << width) - 1), 'anchor': anchor,
                   'hmr_choices': assignment >> width, 'operation_index': i, 'wire': wire}
        _validate_witness(source, spec, witness, obligation, guard)
        result.update(status='not_proved', obligation=obligation, witness=witness)
        return True

    for i, op in enumerate(source['ops']):
        w.retained([*state, phase, domain, *memory.values()])
        kind, qs, slot = op['kind'], op['wires'], op['slot']
        condition = _condition(op, memory, w)
        if kind in ('x', 'cx', 'ccx', 'mcx'):
            state[qs[-1]] = w.xor(state[qs[-1]], w.mul(condition, w.all(state[q] for q in qs[:-1])))
        elif kind in ('swap', 'cswap'):
            a, b = qs[-2:]
            enabled = condition if kind == 'swap' else w.mul(condition, state[qs[0]])
            diff = w.mul(enabled, w.xor(state[a], state[b]))
            state[a], state[b] = w.xor(state[a], diff), w.xor(state[b], diff)
        elif kind in reference.SIGN:
            phase = w.xor(phase, w.mul(condition, w.all(state[q] for q in qs)))
        elif kind == 'hmr':
            bit = w.var(width + hmr)
            hmr += 1
            phase = w.xor(phase, w.mul(bit, state[qs[0]]))
            state[qs[0]], memory[slot] = w.zero, bit
        elif kind in ('measure_z', 'reset'):
            q = qs[0]
            measured = w.anchor(state[q], width, anchor)
            if refute('irreversible_record', w.mul(domain, w.xor(state[q], measured)), i, q):
                result.update(compiled_operations=i + 1, hmr_events=hmr,
                              eliminated_events=eliminated, peak_live_slots=peak_slots)
                return result
            eliminated += 1
            state[q] = w.zero if kind == 'reset' else measured
            if kind == 'measure_z':
                memory[slot] = measured
        elif kind == 'store':
            memory[slot] = w.one if op['value'] else w.zero
        elif kind == 'invert':
            memory[slot] = w.xor(memory[slot], condition)
        elif kind == 'oxor':
            memory[slot] = w.xor(memory[slot], memory[op['source']])
        if collect_slots:
            for dead in release.get(i, ()):
                memory.pop(dead, None)
            if slot is not None and last.get(slot, -1) <= i:
                memory.pop(slot, None)
        peak_slots = max(peak_slots, len(memory))
    result.update(compiled_operations=len(source['ops']), hmr_events=hmr,
                  eliminated_events=eliminated, peak_live_slots=peak_slots)
    expected = list(initial)
    for address in spec['legal_addresses']:
        word = spec['table'][address]
        if word:
            select = _selector(spec['address_wires'], address, initial, w)
            for bit, q in enumerate(spec['target_wires']):
                if word >> bit & 1:
                    expected[q] = w.xor(expected[q], select)
    for q in range(width):
        if refute('outputs', w.mul(domain, w.xor(state[q], expected[q])), wire=q):
            return result
    refute('branch_phase', w.mul(domain, w.xor(phase, w.anchor(phase, width, anchor))))
    return result


def verify_stream(source, contract, *, budget=None, max_terms=100000,
                  max_products=1000000, max_seconds=10.0, max_operations=100000,
                  max_json_items=1000000, collect_slots=True, backend="anf",
                  max_graph_nodes=100000, max_clauses=500000):
    """Exact research isometry check, with shared deadlines and replayed refutations.

    Choose ANF or a shared Boolean DAG with exact SAT queries explicitly.
    Resource caps are explicit-data limits, never OS RSS caps. In SAT mode
    max_terms additionally caps generated CNF clauses, not polynomial storage.
    """
    for cap in (max_terms, max_products, max_operations, max_json_items,
                max_graph_nodes, max_clauses):
        reference._integer(cap, 1)
    if type(backend) is not str or backend not in ('anf', 'sat'):
        raise ValueError('backend must be anf or sat')
    if type(collect_slots) is not bool:
        raise ValueError('collect_slots must be an exact Boolean')
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError('finite positive seconds required')
    if budget is not None and type(budget) is not Budget:
        raise TypeError('Budget or None required')
    guard = Guard(intersect_budgets(Budget(max_terms=max_terms, max_seconds=max_seconds),
                                   budget or Budget()))
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError('max_nodes/max_bytes are not supported by this research engine')
    started = time.perf_counter()
    if backend == "anf":
        w = Algebra(guard, max_products)
    else:
        from symq.labs.kraus_graph import Graph

        w = Graph(guard, max_graph_nodes, max_clauses)
    result = {'status': 'inconclusive', 'obligation': None, 'witness': None,
              'proof_kind': f'streaming_kraus_{backend}', 'portable_certificate': False}
    try:
        source = _snapshot(source, guard, max_json_items, [0])
        contract = _snapshot(contract, guard, max_json_items, [0])
        source, spec = reference._freeze(source, contract, max_operations)
        result.update(source_sha256=reference._hash(source), contract_sha256=reference._hash(spec))
        guard.check_time()
        result.update(_execute(source, spec, w, guard, collect_slots))
        w.close()
        guard.check_time()
    except (reference.Limit, ResourceLimitExceeded) as error:
        result.update(status='inconclusive', obligation='resources', witness=None, reason=str(error))
    except SatUnavailable as error:
        result.update(status='unsupported', obligation='backend', witness=None, reason=str(error))
    finally:
        w.close()
    result.update(w.metrics(), seconds=time.perf_counter() - started)
    return result
