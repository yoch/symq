"""Independent GF(2^n) arithmetic for checking multiplier circuits.

Written from the definition and without ``symq.generators.gf2n``: elements are bit lists of
polynomial coefficients, the product is the full convolution over GF(2), and the reduction
replaces every power ``x^k`` with ``k >= n`` by ``x^k - x^n * modulus``, top degree first.
"""
from __future__ import annotations

__all__ = ["multiplier_output", "multiply"]


def _bits(value: int, count: int) -> list[int]:
    return [(value >> i) & 1 for i in range(count)]


def multiply(n: int, a: int, b: int, modulus: int) -> int:
    """``a * b`` in ``GF(2)[x] / modulus``, with ``modulus`` of degree ``n``."""
    left, right, poly = _bits(a, n), _bits(b, n), _bits(modulus, n + 1)
    if poly[n] != 1 or not (0 <= a < 1 << n and 0 <= b < 1 << n):
        raise ValueError("operands must be field elements and the modulus of degree n")
    product = [0] * (2 * n - 1)
    for i, x in enumerate(left):
        for j, y in enumerate(right):
            product[i + j] ^= x & y
    for degree in range(2 * n - 2, n - 1, -1):
        if product[degree]:
            for k in range(n + 1):
                product[degree - n + k] ^= poly[k]
    return sum(bit << i for i, bit in enumerate(product[:n]))


def multiplier_output(n: int, state: int, modulus: int) -> int:
    """The state of a dirty-register multiplier ``(a, b, t) -> (a, b, t XOR a*b)``."""
    mask = (1 << n) - 1
    a, b, t = state & mask, (state >> n) & mask, (state >> 2 * n) & mask
    return a | (b << n) | ((t ^ multiply(n, a, b, modulus)) << 2 * n)
