"""Static feed-forward compiler for c*sum_j <s_j, a*b_j> over GF(2^m).

Research fragment; no whole-circuit qualification.
Classical nodes are a bounded, topologically ordered Boolean DAG. Quantum gates
are classically guarded CX/CCZ; there is no outcome-indexed exponential dispatch.
All live quantum inputs are restored, without a fresh quantum ancilla.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def multiply(a: int, b: int, m: int, modulus: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        b >>= 1
        a <<= 1
        if a >> m:
            a ^= modulus
    return r


def poly_rem(a: int, b: int) -> int:
    while a and a.bit_length() >= b.bit_length():
        a ^= b << (a.bit_length() - b.bit_length())
    return a


def poly_gcd(a: int, b: int) -> int:
    while b:
        a, b = b, poly_rem(a, b)
    return a


def is_irreducible(m: int, modulus: int) -> bool:
    if modulus.bit_length() != m + 1 or not modulus & 1:
        return False
    # Rabin criterion with all k <= floor(m/2), inexpensive at our bounded m.
    x, z = 2, 2
    for k in range(1, m + 1):
        z = multiply(z, z, m, modulus)
        if k <= m // 2 and poly_gcd(z ^ x, modulus) != 1:
            return False
    return z == x


@dataclass
class BooleanDAG:
    n_inputs: int

    def __post_init__(self) -> None:
        self.nodes: list[list[object]] = []
        self.cache: dict[tuple[str, int, int], int] = {}

    def make(self, op: str, a: int, b: int) -> int:
        if a > b:
            a, b = b, a
        if op == "xor":
            if a == b:
                return 0
            if a == 0:
                return b
        elif op == "and":
            if a == 0:
                return 0
            if a == 1 or a == b:
                return b
        else:
            raise ValueError(op)
        key = (op, a, b)
        if key not in self.cache:
            self.cache[key] = 2 + self.n_inputs + len(self.nodes)
            self.nodes.append([op, a, b])
        return self.cache[key]

    def xor(self, a: int, b: int) -> int:
        return self.make("xor", a, b)

    def and_(self, a: int, b: int) -> int:
        return self.make("and", a, b)

    def not_(self, a: int) -> int:
        return self.xor(1, a)

    def any_(self, bits: list[int]) -> int:
        out = 0
        for b in bits:
            out = self.xor(self.xor(out, b), self.and_(out, b))
        return out

    def parity(self, bits: list[int], mask: int) -> int:
        out = 0
        for i, b in enumerate(bits):
            if mask >> i & 1:
                out = self.xor(out, b)
        return out

    def swap_words(self, a: list[int], b: list[int], g: int) -> tuple[list[int], list[int]]:
        d = [self.and_(g, self.xor(x, y)) for x, y in zip(a, b, strict=True)]
        return (
            [self.xor(x, z) for x, z in zip(a, d, strict=True)],
            [self.xor(y, z) for y, z in zip(b, d, strict=True)],
        )


def compile_bank(m: int, modulus: int, bank: int = 1) -> dict:
    """Compile a polynomial-size static classical/quantum feed-forward program.

    Wire order: c, a[0:m], b_0[0:m], ..., b_{bank-1}[0:m].
    Outcome bits are LSB first within each measured m-bit garbage word.
    The phase predicate is NOT a proof that a given garbage has this value.
    """
    if type(m) is not int or not 2 <= m <= 16:
        raise ValueError("m must be an integer in [2,16]")
    if type(bank) is not int or not 1 <= bank <= 128:
        raise ValueError("bank must be an integer in [1,128]")
    if type(modulus) is not int or not is_irreducible(m, modulus):
        raise ValueError("irreducible degree-m modulus required")
    dag = BooleanDAG(m * bank)
    outcomes = [[2 + j * m + i for i in range(m)] for j in range(bank)]
    prep: list[list[object]] = []

    def cx(dst: list, i: int, j: int, g: int) -> None:
        if g:
            dst.append(["cx", i, j, g])

    def swap(dst: list, i: int, j: int, g: int) -> None:
        cx(dst, i, j, g)
        cx(dst, j, i, g)
        cx(dst, i, j, g)

    def b_wire(j: int, i: int) -> int:
        return 1 + m + j * m + i

    # Move the first nonzero outcome block to position zero, together with its B.
    for j in range(1, bank):
        g = dag.and_(dag.not_(dag.any_(outcomes[0])), dag.any_(outcomes[j]))
        outcomes[0], outcomes[j] = dag.swap_words(outcomes[0], outcomes[j], g)
        for i in range(m):
            swap(prep, b_wire(0, i), b_wire(j, i), g)

    active = dag.any_(outcomes[0])
    tensor = [[multiply(1 << i, 1 << k, m, modulus) for k in range(m)] for i in range(m)]
    matrices = [
        [[dag.parity(outcomes[j], tensor[i][k]) for k in range(m)] for i in range(m)]
        for j in range(bank)
    ]
    matrix = [row.copy() for row in matrices[0]]
    # In the all-zero branch substitute I, but skip the phase gates.
    for i in range(m):
        matrix[i][i] = dag.xor(matrix[i][i], dag.not_(active))
    row_ops: list[list[object]] = []
    for k in range(m):
        for j in range(k + 1, m):
            g = dag.and_(dag.not_(matrix[k][k]), matrix[j][k])
            matrix[k], matrix[j] = dag.swap_words(matrix[k], matrix[j], g)
            swap(row_ops, b_wire(0, k), b_wire(0, j), g)
        for i in range(m):
            if i == k:
                continue
            g = matrix[i][k]
            matrix[i] = [
                dag.xor(x, dag.and_(g, y)) for x, y in zip(matrix[i], matrix[k], strict=True)
            ]
            cx(row_ops, b_wire(0, k), b_wire(0, i), g)
    # If E_r...E_1 K = I, applying E_r first builds K on the quantum B register.
    prep.extend(reversed(row_ops))
    for j in range(1, bank):
        for i in range(m):
            for k in range(m):
                cx(prep, b_wire(j, k), b_wire(0, i), matrices[j][i][k])
    phase = [["ccz", 0, 1 + i, b_wire(0, i), active] for i in range(m)]
    result = {
        "schema": "bilinear-phase-fusion-v1",
        "field": {"m": m, "modulus": modulus},
        "bank": bank,
        "n_inputs": m * bank,
        "width": 1 + m * (bank + 1),
        "classical": dag.nodes,
        "quantum": prep + phase + list(reversed(prep)),
    }
    return result


def branch(program: dict, outcomes: list[int]) -> list[list[object]]:
    from .checker import validate

    validate(program)
    m = program["field"]["m"]
    if len(outcomes) != program["bank"] or any(
        type(s) is not int or not 0 <= s < 1 << m for s in outcomes
    ):
        raise ValueError("invalid outcome words")
    bits = [0, 1] + [(s >> i) & 1 for s in outcomes for i in range(m)]
    for op, a, b in program["classical"]:
        bits.append(bits[a] ^ bits[b] if op == "xor" else bits[a] & bits[b])
    return [g[:-1] for g in program["quantum"] if bits[g[-1]]]
