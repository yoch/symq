"""Independent exact sparse branch oracle for one-ancilla error probabilities.

Test-only reference (it lives in ``tests/testkit``): it must stay independent of
``symq.labs.backward_ancilla``, ``symq.labs.shift_diagonal_ancilla`` and the
simulation helpers of ``symq.experimental.hybrid``. It was written for the
yoch/symq#147 wave-2 audit and checked there against an exact dense Kraus oracle
(11,006 basis diagonals and 1,500 superposition expectations, all identical).

Computes p(psi) = <psi|E|psi> = Pr[target ancilla reads 1 at the end] for a data
input psi (a sparse dict basis -> rational amplitude, default a basis state x)
with every ancilla initially |0>. It is independent of symq's simulation code
and of the symbolic checkers: it reads only the plain fields of each operation
(kind, wires, slot, condition, source, value).

Representation (exact, no square roots): a branch is (classical table,
rational vector v, rational D) standing for the unnormalized pure state
v / sqrt(D); its probability weight is ||v||^2 / D. Kraus maps:
  * permutation gates (x/cx/ccx/mcx/swap/cswap) and sign gates (z/cz/ccz/neg),
    optionally guarded by a classical condition 'bK' or '!bK';
  * hmr q -> slot: K_m = |0><m_X|_q, |m_X> = (|0> + (-1)^m |1>)/sqrt2:
        v' = v|q=0 + (-1)^m v|q=1 (placed at q=0), D' = 2 D, slot := m;
  * measure_z q -> slot: v' = v restricted to q=m, slot := m;
  * reset q: two Kraus branches (|0><0|, |0><1|), no record;
  * store / invert [condition] / oxor: classical table updates (self-reads ok).
Zero-weight branches are dropped. Two branches are merged only when their live
classical tables AND vectors are identical: the mixture |v><v|/D1 + |v><v|/D2 is
|v><v|/D with 1/D = 1/D1 + 1/D2 (exact). Slots never read again are dropped
from the table first (the obligation observes no final classical output).
Cost is bounded explicitly by max_branches and max_amplitudes.
"""
from __future__ import annotations

from fractions import Fraction

__all__ = ["SparseLimit", "error_probability"]

_PERM = {"x", "cx", "ccx", "mcx", "swap", "cswap"}
_SIGN = {"z", "cz", "ccz", "neg"}
_ARITY = {"x": 1, "cx": 2, "ccx": 3, "swap": 2, "cswap": 3, "z": 1, "cz": 2, "ccz": 3,
          "neg": 0, "hmr": 1, "measure_z": 1, "reset": 1, "store": 0, "invert": 0, "oxor": 0}


class SparseLimit(Exception):
    """A declared cap was reached; no probability is returned."""


def _perm(kind, wires, v):
    if kind in ("x", "cx", "ccx", "mcx"):
        *controls, t = wires
        return v ^ (1 << t) if all(v >> c & 1 for c in controls) else v
    a, b = wires[-2:]
    active = kind == "swap" or v >> wires[0] & 1
    return v ^ (1 << a) ^ (1 << b) if active and (v >> a & 1) != (v >> b & 1) else v


def _sign(kind, wires, v):
    return -1 if kind == "neg" or (kind != "neg" and all(v >> q & 1 for q in wires)) else 1


def _active(condition, table):
    if condition is None:
        return True
    negated = condition.startswith("!")
    return bool(table[condition[1:] if negated else condition]) != negated


def _check(program, target):
    data, ancillas = program.data, program.ancillas
    if type(data) is not int or type(ancillas) is not int or data < 1 or ancillas < 0:
        raise ValueError("bad widths")
    width = data + ancillas
    if type(target) is not int or not data <= target < width:
        raise ValueError("target must be an ancilla")
    init = set()
    for op in program.ops:
        k = op.kind
        if type(k) is not str or k not in _ARITY and k != "mcx":
            raise ValueError(f"unsupported op {k!r}")
        w = op.wires
        if (type(w) is not tuple or any(type(q) is not int or not 0 <= q < width for q in w)
                or len(set(w)) != len(w) or (k == "mcx" and len(w) < 2)
                or (k != "mcx" and len(w) != _ARITY[k])):
            raise ValueError("bad wires")
        reads = []
        if op.condition is not None:
            reads.append(op.condition.removeprefix("!"))
        if k in ("invert", "oxor"):
            reads.append(op.slot)
        if k == "oxor":
            reads.append(op.source)
        if any(r not in init for r in reads):
            raise ValueError("read of uninitialized slot")
        if k in ("hmr", "measure_z", "store"):
            init.add(op.slot)
    return width


