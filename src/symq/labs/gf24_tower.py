"""Experimental 99-term bilinear multiplication construction for GF(2^24).

A nested tower uses GF(2^24) as degree 6 over GF(16), maps an explicit
polynomial basis, evaluates degree-5 polynomials at 10 distinct GF(16)
points and infinity, and composes each resulting GF(16) multiplication
with its verified rank-9 binary factorization. This constructs 11*9=99
rank-one binary terms, not a proven minimum rank.

All arithmetic, isomorphisms, interpolation and factor-mask outputs are
recomputed exactly using only stdlib integer operations. The final factor
tensor is verified against SymQ's pinned GF24 modulus x^24+x^4+x^3+x+1.
No circuit with measurements, phases or dirty uncomputed ancillas is claimed.

Mathematical roots: finite-field evaluation/interpolation, and GF16's
9-term tower factorization discussed by Polytof (ZIB-IOL/polytof, MIT,
commit 0dcac107d15adc34dc646242d222f21ae7d32699). This module is
an independently implemented experimental construction, not a copied
third-party source or a quantum competition score claim.
"""
from __future__ import annotations

from functools import lru_cache

from symq.generators.bilinear_factors import tower_factors
from symq.generators.bilinear_optimization import certify_decomposition
from symq.generators.gf2n import Term

GF24_MODULUS = 0x100001B
GF16_MODULUS = 0x13
BASE_BITS = 4
OUTER_DEGREE = 6
FIELD_SIZE = 1 << BASE_BITS
PINNED_SUBFIELD_ROOT = 0xB781C5
PINNED_OUTER_BETA = 0x10


