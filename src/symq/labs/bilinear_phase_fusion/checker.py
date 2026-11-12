"""Independent exact replay checker; does not import the compiler or optimizer.

It compares bilinear coefficient matrices, not sampled quantum input values.
Every quantum wire must be restored. The accepted fragment is deliberately narrow.
A success proves a diagonal correction for ONE supplied measurement outcome.
It does not prove the garbage/preparation relation in an enclosing circuit.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from functools import lru_cache


class Rejected(ValueError):
    pass


class Inconclusive(TimeoutError):
    pass


def _integer(x: object, low: int, high: int) -> bool:
    return type(x) is int and low <= x < high


def _deadline(seconds: float) -> float:
    if type(seconds) not in (int, float) or not math.isfinite(seconds):
        raise Rejected("seconds must be finite")
    if seconds <= 0:
        raise Inconclusive("budget exhausted")
    return time.monotonic() + seconds


def validate(program: dict, *, check=lambda: None) -> None:
    keys = {"schema", "field", "bank", "n_inputs", "width", "classical", "quantum"}
    if (
        type(program) is not dict
        or set(program) != keys
        or program["schema"] != "bilinear-phase-fusion-v1"
    ):
        raise Rejected("schema")
    field = program["field"]
    if type(field) is not dict or set(field) != {"m", "modulus"}:
        raise Rejected("field schema")
    m = field["m"]
    if not _integer(m, 2, 17) or not _integer(program["bank"], 1, 129):
        raise Rejected("bounded dimensions")
    modulus = field["modulus"]
    if not _integer(modulus, 1 << m, 1 << (m + 1)) or not modulus & 1:
        raise Rejected("modulus")
    # Irreducibility is unnecessary to check a particular correction identity.
    # It is required by the compiler to guarantee all nonzero branches full rank.
    bank = program["bank"]
    if type(program["n_inputs"]) is not int or program["n_inputs"] != m * bank:
        raise Rejected("inputs")
    if type(program["width"]) is not int or program["width"] != 1 + m * (1 + bank):
        raise Rejected("width")
    c = program["classical"]
    q = program["quantum"]
    if type(c) is not list or type(q) is not list or len(c) > 2_000_000 or len(q) > 200_000:
        raise Rejected("program bounds")
    for i, node in enumerate(c):
        check()
        bound = 2 + m * bank + i
        if (
            type(node) is not list
            or len(node) != 3
            or type(node[0]) is not str
            or node[0] not in ("xor", "and")
        ):
            raise Rejected("classical operation")
        if not all(_integer(x, 0, bound) for x in node[1:]):
            raise Rejected("forward/invalid classical reference")
    bound = 2 + m * bank + len(c)
    for g in q:
        check()
        if (
            type(g) is not list
            or len(g) not in (4, 5)
            or type(g[0]) is not str
            or not _integer(g[-1], 0, bound)
        ):
            raise Rejected("gate or guard")
        if g[0] == "cx" and len(g) == 4:
            if not all(_integer(w, m + 1, program["width"]) for w in g[1:3]) or g[1] == g[2]:
                raise Rejected("CX restricted to distinct B wires")
        elif g[0] == "ccz" and len(g) == 5:
            if (
                type(g[1]) is not int
                or g[1] != 0
                or not _integer(g[2], 1, m + 1)
                or not _integer(g[3], m + 1, program["width"])
            ):
                raise Rejected("CCZ requires c, one A wire, one B wire")
        else:
            raise Rejected("unsupported gate")


def multiplication_oracle(x: int, y: int, degree: int, polynomial: int) -> int:
    # Deliberately different from compiler's shift-and-reduce multiplication.
    raw = 0
    for i in range(degree):
        for j in range(degree):
            if ((x >> i) & 1) and ((y >> j) & 1):
                raw ^= 1 << (i + j)
    for k in range(2 * degree - 2, degree - 1, -1):
        if (raw >> k) & 1:
            raw ^= polynomial << (k - degree)
    return raw


@lru_cache(maxsize=32)
def _basis_tensor(m: int, modulus: int) -> tuple[tuple[int, ...], ...]:
    return tuple(
        tuple(multiplication_oracle(1 << i, 1 << k, m, modulus) for k in range(m)) for i in range(m)
    )


def binary_rank(rows: list[int]) -> int:
    basis = {}
    for value in rows:
        while value:
            pivot = value.bit_length() - 1
            if pivot in basis:
                value ^= basis[pivot]
            else:
                basis[pivot] = value
                break
    return len(basis)


def _bits(program: dict, outcomes: list[int], *, check=lambda: None) -> list[int]:
    m = program["field"]["m"]
    if (
        type(outcomes) is not list
        or len(outcomes) != program["bank"]
        or not all(_integer(x, 0, 1 << m) for x in outcomes)
    ):
        raise Rejected("outcomes")
    values = [0, 1]
    for word in outcomes:
        for i in range(m):
            values.append((word >> i) & 1)
    for node in program["classical"]:
        check()
        a, b = values[node[1]], values[node[2]]
        if node[0] == "xor":
            values.append(int(a != b))
        else:
            values.append(int(a == 1 and b == 1))
    return values


def check_outcome(program: dict, outcomes: list[int], *, seconds: float = 30.0) -> dict:
    deadline = _deadline(seconds)

    def check():
        if time.monotonic() >= deadline:
            raise Inconclusive("budget exhausted")

    validate(program, check=check)
    values = _bits(program, outcomes, check=check)
    m, modulus = program["field"]["m"], program["field"]["modulus"]
    bsize = m * program["bank"]
    linear = [1 << i for i in range(bsize)]
    phase = [0] * m
    count = Counter()
    offset = m + 1
    for index, g in enumerate(program["quantum"]):
        if index % 256 == 0 and time.monotonic() > deadline:
            raise Inconclusive("budget exhausted")
        if not values[g[-1]]:
            continue
        count[g[0]] += 1
        if g[0] == "cx":
            linear[g[2] - offset] ^= linear[g[1] - offset]
        else:
            phase[g[2] - 1] ^= linear[g[3] - offset]
    if any(value != 1 << i for i, value in enumerate(linear)):
        raise Rejected("B restoration failed")
    expected = [0] * m
    tensor = _basis_tensor(m, modulus)
    for i in range(m):
        for j, outcome in enumerate(outcomes):
            for k in range(m):
                v = tensor[i][k]
                if (v & outcome).bit_count() & 1:
                    expected[i] ^= 1 << (j * m + k)
    if phase != expected:
        raise Rejected("phase coefficient mismatch")
    if time.monotonic() > deadline:
        raise Inconclusive("budget exhausted")
    return {
        "outcomes": outcomes,
        "cx": count["cx"],
        "ccz": count["ccz"],
        "coefficients_checked": m * bsize,
        "restored_wires": program["width"],
        "bilinear_rank": binary_rank(expected),
    }


def canonical_digest(obj: object) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(text).hexdigest()


def check_certificate(program: dict, certificate: dict) -> dict:
    if type(certificate) is not dict or set(certificate) != {
        "schema",
        "program_sha256",
        "outcomes",
    }:
        raise Rejected("certificate schema; claimed success flags are not accepted")
    if certificate["schema"] != "bilinear-phase-branch-v1" or certificate[
        "program_sha256"
    ] != canonical_digest(program):
        raise Rejected("source binding")
    # Never trust a stored positive verdict. Reconstruct and compare the matrices.
    return check_outcome(program, certificate["outcomes"])


def load_strict(path: str) -> dict:
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise Rejected("duplicate JSON key")
            result[k] = v
        return result

    def bad_constant(x):
        raise Rejected(f"nonfinite JSON constant: {x}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=pairs, parse_constant=bad_constant)
