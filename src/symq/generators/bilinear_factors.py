"""Exact GF(16)/GF(64) tensor-rank constructions from a GF(4) tower.

The 9/15-factor decompositions are obtained by multiplication via interpolation
in GF(4)[z], followed by an explicit GF(2)-linear field-basis isomorphism.
The precise polynomial modulus is required; 0x43 and 0x49 name different
representations of GF(64) and may not be interchanged.

Mathematical context: Polytof (ZIB-IOL/polytof, MIT), pinned at
0dcac107d15adc34dc646242d222f21ae7d32699; the public James Barlow
VQCC bilinear KMB evaluation corpus (Apache-2.0) motivated these cases.
This is original, self-contained standard-library Python code, not a copy
of either upstream software. It is a constructive upper bound, not a
proof of minimum rank or a compiler-level substitution theorem.
"""
from __future__ import annotations

from functools import lru_cache

from .bilinear_optimization import certify_decomposition
from .gf2n import Term, is_irreducible

__all__ = ["tower_factors"]


def _mul4(a: int, b: int) -> int:
    """GF(4) multiply modulo omega**2 + omega + 1, 0 <= a,b <= 3."""
    a0, a1 = a & 1, (a >> 1) & 1
    b0, b1 = b & 1, (b >> 1) & 1
    low = (a0 & b0) ^ (a1 & b1)
    high = (a0 & b1) ^ (a1 & b0) ^ (a1 & b1)
    return low | (high << 1)


def _pow4(a: int, exponent: int) -> int:
    out = 1
    for _ in range(exponent):
        out = _mul4(out, a)
    return out


def _mul_tower(a: int, b: int, degree: int) -> int:
    """GF(4)[z]/(z^2+z+omega) or GF(4)[z]/(z^3+z+1)."""
    x = tuple((a >> (2 * i)) & 3 for i in range(degree))
    y = tuple((b >> (2 * i)) & 3 for i in range(degree))
    coeff = [0] * (2 * degree - 1)
    for i in range(degree):
        for j in range(degree):
            coeff[i + j] ^= _mul4(x[i], y[j])
    if degree == 2:
        coeff[0] ^= _mul4(2, coeff[2])
        coeff[1] ^= coeff[2]
    else:
        for j in (4, 3):
            coeff[j - 3] ^= coeff[j]
            coeff[j - 2] ^= coeff[j]
    return sum(coeff[i] << (2 * i) for i in range(degree))


def _rank(columns: list[int]) -> int:
    pivots: dict[int, int] = {}
    for column in columns:
        while column:
            leading = column.bit_length() - 1
            if leading not in pivots:
                pivots[leading] = column
                break
            column ^= pivots[leading]
    return len(pivots)


def _isomorphism(degree: int, modulus: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Find the first full-rank root of the caller's monic polynomial in the tower."""
    n = degree * 2
    size = 1 << n
    for generator in range(2, size):
        powers = [1]
        for _ in range(n):
            powers.append(_mul_tower(powers[-1], generator, degree))
        value = 0
        for i in range(n + 1):
            if modulus >> i & 1:
                value ^= powers[i]
        if value != 0 or _rank(powers[:n]) != n:
            continue
        forward = tuple(
            _linear_apply(powers, a) for a in range(size)
        )
        if len(set(forward)) != size:
            raise AssertionError("rank check and field basis disagree")
        inverse = [0] * size
        for index, image in enumerate(forward):
            inverse[image] = index
        return forward, tuple(inverse)
    raise ValueError("no GF(2)-linear tower isomorphism for the specified modulus")


def _linear_apply(columns: list[int], x: int) -> int:
    result = 0
    for index in range(x.bit_length()):
        if x >> index & 1:
            result ^= columns[index]
    return result


def _solve_vandermonde(rhs: tuple[int, ...]) -> tuple[int, ...]:
    """Solve four evaluation equations for a cubic over GF(4)."""
    points = (0, 1, 2, 3)
    rows = [
        [_pow4(t, j) for j in range(4)] + [rhs[i]]
        for i, t in enumerate(points)
    ]
    for col in range(4):
        pivot = next((r for r in range(col, 4) if rows[r][col]), None)
        if pivot is None:
            raise ArithmeticError("noninvertible GF(4) interpolation matrix")
        rows[pivot], rows[col] = rows[col], rows[pivot]
        inverse = _pow4(rows[col][col], 2)
        rows[col] = [_mul4(inverse, v) for v in rows[col]]
        for r in range(4):
            if r != col and rows[r][col]:
                scale = rows[r][col]
                rows[r] = [rows[r][i] ^ _mul4(scale, rows[col][i])
                           for i in range(5)]
    return tuple(row[-1] for row in rows)


def _evaluation(value: int, sample: int, degree: int) -> int:
    if degree == 2:
        if sample == 0:
            return value & 3
        if sample == 1:
            return (value & 3) ^ ((value >> 2) & 3)
        return (value >> 2) & 3  # infinity
    if sample == 4:
        return (value >> 4) & 3  # infinity
    point = (0, 1, 2, 3)[sample]
    return ((value & 3) ^ _mul4((value >> 2) & 3, point)
            ^ _mul4((value >> 4) & 3, _pow4(point, 2)))


def _interpolate(sample: int, result: int, degree: int) -> int:
    if degree == 2:
        if sample == 0:
            return result | (result << 2)
        if sample == 1:
            return result << 2
        return _mul4(result, 2)
    highest = result if sample == 4 else 0
    rhs = tuple(
        (result if sample == i else 0) ^ _mul4(highest, _pow4(point, 4))
        for i, point in enumerate((0, 1, 2, 3))
    )
    a0, a1, a2, a3 = _solve_vandermonde(rhs)
    return (a0 ^ a3) | ((a1 ^ a3 ^ highest) << 2) | ((a2 ^ highest) << 4)


def tower_factors(n: int, modulus: int) -> tuple[Term, ...]:
    """Return an exact 9- or 15-product GF(2^n) multiplication tensor.

    Caller must state the polynomial basis, not just the abstract field.
    Reject unsupported widths and reducible/malformed polynomials. Output is
    immutable; it can be used directly with a one-CCX-per-factor emitter.
    """
    # Validated before the cache: equal-hashing floats such as 4.0 must not hit a cached entry.
    if type(n) is not int or n not in (4, 6):
        raise ValueError("tower-rank construction supports only n=4 or n=6")
    if type(modulus) is not int or not is_irreducible(n, modulus):
        raise ValueError("modulus must be a monic irreducible degree-n GF(2) polynomial")
    return _tower_factors(n, modulus)


@lru_cache(maxsize=16)
def _tower_factors(n: int, modulus: int) -> tuple[Term, ...]:
    degree = n // 2
    forward, inverse = _isomorphism(degree, modulus)
    factors: list[Term] = []
    for sample in range(2 * degree - 1):
        l0 = sum(((_evaluation(forward[1 << i], sample, degree) & 1) << i)
                 for i in range(n))
        l1 = sum((((_evaluation(forward[1 << i], sample, degree) >> 1) & 1) << i)
                 for i in range(n))
        for u, value in ((l0, 3), (l1, 1), (l0 ^ l1, 2)):
            factors.append(Term(u, u, inverse[_interpolate(sample, value, degree)]))
    if len(factors) != (9 if n == 4 else 15):
        raise ArithmeticError("unexpected bilinear factor count")
    certify_decomposition(n, factors, modulus)
    return tuple(factors)
