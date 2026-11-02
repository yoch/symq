"""Independent dense cq-state oracle for HMR table loaders (issue #144 research).

It shares no code with ``symq.labs.hmr_table_contract`` (ket trajectories with sign
bookkeeping) nor with the density evolution of ``symq.experimental.hybrid``. Every
instruction is turned into an explicit local integer matrix ``M`` on its wires and applied
to a sparse density operator as ``rho -> M rho M^T``:

* HMR with outcome m uses the scaled Kraus matrix ``sqrt(2) |0><(+|-)|`` = ``[[1, (-1)^m],
  [0, 0]]`` and multiplies the result by 1/2, so all arithmetic is exact rationals;
* Z measurement uses the projector of its outcome, reset sums ``|0><0|`` and ``|0><1|``;
* classically controlled gates act on the cq-branches whose memory satisfies the condition.

Wires beyond the program's width are an external reference that no instruction touches, so
``(E (x) id_R)(rho)`` is computed directly. Records are forgotten (summed) unless observed.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product

from symq.experimental.hybrid import HybridProgram

Matrix = dict[tuple[int, int], Fraction]
Local = dict[int, list[tuple[int, int]]]
"""Local matrix by input column: ``in -> [(out, coefficient)]``."""


def _columns(entries: dict[tuple[int, int], int], size: int) -> Local:
    columns: Local = {i: [] for i in range(size)}
    for (out, inp), value in entries.items():
        if value:
            columns[inp].append((out, value))
    return columns


def _gate(kind: str, arity: int) -> Local:
    """Local unitary matrix of a gate on ``arity`` wires (local bit i = i-th listed wire)."""
    size = 1 << arity
    entries: dict[tuple[int, int], int] = {}
    for inp in range(size):
        bits = [(inp >> i) & 1 for i in range(arity)]
        if kind in {"x", "cx", "ccx", "mcx"}:
            out = inp ^ (1 << (arity - 1)) if all(bits[:-1]) else inp
            entries[out, inp] = 1
        elif kind == "swap":
            entries[(bits[1] | bits[0] << 1), inp] = 1
        elif kind == "cswap":
            out = (bits[0] | bits[2] << 1 | bits[1] << 2) if bits[0] else inp
            entries[out, inp] = 1
        elif kind in {"z", "cz", "ccz"}:
            entries[inp, inp] = -1 if all(bits) else 1
        elif kind == "neg":
            entries[inp, inp] = -1
        else:
            raise AssertionError(kind)
    return _columns(entries, size)


def _hmr(outcome: int) -> Local:
    return _columns({(0, 0): 1, (0, 1): -1 if outcome else 1}, 2)


def _projector(outcome: int) -> Local:
    return _columns({(outcome, outcome): 1}, 2)


def _get(state: int, wires: tuple[int, ...]) -> int:
    return sum(((state >> w) & 1) << i for i, w in enumerate(wires))


def _set(state: int, wires: tuple[int, ...], value: int) -> int:
    for i, w in enumerate(wires):
        state = (state & ~(1 << w)) | (((value >> i) & 1) << w)
    return state


def _conjugate(rho: Matrix, local: Local, wires: tuple[int, ...],
               scale: Fraction = Fraction(1)) -> Matrix:
    """``scale * M rho M^T`` with M acting on ``wires`` (real matrices only)."""
    out: Matrix = {}
    for (row, col), value in rho.items():
        for r_out, r_coeff in local[_get(row, wires)]:
            for c_out, c_coeff in local[_get(col, wires)]:
                key = (_set(row, wires, r_out), _set(col, wires, c_out))
                out[key] = out.get(key, Fraction(0)) + scale * r_coeff * c_coeff * value
    return {k: v for k, v in out.items() if v}


def _holds(condition: str | None, memory: dict[str, int]) -> bool:
    if condition is None:
        return True
    negated = condition[0] == "!"
    return bool(memory[condition.lstrip("!")]) != negated


def evolve(program: HybridProgram, rho: Matrix, *,
           observed: tuple[str, ...] = ()) -> dict[tuple[int, ...], Matrix]:
    """``(E (x) id)(rho)`` keyed by the final values of the observed slots.

    ``rho`` is over the program wires plus any higher reference wires; the caller puts
    the program's ancilla wires in |0>.
    """
    program.validate()
    branches: list[tuple[dict[str, int], Matrix]] = [({}, dict(rho))]
    half = Fraction(1, 2)
    for op in program.ops:
        kind, wires = op.kind, op.wires
        step: list[tuple[dict[str, int], Matrix]] = []
        for memory, state in branches:
            if kind == "hmr" or kind == "measure_z":
                for outcome in (0, 1):
                    if kind == "hmr":
                        image = _conjugate(state, _hmr(outcome), wires, half)
                    else:
                        image = _conjugate(state, _projector(outcome), wires)
                    if image:
                        step.append(({**memory, op.slot: outcome}, image))
            elif kind == "reset":
                zero = _conjugate(state, _columns({(0, 0): 1}, 2), wires)
                one = _conjugate(state, _columns({(0, 1): 1}, 2), wires)
                total = dict(zero)
                for key, value in one.items():
                    total[key] = total.get(key, Fraction(0)) + value
                step.append((memory, {k: v for k, v in total.items() if v}))
            elif kind == "store":
                step.append(({**memory, op.slot: op.value}, state))
            elif kind == "invert":
                flip = int(_holds(op.condition, memory))
                step.append(({**memory, op.slot: memory[op.slot] ^ flip}, state))
            elif kind == "oxor":
                step.append(({**memory, op.slot: memory[op.slot] ^ memory[op.source]}, state))
            elif _holds(op.condition, memory):
                step.append((memory, _conjugate(state, _gate(kind, len(wires)), wires)))
            else:
                step.append((memory, state))
        branches = step
    result: dict[tuple[int, ...], Matrix] = {}
    for memory, state in branches:
        target = result.setdefault(tuple(memory[s] for s in observed), {})
        for key, value in state.items():
            target[key] = target.get(key, Fraction(0)) + value
    return {k: {p: v for p, v in m.items() if v} for k, m in result.items()}


def forgotten(program: HybridProgram, rho: Matrix) -> Matrix:
    """The outcome-forgotten channel image (every record summed)."""
    return evolve(program, rho).get((), {})


def trace_wires(rho: Matrix, wires: tuple[int, ...]) -> Matrix:
    """Partial trace over ``wires``: keep entries whose traced bits agree, then clear them."""
    mask = sum(1 << w for w in wires)
    out: Matrix = {}
    for (row, col), value in rho.items():
        if row & mask == col & mask:
            key = (row & ~mask, col & ~mask)
            out[key] = out.get(key, Fraction(0)) + value
    return {k: v for k, v in out.items() if v}


def basis_states(address: tuple[int, ...], target: tuple[int, ...],
                 borrowed: tuple[int, ...], legal: tuple[int, ...]) -> list[int]:
    """Legal basis inputs (full target cube, clean wires zero), enumerated independently."""
    states = []
    for a, z, d in product(legal, range(1 << len(target)), range(1 << len(borrowed))):
        states.append(_set(_set(_set(0, address, a), target, z), borrowed, d))
    return states


def xor_image(state: int, address: tuple[int, ...], target: tuple[int, ...],
              table: tuple[int, ...]) -> int:
    """``W`` on one basis state, straight from the table rows."""
    return _set(state, target, _get(state, target) ^ table[_get(state, address)])


def ideal(rho: Matrix, address: tuple[int, ...], target: tuple[int, ...],
          table: tuple[int, ...]) -> Matrix:
    return {(xor_image(r, address, target, table), xor_image(c, address, target, table)): v
            for (r, c), v in rho.items()}


def unit(x: int, y: int) -> Matrix:
    return {(x, y): Fraction(1)}


def pure(vector: dict[int, int]) -> Matrix:
    """Unnormalised ``|psi><psi|`` of an integer vector."""
    return {(r, c): Fraction(a * b) for r, a in vector.items() for c, b in vector.items()
            if a * b}


def first_difference(program: HybridProgram, states: list[int], address: tuple[int, ...],
                     target: tuple[int, ...], table: tuple[int, ...]
                     ) -> tuple[int, int] | None:
    """First legal coherence ``|x><y|`` whose image differs from ``W|x><y|W^T``."""
    for x, y in product(states, repeat=2):
        if forgotten(program, unit(x, y)) != ideal(unit(x, y), address, target, table):
            return x, y
    return None
