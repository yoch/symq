"""Independently reconstructed rank-15 bilinear GF(64) certificate.

GF(64) is represented in the polynomial basis modulo x^6+x+1.  The
construction uses the tower GF(4)[z]/(z^3+z+1), evaluates a degree-2
polynomial at 0, 1, omega, omega^2 and infinity, and decomposes each
GF(4) multiplication into three GF(2) products.

References (not imported or copied): Polytof, ZIB-IOL, MIT license,
https://github.com/ZIB-IOL/polytof at 0dcac107d15adc34dc646242d222f21ae7d32699,
'scripts/make_cpd_gf.py' (scheme_n6), arXiv:2602.15285.

This is a constructive 15-term upper bound, not an optimality proof, a
Kaggle circuit, or a claim of an official score improvement.
"""
from __future__ import annotations

from functools import lru_cache

N = 6
MODULUS = 0x43  # x^6 + x + 1


def _gf4_mul(a: int, b: int) -> int:
    """Multiply in GF(4)=GF(2)[omega]/(omega^2+omega+1)."""
    if not (0 <= a < 4 and 0 <= b < 4):
        raise ValueError("GF(4) element is outside 0..3")
    p = ((a & 1) & (b & 1)) ^ (((a >> 1) & 1) & ((b >> 1) & 1))
    q = ((a & 1) & ((b >> 1) & 1)) ^ (((a >> 1) & 1) & (b & 1)) ^ (
        ((a >> 1) & 1) & ((b >> 1) & 1)
    )
    return p | (q << 1)


def _gf4_pow(a: int, power: int) -> int:
    out = 1
    for _ in range(power):
        out = _gf4_mul(out, a)
    return out


def _tower_mul(a: int, b: int) -> int:
    """Exact independent 6-bit tower oracle, z^3=z+1."""
    if not (0 <= a < 64 and 0 <= b < 64):
        raise ValueError("tower field element is outside 0..63")
    lhs = [(a >> (2 * i)) & 3 for i in range(3)]
    rhs = [(b >> (2 * i)) & 3 for i in range(3)]
    p = [0] * 5
    for i in range(3):
        for j in range(3):
            p[i + j] ^= _gf4_mul(lhs[i], rhs[j])
    for k in (4, 3):
        v = p[k]
        p[k - 3] ^= v
        p[k - 2] ^= v
    return p[0] | (p[1] << 2) | (p[2] << 4)


def _linear_rank(columns: tuple[int, ...]) -> int:
    pivots: dict[int, int] = {}
    for c in columns:
        while c:
            p = c.bit_length() - 1
            if p not in pivots:
                pivots[p] = c
                break
            c ^= pivots[p]
    return len(pivots)


def _isomorphism() -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Find explicit F2-linear isomorphism from polynomial to tower basis."""
    for generator in range(2, 64):
        powers = [1]
        for _ in range(6):
            powers.append(_tower_mul(powers[-1], generator))
        if powers[6] != (generator ^ 1) or _linear_rank(tuple(powers[:6])) != 6:
            continue
        def forward(x: int) -> int:
            value = 0
            for i in range(6):
                if (x >> i) & 1:
                    value ^= powers[i]
            return value
        fwd = tuple(forward(i) for i in range(64))
        if len(set(fwd)) != 64:
            raise AssertionError("non-bijective field isomorphism")
        inverse = [0] * 64
        for i, j in enumerate(fwd):
            inverse[j] = i
        return fwd, tuple(inverse)
    raise AssertionError("no field isomorphism found")


def _gf4_solve(matrix: tuple[tuple[int, ...], ...], rhs: tuple[int, ...]) -> tuple[int, ...]:
    n = len(rhs)
    rows = [list(matrix[i]) + [rhs[i]] for i in range(n)]
    for col in range(n):
        pivot = next((i for i in range(col, n) if rows[i][col]), None)
        if pivot is None:
            raise AssertionError("singular GF(4) interpolation")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        inv = _gf4_pow(rows[col][col], 2)  # inverse of a !=0 in GF(4)
        rows[col] = [_gf4_mul(inv, val) for val in rows[col]]
        for i in range(n):
            if i != col and rows[i][col]:
                scale = rows[i][col]
                rows[i] = [a ^ _gf4_mul(scale, b)
                           for a, b in zip(rows[i], rows[col])]
    return tuple(row[-1] for row in rows)


POINTS = (0, 1, 2, 3)  # finite evaluation points; fifth point is infinity
_MATRIX = tuple(tuple(_gf4_pow(t, j) for j in range(4)) for t in POINTS)


def _evaluate(value: int, sample: int) -> int:
    if sample == 4:  # infinity
        return (value >> 4) & 3
    t = POINTS[sample]
    return ((value & 3) ^ _gf4_mul((value >> 2) & 3, t)
            ^ _gf4_mul((value >> 4) & 3, _gf4_pow(t, 2)))


def _reconstruct_from_one_sample(sample: int, value: int) -> int:
    high = value if sample == 4 else 0
    rhs = tuple((value if j == sample else 0) ^
                _gf4_mul(high, _gf4_pow(t, 4))
                for j, t in enumerate(POINTS))
    c0, c1, c2, c3 = _gf4_solve(_MATRIX, rhs)
    return (c0 ^ c3) | ((c1 ^ c3 ^ high) << 2) | ((c2 ^ high) << 4)


@lru_cache(maxsize=1)
def rank15_terms() -> tuple[tuple[int, int, int], ...]:
    """Triples (left linear form, right linear form, output XOR mask).

    Exactly 5 outer interpolation points times 3 inner GF(4) products.
    Each equality can be checked independently as a 6x6x6 GF(2) tensor.
    """
    to_tower, to_poly = _isomorphism()
    terms: list[tuple[int, int, int]] = []
    for sample in range(5):
        left_bit0 = sum(((_evaluate(to_tower[1 << i], sample) >> 0) & 1) << i
                        for i in range(6))
        left_bit1 = sum(((_evaluate(to_tower[1 << i], sample) >> 1) & 1) << i
                        for i in range(6))
        # GF(4) Karatsuba: p0=l0*r0; p1=l1*r1; p2=(l0+l1)*(r0+r1)
        # GF(4) product = (p0+p1) + omega*(p0+p2).
        for left, right, piece in (
            (left_bit0, left_bit0, 0b11),
            (left_bit1, left_bit1, 0b01),
            (left_bit0 ^ left_bit1, left_bit0 ^ left_bit1, 0b10),
        ):
            reduced_tower = _reconstruct_from_one_sample(sample, piece)
            terms.append((left, right, to_poly[reduced_tower]))
    if len(terms) != 15 or any(not (a and b and w) for a, b, w in terms):
        raise AssertionError("rank-15 construction contains zero terms")
    return tuple(terms)
