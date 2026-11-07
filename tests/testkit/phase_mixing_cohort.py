"""Independent phase-certificate cohort (audit #166), unrelated to benchmarks/phase_*.

Dephasers measure dense invertible XOR mixes of random AND-products with offsets, extra
linear terms, same/earlier-outcome feedback and unconditional signs; sources add phase
gadgets on atom products, XOR predicates (aggregate cancellations) and arbitrary monomials,
with k=1..4, negative angles and full turns, shared permutations and output mutations, on
random offset affine supports. True certificates come from a separate scalar simulation
of the effective signature and delta (Moebius transform), never from symq.labs code.
"""
from __future__ import annotations

from fractions import Fraction

from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.phase import PhaseProgram
from tests.testkit.affine_phase_oracle import inputs


def monomial(rng, wires):
    return sorted(rng.sample(wires, rng.choice((1, 1, 2, 2, 3))))

def emit(prog, mono, target):
    if len(mono) == 1: prog.cx(mono[0], target)
    elif len(mono) == 2: prog.ccx(mono[0], mono[1], target)
    else: prog.mcx(*mono, target)

def make_case(rng):
    n = rng.choice((3, 4)); scratch = n; width = n + 1; data = list(range(n))
    H = rng.choice((1, 2, 3)); anc = rng.choice((1, 2))
    d = PhaseProgram(width, anc)
    atoms = [monomial(rng, data) for _ in range(H)]
    while True:   # dense invertible mixing of the atom products
        rows = [rng.randrange(1, 1 << H) for _ in range(H)]
        span, ok = {0}, True
        for r in rows:
            if r in span: ok = False; break
            span |= {s ^ r for s in span}
        if ok: break
    for j, r in enumerate(rows):
        a = width + rng.randrange(anc)
        if rng.random() < 0.3: d.x(a)                      # signature offset
        for i in range(H):
            if r >> i & 1: emit(d, atoms[i], a)
        if rng.random() < 0.2: d.cx(rng.choice(data), a)   # extra linear term
        idx = d.hmr(a)
        if rng.random() < 0.35: d.mcz_if(idx, *monomial(rng, data))
        if idx and rng.random() < 0.25: d.mcz_if(rng.randrange(idx), *monomial(rng, data))
        if rng.random() < 0.2: d.z(rng.choice(data))
    kl, kr = rng.choice((1, 2, 3, 4)), rng.choice((1, 2, 3, 4))
    left, right = DyadicPhaseProgram(width, k=kl), DyadicPhaseProgram(width, k=kr)
    def ang(k): return Fraction(rng.randrange(-2 * (1 << k), 2 * (1 << k) + 1), 1 << k)
    def gadget(prog, monos, angle):
        for m in monos: emit(prog, m, scratch)
        prog.phase(scratch, angle)
        for m in reversed(monos): emit(prog, m, scratch)
    for prog, k in ((left, kl), (right, kr)):
        for _ in range(rng.randrange(0, 4)):
            style = rng.random()
            if style < 0.5:    # product of atoms (a function of h when mixing is invertible)
                chosen = [atoms[i] for i in range(H) if rng.random() < 0.6] or [atoms[0]]
                monos = [sorted(set().union(*map(set, chosen)))]
            elif style < 0.8:  # XOR predicate, enabling aggregate cancellations
                monos = [atoms[rng.randrange(H)], sorted(set(atoms[rng.randrange(H)]) | set(monomial(rng, data)))]
            else:              # arbitrary monomial predicate (often not a function of h)
                monos = [monomial(rng, data)]
            gadget(prog, monos, ang(k))
    perm = [rng.sample(data, 3) for _ in range(rng.randrange(0, 3))]
    for prog in (left, right):
        for a, b, c in perm:
            prog.ccx(a, b, c)
    if rng.random() < 0.08: right.x(rng.choice(data))      # output mutation
    cols = []
    for _ in range(rng.randrange(1, n + 1)):
        c = rng.randrange(1, 1 << n); span = {0}
        for v in cols: span |= {s ^ v for s in span}
        if c not in span: cols.append(c)
    return left, right, d, rng.randrange(1 << n), tuple(cols), H

def signature_word(d, x):
    state, sig = x, []
    for op in d.ops:
        if op.kind == 'mcx':
            *c, t = op.qubits
            if all(state >> q & 1 for q in c): state ^= 1 << t
        elif op.kind == 'hmr':
            q = op.qubits[0]; sig.append(state >> q & 1); state &= ~(1 << q)
        elif op.kind == 'mcz_if' and all(state >> q & 1 for q in op.qubits):
            sig[op.outcome] ^= 1
    return sum(b << j for j, b in enumerate(sig))

def certificates(left, right, d, offset, cols, H):
    k = max(left.k, right.k); table = {}; consistent = True
    for x in inputs(left.width, offset, cols):
        delta = ((left.run(x)[1] << (k - left.k)) - (right.run(x)[1] << (k - right.k))) % (1 << k)
        h = signature_word(d, x)
        if table.setdefault(h, delta) != delta: consistent = False
    planes = []
    for j in range(k):
        coeff = [(table.get(v, 0) >> j) & 1 for v in range(1 << H)]
        for i in range(H):
            for v in range(1 << H):
                if v >> i & 1: coeff[v] ^= coeff[v ^ (1 << i)]
        planes.append(tuple(v for v in range(1 << H) if coeff[v]))
    factored = tuple((1 << j, tuple(tuple(1 << (i + 1) for i in range(H) if m >> i & 1) for m in plane))
                     for j, plane in enumerate(planes))
    return tuple(planes), factored, consistent
