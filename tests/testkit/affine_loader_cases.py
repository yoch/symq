"""Independent affine-target loader cohort (audit #164).

Random consistent parity systems (dependent rows, rank-zero images), scrambled wire roles,
relation-dependent resets/HMR/measurements that are harmless only on the declared image,
and mutations. Legal physical inputs are enumerated by brute force from the equations (not
from the checker's conversion); truth comes from the explicit-matrix oracle of #157.
"""
from __future__ import annotations

from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.affine_table import affine_target_from_equations


def to_program(src):
    return HybridProgram(src['data'], src['ancillas'], [HOp(o['kind'], tuple(o['wires']), o['slot'], o['condition'], o['source'], o['value']) for o in src['ops']])
def op(kind, *w, slot=None, condition=None, source=None, value=None):
    return {'kind': kind, 'wires': list(w), 'slot': slot, 'condition': condition, 'source': source, 'value': value}
def pack(w, v): return sum(((v >> j) & 1) << q for j, q in enumerate(w))
def parity(v): return v.bit_count() & 1

def gen(rng):
    na, nt, nc, nb = rng.choice((1, 2)), rng.choice((2, 3)), rng.choice((1, 2)), rng.choice((0, 1))
    width = na + nt + nc + nb
    wires = list(range(width)); rng.shuffle(wires)
    a, t, c, b = wires[:na], wires[na:na+nt], sorted(wires[na+nt:na+nt+nc]), sorted(wires[na+nt+nc:])
    while True:   # consistent random parity system (possibly dependent rows, possibly rank 0 image)
        eqs = [[rng.randrange(1 << nt), rng.randrange(2)] for _ in range(rng.randrange(0, nt + 2))]
        sols = [z for z in range(1 << nt) if all(parity(z & m) == r for m, r in eqs)]
        if sols: break
    space = affine_target_from_equations(nt, eqs)
    table = [rng.randrange(1 << nt) for _ in range(1 << na)]
    legal = sorted(rng.sample(range(1 << na), rng.randrange(1, (1 << na) + 1)))
    ops, n = [], [0]
    def slot():
        n[0] += 1; return f'b{n[0]}'
    anc = c[0]
    for addr in range(1 << na):
        flips = [a[i] for i in range(na) if not addr >> i & 1]
        ops += [op('x', q) for q in flips]
        ops.append(op('mcx' if na > 1 else 'cx', *a, anc))
        ops += [op('cx', anc, q) for j, q in enumerate(t) if table[addr] >> j & 1]
        if rng.random() < 0.6:
            s = slot(); ops += [op('hmr', anc, slot=s), op('cz' if na > 1 else 'z', *a, condition=s)]
        else:
            ops.append(op('mcx' if na > 1 else 'cx', *a, anc))
        ops += [op('x', q) for q in flips]
    # relation-dependent work on the ancilla: harmless only if mask is constant on the image
    for _ in range(rng.randrange(0, 3)):
        if eqs and rng.random() < 0.7:
            m, r = rng.choice(eqs)
            if rng.random() < 0.5 and len(eqs) > 1:
                m2, r2 = rng.choice(eqs); m, r = m ^ m2, r ^ r2
        else:
            m, r = rng.randrange(1, 1 << nt), None
        ws = [t[j] for j in range(nt) if m >> j & 1]
        if not ws: continue
        ops += [op('cx', q, anc) for q in ws]
        mode = rng.random()
        if mode < 0.4:
            ops.append(op('reset', anc))
        elif mode < 0.7:
            s = slot(); ops.append(op('hmr', anc, slot=s))
        else:
            s = slot(); ops += [op('measure_z', anc, slot=s), op('x', anc, condition=s)]
    if rng.random() < 0.2:   # random mutation
        k = rng.choice(['x', 'z', 'cz', 'cx', 'reset'])
        ar = {'x': 1, 'z': 1, 'cz': 2, 'cx': 2, 'reset': 1}[k]
        ops.insert(rng.randrange(len(ops) + 1), op(k, *rng.sample(range(width), ar)))
    src = {'kind': 'hybrid', 'schema_version': 1, 'data': width, 'ancillas': 0, 'ops': ops}
    spec = {'kind': 'symq_affine_hmr_table_contract', 'schema_version': 2, 'width': width,
            'address_wires': a, 'target_wires': t, 'clean_wires': c, 'borrowed_wires': b,
            'table': [table[i] if i in legal or rng.random() < 0.5 else None for i in range(len(table))],
            'legal_addresses': legal, 'target_space': space,
            'bit_order': 'lsb_first', 'records': 'forgotten', 'outputs': 'all_retained'}
    xs = [pack(a, x) | pack(t, z) | pack(b, d) for x in legal for z in sols for d in range(1 << nb)]
    return src, spec, xs

def ideal(spec, x):
    a = sum(((x >> q) & 1) << i for i, q in enumerate(spec['address_wires']))
    return x ^ pack(spec['target_wires'], spec['table'][a])
