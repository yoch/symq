"""Independent loader cohort for the Kraus routes (audit #164).

A generator unrelated to ``benchmarks.anchored_kraus.random_source``: scrambled wire roles,
restricted target values, HMR-uncomputed selectors with corrections routed through classical
memory, deterministic measurements and resets, slot reuse and random mutations. Truth comes
from the explicit-matrix oracle ``tests/testkit/table_channel_oracle.py``, which shares no
code with ``symq.labs.anchored_*`` or with ``benchmarks.anchored_kraus.image``.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product

from symq.experimental.hybrid import HOp, HybridProgram
from tests.testkit import table_channel_oracle as oracle


def to_program(src):
    return HybridProgram(src['data'], src['ancillas'], [HOp(o['kind'], tuple(o['wires']), o['slot'], o['condition'], o['source'], o['value']) for o in src['ops']])

def op(kind, *w, slot=None, condition=None, source=None, value=None):
    return {'kind': kind, 'wires': list(w), 'slot': slot, 'condition': condition, 'source': source, 'value': value}

def roles(rng):
    na = rng.choice((1, 2)); nt = rng.choice((1, 2)); nc = rng.choice((1, 2)); nb = rng.choice((0, 1))
    width = na + nt + nc + nb
    wires = list(range(width)); rng.shuffle(wires)
    a, t, c, b = wires[:na], wires[na:na+nt], wires[na+nt:na+nt+nc], wires[na+nt+nc:]
    return width, a, t, c, b

def gen(rng):
    width, a, t, c, b = roles(rng)
    # program ancillas must be the top wires and clean: put all ancilla roles as data clean wires instead
    table = [rng.randrange(1 << len(t)) for _ in range(1 << len(a))]
    legal = sorted(rng.sample(range(1 << len(a)), rng.randrange(1, (1 << len(a)) + 1)))
    targets = None
    if rng.random() < 0.25:
        targets = sorted(rng.sample(range(1 << len(t)), rng.randrange(1, (1 << len(t)) + 1)))
    ops, slots, nslot = [], [], [0]
    def new_slot():
        s = f'b{nslot[0]}'; nslot[0] += 1; slots.append(s); return s
    def cond():
        if slots and rng.random() < 0.3:
            s = rng.choice(slots); return ('!' + s) if rng.random() < 0.3 else s
        return None
    # structured part: compute row selectors into a clean wire, copy table bits, HMR-uncompute
    anc = c[0]
    for addr in range(1 << len(a)):
        bits = [(addr >> i) & 1 for i in range(len(a))]
        flips = [a[i] for i in range(len(a)) if not bits[i]]
        for q in flips: ops.append(op('x', q))
        ops.append(op('mcx' if len(a) > 1 else 'cx', *a, anc))
        for j, q in enumerate(t):
            if table[addr] >> j & 1: ops.append(op('cx', anc, q))
        style = rng.random()
        if style < 0.5:          # HMR uncompute + phase correction (cz on controls / z for one control)
            s = new_slot(); ops.append(op('hmr', anc, slot=s))
            ops.append(op('cz' if len(a) > 1 else 'z', *a, condition=s))
        elif style < 0.7:        # coherent uncompute
            ops.append(op('mcx' if len(a) > 1 else 'cx', *a, anc))
        elif style < 0.85:       # HMR, correction routed through classical memory
            s = new_slot(); ops.append(op('hmr', anc, slot=s))
            s2 = new_slot(); ops.append(op('store', slot=s2, value=0)); ops.append(op('oxor', slot=s2, source=s))
            ops.append(op('invert', slot=s2)); ops.append(op('invert', slot=s2))
            ops.append(op('cz' if len(a) > 1 else 'z', *a, condition=s2))
        else:                    # deterministic measurement then reset of the uncomputed ancilla
            ops.append(op('mcx' if len(a) > 1 else 'cx', *a, anc))
            s = new_slot(); ops.append(op('measure_z', anc, slot=s)); ops.append(op('reset', anc))
            ops.append(op('x', anc, condition=s))  # value is 0, so never fires
        for q in flips: ops.append(op('x', q))
    # random noise / mutation
    kinds = ['x', 'cx', 'ccx', 'swap', 'cswap', 'z', 'cz', 'ccz', 'neg', 'hmr', 'measure_z', 'reset', 'invert', 'oxor', 'store', 'slotreuse', 'pair']
    for _ in range(rng.choice((0, 0, 1, 2))):
        k = rng.choice(kinds)
        pos = rng.randrange(len(ops) + 1)
        n = {'x': 1, 'cx': 2, 'ccx': 3, 'swap': 2, 'cswap': 3, 'z': 1, 'cz': 2, 'ccz': 3, 'neg': 0}.get(k)
        if n is not None:
            new = [op(k, *rng.sample(range(width), n), condition=cond())]
            if rng.random() < 0.4: new = new * 2   # self-inverse pair (often harmless)
        elif k in ('hmr', 'measure_z'):
            new = [op(k, rng.randrange(width), slot=new_slot())]
        elif k == 'reset':
            new = [op(k, rng.randrange(width))]
        elif k == 'store':
            new = [op('store', slot=new_slot(), value=rng.randrange(2))]
        elif k == 'slotreuse' and slots:
            new = [op('hmr', c[-1], slot=rng.choice(slots))]
        elif k == 'pair':
            q = rng.randrange(width); s = new_slot()
            new = [op('hmr', q, slot=s), op('z', q, condition=s)]
        else:
            continue
        # keep slot initialisation order valid: append new ops at the end if they read slots
        ops[pos:pos] = new if all(o['condition'] is None for o in new) else []
        if any(o['condition'] is not None for o in new): ops += new
    if rng.random() < 0.15 and slots:
        s = rng.choice(slots); ops.append(op('invert', slot=s, condition=cond()))
    src = {'kind': 'hybrid', 'schema_version': 1, 'data': width, 'ancillas': 0, 'ops': ops}
    spec = {'kind': 'symq_hmr_table_contract', 'schema_version': 1, 'width': width,
            'address_wires': a, 'target_wires': t, 'clean_wires': sorted(c), 'borrowed_wires': sorted(b),
            'table': [table[i] if (i in legal or rng.random() < 0.5) else None for i in range(len(table))],
            'legal_addresses': legal, 'target_values': targets,
            'bit_order': 'lsb_first', 'records': 'forgotten', 'outputs': 'all_retained'}
    return src, spec

def pack(w, v): return sum(((v >> j) & 1) << q for j, q in enumerate(w))
def legal_inputs(spec):
    tv = range(1 << len(spec['target_wires'])) if spec['target_values'] is None else spec['target_values']
    return [pack(spec['address_wires'], a) | pack(spec['target_wires'], z) | pack(spec['borrowed_wires'], d)
            for a in spec['legal_addresses'] for z in tv for d in range(1 << len(spec['borrowed_wires']))]
def ideal(spec, x):
    a = sum(((x >> q) & 1) << i for i, q in enumerate(spec['address_wires']))
    return x ^ pack(spec['target_wires'], spec['table'][a])


def truth(src, spec):
    """(holds, images) for the declared XOR isometry on every legal coherence."""
    program = to_program(src)
    xs = legal_inputs(spec)
    images = {(x, y): oracle.forgotten(program, {(x, y): Fraction(1)}) for x, y in product(xs, repeat=2)}
    holds = all(v == {(ideal(spec, x), ideal(spec, y)): Fraction(1)} for (x, y), v in images.items())
    return holds, images, xs
