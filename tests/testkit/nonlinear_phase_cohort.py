"""Independent nonlinear-phase cohort (audit #164).

Random strict dephasers (1-3 HMR, conditional feedback on the same and earlier outcomes,
unconditional signs), random affine supports, mixed precision k=1..4, negative angles and
full turns, shared permutation suffixes and output mutations. Certificates are built by a
separate brute-force scalar simulation of the effective signature and of delta; truth is
the exact Kraus/cyclotomic oracle ``tests/testkit/affine_phase_oracle.same_channel``. No
code from ``affine_phase`` or ``nonlinear_phase_bits`` is used to build either.
"""
from __future__ import annotations

from fractions import Fraction

from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.phase import PhaseProgram
from tests.testkit.affine_phase_oracle import inputs

D_WIRES = (0, 1, 2)   # wire 3 is scratch, fixed to 0 on every support

def rand_subset(rng):
    s = [q for q in D_WIRES if rng.random() < 0.5]
    return s or [rng.choice(D_WIRES)]

def make_dephaser(rng):
    anc = rng.choice((1, 2)); d = PhaseProgram(4, anc)
    for j in range(rng.choice((1, 2, 3))):
        a = 4 + rng.randrange(anc)
        sub = rand_subset(rng)
        if len(sub) == 1: d.cx(sub[0], a)
        elif len(sub) == 2: d.ccx(sub[0], sub[1], a)
        else: d.mcx(*sub, a)
        if rng.random() < 0.3: d.cx(rng.choice(D_WIRES), a)
        idx = d.hmr(a)
        if rng.random() < 0.4: d.mcz_if(idx, *rand_subset(rng))
        if rng.random() < 0.3 and idx > 0: d.mcz_if(rng.randrange(idx), *rand_subset(rng))
        if rng.random() < 0.2: d.z(rng.choice(D_WIRES))
    return d

def signature(d, x):
    """Scalar effective signature: qubit value at each HMR XOR later feedback products."""
    state, sig = x, []
    for op in d.ops:
        if op.kind == 'mcx':
            *c, t = op.qubits
            if all(state >> q & 1 for q in c): state ^= 1 << t
        elif op.kind == 'hmr':
            q = op.qubits[0]; sig.append(state >> q & 1); state &= ~(1 << q)
        elif op.kind == 'mcz_if':
            if all(state >> q & 1 for q in op.qubits): sig[op.outcome] ^= 1
    return sum(b << j for j, b in enumerate(sig)), len(sig)

def gadget(p, sub, angle):
    if len(sub) == 1: p.cx(sub[0], 3)
    else: p.mcx(*sub, 3)
    p.phase(3, angle)
    if len(sub) == 1: p.cx(sub[0], 3)
    else: p.mcx(*sub, 3)

def make_pair(rng, d):
    kl, kr = rng.choice((1, 2, 3, 4)), rng.choice((1, 2, 3, 4))
    left, right = DyadicPhaseProgram(4, k=kl), DyadicPhaseProgram(4, k=kr)
    perm = [(rng.choice(('x', 'cx', 'ccx')), rng.sample(D_WIRES, 3)) for _ in range(rng.randrange(0, 3))]
    def ang(k):  # negative angles and multiple full turns
        return Fraction(rng.randrange(-2 * (1 << k), 2 * (1 << k)), 1 << k)
    for prog, k in ((left, kl), (right, kr)):
        for _ in range(rng.randrange(0, 4)):
            gadget(prog, rand_subset(rng), ang(k))
        if rng.random() < 0.3: prog.phase(rng.choice(D_WIRES), ang(k))
    # shared permutation suffix (same outputs) and a shared common gadget
    for prog in (left, right):
        for kind, ws in perm:
            if kind == 'x':
                prog.x(ws[0])
            elif kind == 'cx':
                prog.cx(ws[0], ws[1])
            else:
                prog.ccx(*ws)
    if rng.random() < 0.1:   # output mutation
        right.x(rng.choice(D_WIRES))
    return left, right

def support(rng):
    cols = []
    for _ in range(rng.randrange(1, 4)):
        c = rng.randrange(1, 8)
        # keep independent
        span = {0}
        for v in cols:
            span |= {s ^ v for s in span}
        if c not in span: cols.append(c)
    offset = rng.randrange(8)
    return offset, tuple(cols)

def certificate(left, right, d, offset, cols, k):
    table, consistent = {}, True
    H = None
    for x in inputs(4, offset, cols):
        _, pl = left.run(x); _, pr = right.run(x)
        delta = ((pl << (k - left.k)) - (pr << (k - right.k))) % (1 << k)
        h, H = signature(d, x)
        if table.setdefault(h, delta) != delta: consistent = False
    planes = []
    for j in range(k):
        coeff = [(table.get(v, 0) >> j) & 1 for v in range(1 << H)]
        for i in range(H):   # Moebius transform
            for v in range(1 << H):
                if v >> i & 1: coeff[v] ^= coeff[v ^ (1 << i)]
        planes.append(tuple(v for v in range(1 << H) if coeff[v]))
    return tuple(planes), consistent
