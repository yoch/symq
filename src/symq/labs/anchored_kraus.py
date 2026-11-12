"""Research pilot: exact anchored Kraus-separability via Boolean polynomials.

Closed JSON input compatible with SymQ's hybrid program / HMR table documents.
No stable API, no automatic backend selection, no portable proof certificate.
A nonzero obligation is a refutation; resource exhaustion is inconclusive.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any

from symq.errors import ResourceLimitExceeded, SymqError
from symq.labs.resource_report import resource_report
from symq.resources import Budget, Guard, intersect_budgets

Poly = frozenset[int]
ZERO: Poly = frozenset()
ONE: Poly = frozenset((0,))
ARITY = {'x': 1, 'cx': 2, 'ccx': 3, 'swap': 2, 'cswap': 3, 'z': 1, 'cz': 2, 'ccz': 3, 'neg': 0, 'hmr': 1, 'measure_z': 1, 'reset': 1}
PERM = {'x', 'cx', 'ccx', 'mcx', 'swap', 'cswap'}
SIGN = {'z', 'cz', 'ccz', 'neg'}
CLASSIC = {'store', 'invert', 'oxor'}
EVENTS = {'hmr', 'measure_z', 'reset'}

class Limit(Exception):
    """No semantic conclusion is available within the requested budget.

    ``str()`` is the resource name; ``limit`` and ``observed`` are set when known.
    """

    def __init__(self, resource: str, limit: float | None = None,
                 observed: float | None = None) -> None:
        super().__init__(resource)
        self.resource, self.limit, self.observed = resource, limit, observed


MAX_ADDRESS_BITS = 12
"""Address width this verifier accepts; a wider, well-formed table is ``unsupported``."""


class Capacity(SymqError):
    """A well-formed input lies outside the sizes this verifier supports.

    Callers report it as ``unsupported``: no verdict, and not a malformed input.
    """

@dataclass
class Work:
    max_terms: int
    max_products: int
    deadline: float
    products: int = 0
    peak_terms: int = 0

    def check(self, count: int=0) -> None:
        if time.perf_counter() > self.deadline:
            raise Limit('deadline')
        self.peak_terms = max(self.peak_terms, count)
        if count > self.max_terms:
            raise Limit('terms', self.max_terms, count)

    def xor(self, a: Poly, b: Poly) -> Poly:
        self.check(len(a) + len(b))
        result = a ^ b
        self.check(len(result))
        return result

    def mul(self, a: Poly, b: Poly) -> Poly:
        self.check()
        if not a or not b:
            return ZERO
        if a == ONE:
            return b
        if b == ONE or a == b:
            return a
        self.products += len(a) * len(b)
        if self.products > self.max_products:
            raise Limit('products', self.max_products, self.products)
        result: set[int] = set()
        for x in a:
            for y in b:
                mask = x | y
                if mask in result:
                    result.remove(mask)
                else:
                    result.add(mask)
                self.check(len(result))
        return frozenset(result)

    def all(self, values) -> Poly:
        result = ONE
        for value in values:
            result = self.mul(result, value)
        return result

    def anchor(self, value: Poly, width: int, basis: int) -> Poly:
        """Substitute all physical input bits, leaving immutable event variables."""
        low = (1 << width) - 1
        result: set[int] = set()
        for mask in value:
            self.check()
            if mask & low & ~basis:
                continue
            term = mask & ~low
            if term in result:
                result.remove(term)
            else:
                result.add(term)
        self.check(len(result))
        return frozenset(result)


def _snapshot(value, guard, cap, count, depth=0):
    """Budgeted detached exact-primitive tree; reject cycles through depth bound."""
    guard.check_time()
    count[0] += 1
    if count[0] > cap:
        raise Limit('JSON items', cap, count[0])
    if depth > 8:
        raise ValueError('JSON nesting exceeds the closed schema')
    if value is None or type(value) in (int, bool):
        if type(value) is int and value.bit_length() > 1024:
            raise ValueError('oversized input integer')
        return value
    if type(value) is str:
        if len(value) > 128:
            raise ValueError('oversized input string')
        return value
    if type(value) is list:
        return [_snapshot(v, guard, cap, count, depth + 1) for v in value]
    if type(value) is dict and all(type(k) is str for k in value):
        return {_snapshot(k, guard, cap, count, depth + 1):
                _snapshot(v, guard, cap, count, depth + 1) for k, v in value.items()}
    raise ValueError('only exact JSON primitives are accepted')


def _plain(value: Any) -> None:
    """Only exact JSON primitives: no spoofed subclasses or custom equality."""
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is list:
        for item in value:
            _plain(item)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            _plain(item)
        return
    raise ValueError('exact JSON primitives required')


def _object(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError('missing or extra fields')


def _integer(value, lower=0, upper=None):
    if type(value) is not int or value < lower or (upper is not None and value > upper):
        raise ValueError('integer outside supported bounds')


def _array(value, bound, *, nonempty=False, ordered=False):
    if type(value) is not list or (nonempty and (not value)):
        raise ValueError('list required, nonempty where declared')
    for item in value:
        _integer(item, 0, bound - 1)
    if len(set(value)) != len(value):
        raise ValueError('duplicate list item')
    if ordered and value != sorted(value):
        raise ValueError('ordered values required')


def _capacity(spec, max_target_bits, max_address_bits=MAX_ADDRESS_BITS):
    """Raise ``Capacity`` for a validated contract wider than this verifier supports."""
    if len(spec['address_wires']) > max_address_bits:
        raise Capacity(f"address width {len(spec['address_wires'])} exceeds this verifier's "
                       f"limit of {max_address_bits}")
    if len(spec['target_wires']) > max_target_bits:
        raise Capacity(f"target width {len(spec['target_wires'])} exceeds this verifier's "
                       f"limit of {max_target_bits}")


def _freeze(source, spec, max_operations, *, max_target_bits=16, check_capacity=True):
    """Validate and detach a source and a version-1 contract.

    Malformed input raises ``ValueError``. Only a contract that is otherwise valid is then
    compared with the size limits (``Capacity``); a caller that validates more of the
    contract after this function passes ``check_capacity=False`` and calls ``_capacity``
    itself once everything is validated.
    """
    _plain(source)
    _plain(spec)
    source = json.loads(json.dumps(source))
    spec = json.loads(json.dumps(spec))
    _object(source, 'schema_version kind data ancillas ops')
    if type(source['schema_version']) is not int or source['schema_version'] != 1:
        raise ValueError('unsupported source schema')
    if source['kind'] != 'hybrid':
        raise ValueError('hybrid source required')
    _integer(source['data'], 1, 256)
    _integer(source['ancillas'], 0, 256)
    width = source['data'] + source['ancillas']
    _integer(width, 2, 256)
    if type(source['ops']) is not list:
        raise ValueError('operation list required')
    if len(source['ops']) > max_operations:
        raise Limit('operations', max_operations, len(source['ops']))
    initialized: set[str] = set()
    for op in source['ops']:
        _object(op, 'kind wires slot condition source value')
        kind, wires = (op['kind'], op['wires'])
        if type(kind) is not str or kind not in PERM | SIGN | CLASSIC | EVENTS:
            raise ValueError('unsupported operation')
        _array(wires, width)
        if kind == 'mcx' and len(wires) < 2:
            raise ValueError('MCX arity')
        if kind in ARITY and len(wires) != ARITY[kind]:
            raise ValueError('gate arity')
        for key in ('slot', 'condition', 'source'):
            if op[key] is not None and type(op[key]) is not str:
                raise ValueError('slot names must be strings')
        condition = op['condition']
        if condition is not None:
            name = condition.removeprefix('!')
            if name not in initialized or kind in EVENTS or kind in {'store', 'oxor'}:
                raise ValueError('invalid classical condition')
        if kind in CLASSIC | {'hmr', 'measure_z'}:
            slot = op['slot']
            if type(slot) is not str or not slot.startswith('b') or (not slot[1:].isdigit()) or (str(int(slot[1:])) != slot[1:]):
                raise ValueError('invalid slot')
        elif op['slot'] is not None:
            raise ValueError('unexpected slot')
        if kind == 'store':
            if wires or op['source'] is not None:
                raise ValueError('invalid store')
            _integer(op['value'], 0, 1)
        elif kind in {'invert', 'oxor'}:
            if wires or op['slot'] not in initialized or op['value'] is not None:
                raise ValueError('invalid classical update')
            if kind == 'oxor' and op['source'] not in initialized:
                raise ValueError('uninitialized source')
            if kind == 'invert' and op['source'] is not None:
                raise ValueError('unexpected source')
        elif op['source'] is not None or op['value'] is not None:
            raise ValueError('extraneous fields')
        if kind in CLASSIC | {'hmr', 'measure_z'}:
            initialized.add(op['slot'])
    _object(spec, 'kind schema_version width address_wires target_wires clean_wires borrowed_wires table legal_addresses target_values bit_order records outputs')
    if type(spec['schema_version']) is not int or spec['schema_version'] != 1 or spec['kind'] != 'symq_hmr_table_contract' or (spec['bit_order'] != 'lsb_first') or (spec['records'] != 'forgotten') or (spec['outputs'] != 'all_retained'):
        raise ValueError('unsupported table contract')
    _integer(spec['width'], 2, 256)
    if spec['width'] != width:
        raise ValueError('width mismatch')
    names = ('address_wires', 'target_wires', 'clean_wires', 'borrowed_wires')
    for name in names:
        _array(spec[name], width, nonempty=name in names[:2])
    if sorted(q for key in names for q in spec[key]) != list(range(width)):
        raise ValueError('wire roles must partition width')
    if not set(range(source['data'], width)) <= set(spec['clean_wires']):
        raise ValueError('program ancillas must be declared clean')
    rows = 1 << len(spec['address_wires'])
    if type(spec['table']) is not list or len(spec['table']) != rows:
        raise ValueError('complete table shape required')
    _array(spec['legal_addresses'], rows, nonempty=True, ordered=True)
    target_count = 1 << len(spec['target_wires'])
    legal = set(spec['legal_addresses'])
    for a, row in enumerate(spec['table']):
        if row is None and a not in legal:
            continue
        _integer(row, 0, target_count - 1)
    if spec['target_values'] is not None:
        _array(spec['target_values'], target_count, nonempty=True, ordered=True)
    if check_capacity:
        _capacity(spec, max_target_bits)
    return (source, spec)


def _condition(name, memory, w):
    if name is None:
        return ONE
    if name.startswith('!'):
        return w.xor(ONE, memory[name[1:]])
    return memory[name]


def _selector(wires, value, initial, w):
    return w.all((initial[q] if value >> i & 1 else w.xor(ONE, initial[q]) for i, q in enumerate(wires)))


def _allowed(wires, values, initial, w):
    if len(values) == 1 << len(wires):
        return ONE
    out = ZERO
    for value in values:
        out = w.xor(out, _selector(wires, value, initial, w))
    return out


def _compile(source, initial, w):
    state, memory, phase, support = (list(initial), {}, ZERO, ONE)
    width, event, hmr = (len(initial), 0, 0)
    for op in source['ops']:
        w.check(sum(map(len, state)) + len(phase) + len(support) + sum(map(len, memory.values())))
        kind, qs, slot = (op['kind'], op['wires'], op['slot'])
        condition = _condition(op['condition'], memory, w)
        if kind in {'x', 'cx', 'ccx', 'mcx'}:
            toggle = w.mul(condition, w.all(state[q] for q in qs[:-1]))
            state[qs[-1]] = w.xor(state[qs[-1]], toggle)
        elif kind in {'swap', 'cswap'}:
            a, b = qs[-2:]
            enabled = condition if kind == 'swap' else w.mul(condition, state[qs[0]])
            diff = w.mul(enabled, w.xor(state[a], state[b]))
            state[a], state[b] = (w.xor(state[a], diff), w.xor(state[b], diff))
        elif kind in SIGN:
            phase = w.xor(phase, w.mul(condition, w.all(state[q] for q in qs)))
        elif kind in EVENTS:
            bit = frozenset((1 << width + event,))
            event += 1
            q = qs[0]
            if kind == 'hmr':
                hmr += 1
                phase = w.xor(phase, w.mul(bit, state[q]))
            else:
                support = w.mul(support, w.xor(ONE, w.xor(bit, state[q])))
            if kind != 'measure_z':
                state[q] = ZERO
            if kind != 'reset':
                memory[slot] = bit
        elif kind == 'store':
            memory[slot] = ONE if op['value'] else ZERO
        elif kind == 'invert':
            memory[slot] = w.xor(memory[slot], condition)
        elif kind == 'oxor':
            memory[slot] = w.xor(memory[slot], memory[op['source']])
    w.check()
    return (state, phase, support, event, hmr)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def verify(source: dict, contract: dict, *, budget: Budget | None=None, max_terms: int=100000, max_products: int=1000000, max_seconds: float=10.0, max_operations: int=100000, max_json_items: int=1000000) -> dict:
    """Research-only exact symbolic decision for the closed sign/hybrid grammar.

    Caps bound explicit polynomial growth; they are not an OS memory guarantee.
    Refutations report the assignment making a Boolean obligation nonzero. The
    mathematical criterion is necessary/sufficient; no untrusted receipt is accepted.
    The deadline and term cap are intersected with ``budget`` and any active
    VerificationSession (never restarted); inherited node/byte caps are refused.
    """
    for cap in (max_terms, max_products, max_operations, max_json_items):
        _integer(cap, 1)
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError('finite positive seconds required')
    if budget is not None and type(budget) is not Budget:
        raise TypeError('Budget or None required')
    guard = Guard(intersect_budgets(Budget(max_terms=max_terms, max_seconds=max_seconds), budget or Budget()))
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError('max_nodes/max_bytes are not supported by this research engine')
    started = time.perf_counter()
    w = Work(guard.budget.max_terms, max_products, guard.deadline)
    result = {'schema_version': 1, 'status': 'inconclusive', 'obligation': None, 'source_sha256': None, 'contract_sha256': None, 'witness': None, 'proof_kind': 'anchored_kraus_anf', 'portable_certificate': False}
    try:
        w.check()
        source = _snapshot(source, guard, max_json_items, [0])
        contract = _snapshot(contract, guard, max_json_items, [0])
        source, spec = _freeze(source, contract, max_operations)
        result.update(source_sha256=_hash(source), contract_sha256=_hash(spec))
        width = spec['width']
        clean = set(spec['clean_wires'])
        initial = [ZERO if q in clean else frozenset((1 << q,)) for q in range(width)]
        a0 = spec['legal_addresses'][0]
        z0 = 0 if spec['target_values'] is None else spec['target_values'][0]
        anchor = sum(((a0 >> i & 1) << q for i, q in enumerate(spec['address_wires'])))
        anchor |= sum(((z0 >> i & 1) << q for i, q in enumerate(spec['target_wires'])))
        domain = _allowed(spec['address_wires'], spec['legal_addresses'], initial, w)
        if spec['target_values'] is not None:
            domain = w.mul(domain, _allowed(spec['target_wires'], spec['target_values'], initial, w))
        outputs, phase, support, events, hmr = _compile(source, initial, w)
        result.update(anchor=anchor, events=events, hmr_events=hmr, represented_hmr_branches=str(1 << hmr))

        def check(obligation, value, wire=None):
            w.check()
            if value:
                assignment = min(value, key=lambda m: (m.bit_count(), m))
                x, m = (assignment & (1 << width) - 1, assignment >> width)
                result.update(status='not_proved', obligation=obligation, witness={'input': x, 'anchor': anchor, 'events': m, 'wire': wire})
                return False
            return True
        baseline_support = w.anchor(support, width, anchor)
        if not check('branch_support', w.mul(domain, w.xor(support, baseline_support))):
            return _finish(result, w, started)
        active = w.mul(domain, support)
        expected = list(initial)
        for address in spec['legal_addresses']:
            word = spec['table'][address]
            if word:
                selection = _selector(spec['address_wires'], address, initial, w)
                for bit, q in enumerate(spec['target_wires']):
                    if word >> bit & 1:
                        expected[q] = w.xor(expected[q], selection)
        for q in range(width):
            if not check('outputs', w.mul(active, w.xor(outputs[q], expected[q])), q):
                return _finish(result, w, started)
        if not check('branch_phase', w.mul(active, w.xor(phase, w.anchor(phase, width, anchor)))):
            return _finish(result, w, started)
        result['status'] = 'equivalent'
        return _finish(result, w, started)
    except (Limit, ResourceLimitExceeded) as error:
        result.update(status='inconclusive', obligation='resources', witness=None, reason=str(error))
        result.update(resource_report(error, {'max_terms': guard.budget.max_terms,
                                              'max_products': max_products,
                                              'max_seconds': guard.budget.max_seconds,
                                              'absolute_deadline': guard.budget.absolute_deadline,
                                              'max_operations': max_operations,
                                              'max_json_items': max_json_items}))
        result.update(seconds=time.perf_counter() - started, peak_terms=w.peak_terms, products=w.products)
        return result
    except Capacity as error:
        result.update(status='unsupported', obligation='capacity', witness=None, reason=str(error))
        result.update(seconds=time.perf_counter() - started, peak_terms=w.peak_terms, products=w.products)
        return result


def _finish(result, work, started):
    work.check()
    result.update(seconds=time.perf_counter() - started, peak_terms=work.peak_terms, products=work.products)
    return result
