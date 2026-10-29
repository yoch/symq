"""Independent reference for the PR #90 gate semantics: dense Kraus operators, exact rationals.

Nothing here imports or reuses the audited oracle. The operator set is written from the gate
descriptions alone, with a *different* algorithm (dense matrices, apply-then-sum) so agreement is
evidence rather than a restatement.

Normalisation trick: every Kraus operator below is scaled by sqrt(2) per measurement, which keeps all
entries rational. If a program has ``k`` measurement events, the true channel is
``2**(-k) * sum_A A rho A^dag`` with the scaled ``A``. The factor is applied once at the end.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import product

F = Fraction


def zeros(n):
    return [[F(0)] * n for _ in range(n)]


def eye(n):
    return [[F(1) if i == j else F(0) for j in range(n)] for i in range(n)]


def matmul(a, b):
    n, m, p = len(a), len(b), len(b[0])
    out = [[F(0)] * p for _ in range(n)]
    for i in range(n):
        for k in range(m):
            a_ik = a[i][k]
            if a_ik:
                row_b = b[k]
                for j in range(p):
                    if row_b[j]:
                        out[i][j] += a_ik * row_b[j]
    return out


def dag(a):
    return [[a[j][i] for j in range(len(a))] for i in range(len(a[0]))]


def embed(local, q, n):
    """Lift a 2x2 operator acting on qubit ``q`` into the full n-qubit space."""
    out = zeros(1 << n)
    for i in range(1 << n):
        for j in range(1 << n):
            if (i & ~(1 << q)) != (j & ~(1 << q)):
                continue
            a, b = (i >> q) & 1, (j >> q) & 1
            out[i][j] = local[a][b]
    return out


def embed_perm(table, n):
    """Lift a basis permutation ``table: index -> index`` on the full space."""
    out = zeros(1 << n)
    for i in range(1 << n):
        out[table(i)][i] = F(1)
    return out


def perms(op_kind, wires, n):
    """The basis permutation of a reversible gate, as a function on basis indices."""
    if op_kind in ("x", "cx", "ccx", "mcx"):
        *controls, target = wires
        return lambda v: v ^ (1 << target) if all(v >> c & 1 for c in controls) else v
    if op_kind == "swap":
        a, b = wires
        return lambda v: v ^ ((1 << a) | (1 << b)) if ((v >> a) ^ (v >> b)) & 1 else v
    if op_kind == "cswap":
        c, a, b = wires
        return lambda v: (
            v ^ ((1 << a) | (1 << b)) if (v >> c & 1) and (((v >> a) ^ (v >> b)) & 1) else v
        )
    raise ValueError(op_kind)


def diagonal_sign(op_kind, wires, n):
    """Diagonal sign as a function of the basis index (Z, CZ, CCZ, NEG)."""
    if op_kind == "neg":
        return lambda v: F(-1)
    return lambda v: F(-1) if all(v >> q & 1 for q in wires) else F(1)


def apply_diagonal(rho, sign, n):
    out = zeros(1 << n)
    for i in range(1 << n):
        for j in range(1 << n):
            if rho[i][j]:
                out[i][j] = rho[i][j] * sign(i) * sign(j)
    return out


def kraus_hmr(q, n):
    """X-basis measure followed by reset to |0>, scaled by sqrt(2).

    The true operator is ``|0><m_X|`` with ``|m_X> = (|0> + (-1)^m |1>)/sqrt2``.
    Scaling by sqrt(2) makes the single-qubit block ``[[1, (-1)^m]]`` on row 0.
    """
    family = []
    for m in (0, 1):
        local = [[F(0), F(0)], [F(0), F(0)]]
        local[0][0] = F(1)
        local[0][1] = F(-1) if m else F(1)
        family.append(embed(local, q, n))
    return family


def kraus_reset(q, n):
    """Trace out and prepare |0>: the family is ``{|0><0|, |0><1|}``.

    These must stay **separate** operators: ``sum_k A_k rho A_k^dag`` is the channel, and collapsing
    the family into ``A0 + A1`` first would give a different (non-trace-preserving) map. On
    ``|0><1|`` the correct result is the zero matrix, because that coherence has trace zero.
    """
    a0 = [[F(1), F(0)], [F(0), F(0)]]  # |0><0|
    a1 = [[F(0), F(1)], [F(0), F(0)]]  # |0><1|
    return [embed(a0, q, n), embed(a1, q, n)], F(1)


def kraus_measure_z(q, n):
    """Projective Z measurement: two projectors, trace preserving, no scaling."""
    p0 = [[F(1), F(0)], [F(0), F(0)]]
    p1 = [[F(0), F(0)], [F(0), F(1)]]
    return [embed(p0, q, n), embed(p1, q, n)], F(1)


def scale(mat, s):
    if s == 1:
        return mat
    return [[v * s for v in row] for row in mat]


def run(ops, n, rho_in, *, trace_after=None):
    """Apply a gate list to a density matrix; returns the exact final matrix.

    ``ops`` entries are ``(kind, wires)`` for gates without classical control, which is all the
    independent reference supports. Measurement outcomes are summed out, so this computes the
    unconditional channel, which is exactly what ``same_channel`` compares.
    """
    dim = 1 << n
    states = [(rho_in, F(1))]  # (matrix, accumulated scalar)
    for kind, wires in ops:
        if kind in ("x", "cx", "ccx", "mcx", "swap", "cswap"):
            U = embed_perm(perms(kind, wires, n), n)
            Ud = dag(U)
            states = [(matmul(matmul(U, r), Ud), s) for r, s in states]
        elif kind in ("z", "cz", "ccz", "neg"):
            sign = diagonal_sign(kind, wires, n)
            states = [(apply_diagonal(r, sign, n), s) for r, s in states]
        elif kind == "reset":
            fam, sc = kraus_reset(wires[0], n)
            states = [(scale(_sum_kraus(r, fam), sc), s) for r, s in states]
        elif kind == "measure_z":
            fam, sc = kraus_measure_z(wires[0], n)
            states = [(scale(_sum_kraus(r, fam), sc), s) for r, s in states]
        elif kind == "hmr":
            fam = kraus_hmr(wires[0], n)
            # each outcome operator was scaled by sqrt2, so the pair contributes twice the
            # true channel: divide by 2.
            states = [(scale(_sum_kraus(r, fam), F(1, 2)), s) for r, s in states]
        else:
            raise ValueError(kind)
    out = zeros(dim)
    for r, s in states:
        for i in range(dim):
            for j in range(dim):
                out[i][j] += r[i][j] * s
    if trace_after is not None and trace_after < n:
        out = partial_trace(out, trace_after, n)
    return out


def _sum_kraus(rho, family):
    n = len(rho)
    out = zeros(n)
    for A in family:
        tmp = matmul(matmul(A, rho), dag(A))
        for i in range(n):
            for j in range(n):
                out[i][j] += tmp[i][j]
    return out


def partial_trace(rho, keep, n):
    """Trace out every qubit with index >= ``keep`` (data wires are the low ones)."""
    dim = 1 << keep
    out = zeros(dim)
    for i in range(dim):
        for j in range(dim):
            acc = F(0)
            for high in range(1 << (n - keep)):
                acc += rho[i | (high << keep)][j | (high << keep)]
            out[i][j] = acc
    return out


def basis_rho(x, y, n=0, dim=None):
    d = dim if dim is not None else (1 << n)
    m = zeros(d)
    m[x][y] = F(1)
    return m


def channel_on_units(ops, data, ancillas, *, trace=True, max_cells=4_000_000):
    """Return {(x,y): matrix} for every |x><y|, or raise if it would be too large."""
    n = data + ancillas
    if (1 << n) ** 2 * (1 << data) ** 2 > max_cells:
        raise MemoryError("independent reference too large for this instance")
    out = {}
    for x, y in product(range(1 << data), repeat=2):
        rho = basis_rho(x, y, n)
        out[(x, y)] = run(ops, n, rho, trace_after=data if trace else None)
    return out
