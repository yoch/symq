"""GF(2^n) field arithmetic and the exact bilinear-tensor budget of multiplication.

**Scope.** The private ``yoch/qant`` GF(2^12) block is not readable from this environment: the
repository, the pinned commit ``071f8c80`` and every referenced path answer HTTP 404, and no local
copy exists. Nothing in this module measures that circuit or claims one of its numbers. What it
computes are properties of the *function* the block implements,

    (a, b, z) -> (a, b, z xor a*b)   in GF(2^12) modulo 0x1053,

because those properties constrain every reversible implementation, including qant's.

## The tensor

Multiplication in GF(2^n) is bilinear, so it is a tensor ``T`` with ``T[i][j] = x^i * x^j`` as an
n-bit vector. A bilinear algorithm writes

    T = sum_{s=1..r} u_s (x) v_s (x) w_s

with ``r`` terms. Each term is one AND: compute ``p_s = (u_s . a)(v_s . b)``, then add ``p_s`` to
every accumulator bit in the support of ``w_s``. So ``r`` is the multiplicative complexity and
``sum_s |w_s|`` counts (term, accumulator-bit) incidences.

## The rank theorem

Coordinate ``k`` of the result is the bilinear form ``a^T A_k b`` with ``A_k[i][j] = bit_k(T[i][j])``.
Expressing it as a sum of rank-one terms needs at least ``rank(A_k)`` of them, and each term
contributes at most one incidence to coordinate ``k``. Hence

    sum_s |w_s| = sum_k #{s : k in w_s} >= sum_k rank(A_k).

This module verifies ``rank(A_k) = n`` for every ``k``, so ``sum_s |w_s| >= n^2``: every bilinear
decomposition of GF(2^n) multiplication has at least ``n^2`` (term, accumulator-bit) incidences.

That is a statement about *terms*, not about gates. It does **not** bound CX, and it must not be used
as if it did: a single CX can transfer every incidence sitting on its control, which
``tests/test_xag_decompositions.py`` exhibits explicitly. Turning incidences into a gate bound needs
the whole architecture, including how the accumulator's initial junk is handled.
"""

from __future__ import annotations

from dataclasses import dataclass

MODULI = {
    2: 0b111,
    3: 0b1011,
    4: 0b10011,
    5: 0b100101,
    6: 0b1000011,
    7: 0b10000011,
    8: 0b100011011,
    12: 0x1053,
}
"""Pinned irreducible polynomials: x^2+x+1, x^3+x+1, x^4+x+1, x^5+x^2+1, x^6+x+1, x^7+x+1,
x^8+x^4+x^3+x+1, and the qant GF(2^12) modulus x^12+x^6+x^4+x+1."""


def gf_mul(n: int, left: int, right: int) -> int:
    """Product in GF(2^n) by shift-and-reduce."""
    modulus = MODULI[n]
    out = 0
    while right:
        if right & 1:
            out ^= left
        right >>= 1
        left <<= 1
        if left >> n & 1:
            left ^= modulus
    return out & ((1 << n) - 1)


def _degree(value: int) -> int:
    return value.bit_length() - 1


def _reduce_by(value: int, modulus: int) -> int:
    top = _degree(modulus)
    while _degree(value) >= top:
        value ^= modulus << (_degree(value) - top)
    return value


def is_irreducible(n: int) -> bool:
    """Trial division by every polynomial of degree up to ``deg/2``.

    A reducible modulus would make ``gf_mul`` a ring with zero divisors, which would invalidate the
    rank argument: slice ranks could drop below ``n``. The tests assert this for every pinned field.
    """
    for divisor in range(2, 1 << (n // 2 + 1)):
        if _degree(divisor) < 1:
            continue
        if _reduce_by(MODULI[n], divisor) == 0:
            return False
    return True


def tensor(n: int) -> list[list[int]]:
    """``T[i][j] = x^i * x^j`` as an n-bit vector."""
    return [[gf_mul(n, 1 << i, 1 << j) for j in range(n)] for i in range(n)]


def coordinate_slices(n: int) -> list[list[int]]:
    """``A_k`` rows as bitmasks: row ``i`` has bit ``j`` set iff bit ``k`` of ``T[i][j]`` is 1."""
    table = tensor(n)
    return [
        [sum(((table[i][j] >> k) & 1) << j for j in range(n)) for i in range(n)] for k in range(n)
    ]


def rank_gaussian(rows: list[int], width: int) -> int:
    """Rank over GF(2) by Gauss-Jordan elimination."""
    rows = list(rows)
    rank = 0
    for column in range(width):
        pivot = next((i for i in range(rank, len(rows)) if (rows[i] >> column) & 1), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for i in range(len(rows)):
            if i != rank and (rows[i] >> column) & 1:
                rows[i] ^= rows[rank]
        rank += 1
    return rank


def rank_incremental(rows: list[int]) -> int:
    """Rank by insertion into a triangular basis; independent of the elimination above."""
    basis: dict[int, int] = {}
    for value in rows:
        current = value
        while current:
            top = current.bit_length() - 1
            if top in basis:
                current ^= basis[top]
            else:
                basis[top] = current
                break
    return len(basis)


@dataclass(frozen=True)
class Budget:
    """Verified structural numbers for one field."""

    n: int
    coordinate_ranks: tuple[int, ...]
    incidence_floor: int
    schoolbook_terms: int
    schoolbook_incidences: int

    @property
    def full_rank(self) -> bool:
        return all(rank == self.n for rank in self.coordinate_ranks)

    @property
    def schoolbook_slack(self) -> int:
        """Incidences the schoolbook decomposition spends above the floor."""
        return self.schoolbook_incidences - self.incidence_floor


def budget(n: int) -> Budget:
    """Coordinate ranks plus the incidence floor, cross-checked by two rank algorithms."""
    slices = coordinate_slices(n)
    by_gaussian = [rank_gaussian(rows, n) for rows in slices]
    by_incremental = [rank_incremental(rows) for rows in slices]
    if by_gaussian != by_incremental:
        raise AssertionError(
            f"rank algorithms disagree for GF(2^{n}): {by_gaussian} vs {by_incremental}"
        )
    table = tensor(n)
    return Budget(
        n=n,
        coordinate_ranks=tuple(by_gaussian),
        incidence_floor=sum(by_gaussian),
        schoolbook_terms=n * n,
        schoolbook_incidences=sum((value).bit_count() for row in table for value in row),
    )


if __name__ == "__main__":  # pragma: no cover - reporting helper
    for field in sorted(MODULI):
        info = budget(field)
        print(
            f"GF(2^{field:2d})  ranks={info.coordinate_ranks}  full_rank={info.full_rank}  "
            f"incidence_floor={info.incidence_floor}  schoolbook={info.schoolbook_terms} terms / "
            f"{info.schoolbook_incidences} incidences (slack {info.schoolbook_slack})  "
            f"irreducible={is_irreducible(field)}"
        )