def error_probability(program, target, x=None, *, psi=None, max_branches=1 << 16,
                      max_amplitudes=1 << 20):
    """Exact Pr[target = 1] for data basis input x (or sparse data state psi)."""
    _check(program, target)
    if psi is None:
        if type(x) is not int or not 0 <= x < 1 << program.data:
            raise ValueError("basis input outside data width")
        psi = {x: Fraction(1)}
    norm = sum(a * a for a in psi.values())
    if norm <= 0 or any(b >> program.data for b in psi):
        raise ValueError("nonzero data-only input state required")
    branches = [({}, dict(psi), Fraction(norm))]  # D = ||psi||^2 normalizes the input
    live_after, live = [], set()
    for op in reversed(program.ops):
        live_after.append(frozenset(live))
        if op.kind in ("hmr", "measure_z", "store"):
            live.discard(op.slot)
        if op.kind in ("invert", "oxor"):
            live.add(op.slot)
        if op.kind == "oxor":
            live.add(op.source)
        if op.condition is not None:
            live.add(op.condition.removeprefix("!"))
    live_after.reverse()
    for op, keep in zip(program.ops, live_after):
        k, nxt = op.kind, []
        for table, vec, d in branches:
            if k in ("store", "invert", "oxor"):
                table = dict(table)
                if k == "store":
                    table[op.slot] = op.value
                elif k == "invert":
                    table[op.slot] ^= int(_active(op.condition, table))
                else:
                    table[op.slot] ^= table[op.source]
                nxt.append((table, vec, d))
            elif k in _PERM or k in _SIGN:
                if _active(op.condition, table):
                    if k in _PERM:
                        vec = {_perm(k, op.wires, b): a for b, a in vec.items()}
                    else:
                        vec = {b: a * _sign(k, op.wires, b) for b, a in vec.items()}
                nxt.append((table, vec, d))
            else:
                q = 1 << op.wires[0]
                if k == "hmr":
                    outcomes = []
                    for m in (0, 1):
                        out = {}
                        for b, a in vec.items():
                            key = b & ~q
                            val = out.get(key, 0) + (-a if m and b & q else a)
                            if val:
                                out[key] = val
                            else:
                                out.pop(key, None)
                        outcomes.append((m, out, 2 * d))
                elif k == "measure_z":
                    outcomes = [(m, {b: a for b, a in vec.items() if bool(b & q) == bool(m)}, d)
                                for m in (0, 1)]
                elif k == "reset":
                    outcomes = [(None, {b & ~q: a for b, a in vec.items() if bool(b & q) == bool(m)}, d)
                                for m in (0, 1)]
                else:
                    raise ValueError(k)
                for m, out, dd in outcomes:
                    if not out:
                        continue
                    t2 = table if m is None else {**table, op.slot: m}
                    nxt.append((t2, out, dd))
        merged = {}
        for table, vec, d in nxt:
            table = {n: b for n, b in table.items() if n in keep}
            key = (tuple(sorted(table.items())), tuple(sorted(vec.items())))
            if key in merged:
                merged[key] = (table, vec, 1 / (1 / merged[key][2] + 1 / d))
            else:
                merged[key] = (table, vec, d)
        branches = list(merged.values())
        if len(branches) > max_branches:
            raise SparseLimit(f"branches {len(branches)} > {max_branches}")
        if sum(len(v) for _, v, _ in branches) > max_amplitudes:
            raise SparseLimit(f"amplitudes > {max_amplitudes}")
    total = Fraction(0)
    for _, vec, d in branches:
        total += sum((a * a for b, a in vec.items() if b >> target & 1), Fraction(0)) / d
    if not 0 <= total <= 1:
        raise ValueError("probability outside [0, 1]: the input program is outside this oracle")
    return total