def _mul(a: int, b: int, n: int, modulus: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & (1 << n):
            a ^= modulus
    return result


def _power(a: int, exponent: int, n: int, modulus: int) -> int:
    result = 1
    while exponent:
        if exponent & 1:
            result = _mul(result, a, n, modulus)
        a = _mul(a, a, n, modulus)
        exponent >>= 1
    return result


def _xor(values) -> int:
    result = 0
    for value in values:
        result ^= value
    return result


def _basis(columns: list[int]) -> dict[int, tuple[int, int]]:
    pivots: dict[int, tuple[int, int]] = {}
    for index, column in enumerate(columns):
        coordinates = 1 << index
        while column:
            pivot = column.bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (column, coordinates)
                break
            column ^= pivots[pivot][0]
            coordinates ^= pivots[pivot][1]
    return pivots


def _decode(pivots: dict[int, tuple[int, int]], value: int) -> int:
    coordinates = 0
    while value:
        pivot = value.bit_length() - 1
        if pivot not in pivots:
            raise ArithmeticError("field element lies outside the declared tower basis")
        value ^= pivots[pivot][0]
        coordinates ^= pivots[pivot][1]
    return coordinates


def _model(root: int, beta: int):
    """Return exact GF16 coordinates and degree-six reduction for a valid basis."""
    if (type(root) is not int or not 0 < root < (1 << 24)
            or type(beta) is not int or not 0 < beta < (1 << 24)):
        raise ValueError("GF24 basis root and generator must be nonzero 24-bit integers")

    def mult24(a: int, b: int) -> int:
        return _mul(a, b, 24, GF24_MODULUS)
    if (_power(root, 4, 24, GF24_MODULUS) ^ root ^ 1) != 0:
        raise ValueError("declared GF16 basis root does not satisfy x^4+x+1")
    alpha = root
    powers = [_power(alpha, j, 24, GF24_MODULUS) for j in range(4)]
    embedding = tuple(_xor(powers[j] for j in range(4) if v >> j & 1)
                      for v in range(FIELD_SIZE))
    if len(set(embedding)) != FIELD_SIZE:
        raise ArithmeticError("GF16 polynomial subfield embedding is not injective")
    beta_powers = [_power(beta, j, 24, GF24_MODULUS)
                   for j in range(OUTER_DEGREE + 1)]
    columns = [mult24(embedding[1 << i], beta_powers[k])
               for k in range(OUTER_DEGREE) for i in range(BASE_BITS)]
    pivots = _basis(columns)
    if len(pivots) != 24:
        raise ArithmeticError("original GF24 generator has insufficient degree over GF16")
    def decode(value: int) -> int:
        return _decode(pivots, value)
    def encode(value: int) -> int:
        return _xor(columns[i] for i in range(24) if value >> i & 1)
    reduction = tuple((decode(beta_powers[OUTER_DEGREE]) >> (BASE_BITS * i)) & 15
                      for i in range(OUTER_DEGREE))
    for i in range(24):
        if encode(decode(1 << i)) != 1 << i:
            raise ArithmeticError("the GF24 tower basis inverse is not exact")
    return decode, encode, reduction


def _matrix_inverse(matrix: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    n = len(matrix)
    rows = [list(values) + [int(i == j) for j in range(n)]
            for i, values in enumerate(matrix)]
    for column in range(n):
        pivot = next((row for row in range(column, n) if rows[row][column]), None)
        if pivot is None:
            raise ArithmeticError("GF16 Vandermonde matrix is singular")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        inverse = _power(rows[column][column], FIELD_SIZE - 2, BASE_BITS, GF16_MODULUS)
        rows[column] = [_mul(value, inverse, BASE_BITS, GF16_MODULUS)
                        for value in rows[column]]
        for row in range(n):
            if row != column and rows[row][column]:
                scale = rows[row][column]
                rows[row] = [
                    rows[row][i] ^ _mul(scale, rows[column][i], BASE_BITS, GF16_MODULUS)
                    for i in range(2 * n)
                ]
    return tuple(tuple(row[n:]) for row in rows)


@lru_cache(maxsize=128)
def gf24_tower_factors(
    *, root: int = PINNED_SUBFIELD_ROOT, beta: int = PINNED_OUTER_BETA
) -> tuple[Term, ...]:
    """Exact 99-product upper-bound construction in SymQ's GF24 basis.

    Optional root/beta must define a valid GF16 embedding and degree-six
    GF24 basis. The default root=0xB781C5 and beta=0x10 minimize emitted CX
    among a specified grid of 4 GF16 conjugates x 24 monomial beta values,
    not among all possible bases or gate synthesis algorithms.
    Never uses private workloads, approximations or a floating-point oracle.
    The result is immutable and cached; its source proof is a full GF(2)
    multiplication-tensor reconstruction, not an independently verified SAT
    certificate or a contextual replacement authorization.
    """
    decode, encode, reduction = _model(root, beta)
    def mul16(a: int, b: int) -> int:
        return _mul(a, b, BASE_BITS, GF16_MODULUS)
    count = 2 * OUTER_DEGREE - 2
    points = tuple(range(count))
    if FIELD_SIZE < count:
        raise ArithmeticError("not enough distinct interpolation points")
    vandermonde = tuple(tuple(_power(point, j, BASE_BITS, GF16_MODULUS)
                              for j in range(count)) for point in points)
    inverse = _matrix_inverse(vandermonde)

    def evaluate(packed: int, sample: int) -> int:
        coeffs = [(packed >> (BASE_BITS * i)) & 15 for i in range(OUTER_DEGREE)]
        if sample == count:
            return coeffs[-1]  # infinity
        point = points[sample]
        return _xor(mul16(coeffs[j], _power(point, j, BASE_BITS, GF16_MODULUS))
                    for j in range(OUTER_DEGREE))

    def reconstruct(sample: int, value: int) -> int:
        if sample < count:
            coefficients = [mul16(inverse[j][sample], value) for j in range(count)]
            coefficients.append(0)
        else:
            coefficients = [
                _xor(mul16(inverse[j][i], _power(points[i], count,
                      BASE_BITS, GF16_MODULUS)) for i in range(count))
                for j in range(count)
            ] + [1]
            coefficients = [mul16(x, value) for x in coefficients]
        for k in range(2 * OUTER_DEGREE - 2, OUTER_DEGREE - 1, -1):
            q = coefficients[k]
            for j in range(OUTER_DEGREE):
                coefficients[k - OUTER_DEGREE + j] ^= mul16(q, reduction[j])
        return encode(sum(coefficients[i] << (BASE_BITS * i)
                          for i in range(OUTER_DEGREE)))

    basis_inputs = tuple(decode(1 << i) for i in range(24))
    inner = tower_factors(BASE_BITS, GF16_MODULUS)
    terms: list[Term] = []
    for sample in range(2 * OUTER_DEGREE - 1):
        evaluated = tuple(evaluate(b, sample) for b in basis_inputs)
        for term in inner:
            left = _xor(1 << i for i, x in enumerate(evaluated)
                        if (x & term.left).bit_count() & 1)
            right = _xor(1 << i for i, x in enumerate(evaluated)
                         if (x & term.right).bit_count() & 1)
            output = reconstruct(sample, term.into)
            if not left or not right or not output:
                raise ArithmeticError("zero rank-one factor in a required tower evaluation")
            terms.append(Term(left, right, output))
    if len(terms) != 99:
        raise ArithmeticError("GF24 tower construction has the wrong number of products")
    certify_decomposition(24, terms, GF24_MODULUS)
    return tuple(terms)
