"""Bilinear tensor of GF(2^n) multiplication and its incidence lower bound.

**Status of this module.** The private ``yoch/qant`` circuit this research was originally aimed at is
not readable from this environment (see ``REPORT.md`` §1): access is *blocked by permissions*, which is
not evidence that the circuit is unoptimisable. Nothing here measures that circuit. What this module
establishes is a statement about the *function* it computes,

    (a, b, z) -> (a, b, z xor a*b)   in GF(2^n) modulo a pinned irreducible polynomial,

and specifically about **rank-one bilinear decompositions of its tensor in a fixed set of output
coordinates**. It is not a bound on CCX, CX or T gates. Please read the scope note at the end of this
docstring before reusing it.

## The tensor

Multiplication in GF(2^n) is bilinear, so it is a tensor ``T`` over GF(2) with ``T[i][j] = x^i * x^j``
as an n-bit vector. A bilinear algorithm writes

    T = sum_{s=1..r} u_s (x) v_s (x) w_s

with ``r`` terms; each term is one AND producing ``(u_s . a)(v_s . b)``, accumulated into the
coordinates named by ``w_s``. So ``r`` is the multiplicative complexity of that decomposition and
``sum_s popcount(w_s)`` counts (term, output-coordinate) incidences.

## The bound, and its proof

Slice ``T`` by output coordinate: ``A_k[i][j] = bit_k(T[i][j])``. For a fixed set of output
coordinates, coordinate ``k`` of ``a*b`` is the bilinear form ``B_k(a, b) = a^T A_k b``. Two facts
give the bound.

*Fact 1 (matrix rank of a nonzero bilinear form).* ``A_k`` is the matrix of ``B_k`` in the standard
basis, so ``rank(A_k)`` is the dimension of the space of ``a``-linear forms spanned by the ``b``-side.
Expressing ``B_k`` as ``sum_t u_t (x) v_t`` with ``t`` terms requires at least ``rank(A_k)`` of them,
because each term contributes a rank-one matrix ``u_t v_t^T`` and rank is subadditive.

*Fact 2 (nondegeneracy of every slice).* GF(2^n) is a field, so every nonzero ``a`` is invertible and
``b -> a*b`` is a bijection. Therefore ``a*b != 0`` whenever ``a != 0`` and ``b != 0``, which means
``B_k`` is not the zero form: some entry of ``A_k`` is 1. A nonzero matrix has rank at least 1, and
here the bound is sharper:

    rank(A_k) = n for every k.

Proof of the sharper statement. ``A_k[i][j]`` is the coefficient of ``x^k`` in ``x^i * x^j``. For
``a`` ranging over the standard basis, ``B_k(x^i, b)`` is the ``k``-th bit of ``x^i * b``. Suppose
``sum_i c_i B_k(x^i, b) = 0`` for all ``b``, i.e. the ``k``-th bit of ``(sum_i c_i x^i) * b`` vanishes
identically. By Fact 2 that forces ``sum_i c_i x^i = 0``, hence every ``c_i = 0``. The ``n`` rows of
``A_k`` are therefore linearly independent, so ``rank(A_k) = n``.

*Conclusion.* Let ``c_k`` be the number of terms ``s`` with ``k`` in the support of ``w_s``. Each such
term contributes at most one rank-one piece to coordinate ``k``, so ``c_k >= rank(A_k) = n``. Summing
over the ``n`` coordinates,

    sum_s popcount(w_s) = sum_k c_k >= sum_k rank(A_k) = n^2.

This is the only theorem in this repository's XAG work. It is established by the argument above, not
by the agreement of two programs: ``rank_gaussian`` and ``rank_incremental`` are cross-checks that a
coding mistake has not slipped into the computed tables, and they make :func:`budget` raise if they
ever disagree.

## Scope: what this is not

The bound constrains **term sets**. It does *not* bound gates. A reversible realisation may compute
intermediate functions that are not rank-one bilinear terms, may change linear bases between products,
and may reuse or uncompute wires; none of that is counted by ``sum_s popcount(w_s)``. In particular
``n^2`` is **not** a lower bound on CCX, on CX, on T-count, or on the size of any circuit. The test
``test_cx_copies_junk_so_the_incidence_floor_is_not_a_cx_bound`` exhibits a concrete three-gate
program that moves two incidences onto a second wire, which is the cheapest reason the inequality
cannot be promoted to a gate bound.
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
"""Pinned irreducible polynomials whose fields the tables are computed over: x^2+x+1, x^3+x+1,
x^4+x+1, x^5+x^2+1, x^6+x+1, x^7+x+1, x^8+x^4+x^3+x+1, and x^12+x^6+x^4+x+1.

The theorem above holds for *any* field and hence any irreducible modulus; these are simply the ones
the tests pin. ``is_irreducible`` verifies them, because a reducible modulus would break Fact 2.
"""


def gf_mul(n: int, left: int, right: int) -> int:
    """Product in GF(2^n) by shift-and-reduce.

    Both operands must be elements of the field, that is ``0 <= value < 2^n``. Out-of-range inputs
    raise rather than being silently reduced: an element larger than ``2^n - 1`` is not a field
    element, and truncating it would return a product of something other than what the caller asked
    for. (A polynomial such as the modulus itself can legitimately be multiplied *by* the algorithm,
    but that is not an element of GF(2^n); use a dedicated polynomial routine for it.)
    """
    limit = 1 << n
    if not (0 <= left < limit and 0 <= right < limit):
        raise ValueError(
            f"operands of GF(2^{n}) multiplication must be in [0, {limit - 1}], "
            f"got left={left}, right={right}"
        )
    modulus = MODULI[n]
    out = 0
    while right:
        if right & 1:
            out ^= left
        right >>= 1
        left <<= 1
        if left >> n & 1:
            left ^= modulus
    return out


def _degree(value: int) -> int:
    return value.bit_length() - 1


def _reduce_by(value: int, modulus: int) -> int:
    top = _degree(modulus)
    while _degree(value) >= top:
        value ^= modulus << (_degree(value) - top)
    return value


def is_irreducible(n: int) -> bool:
    """Trial division by every polynomial of degree up to ``deg/2``.

    A reducible modulus would make ``gf_mul`` a ring with zero divisors, so Fact 2 would fail and the
    bound would not hold. The tests assert this for every pinned field.
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
    """Rank by insertion into a triangular basis; independent of the elimination above.

    Both routines compute the same quantity by different means. Their agreement guards the *tables*;
    the theorem itself rests on the argument in the module docstring.
    """
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
    """Verified structural numbers for one field.

    ``incidence_floor`` is ``n^2``, the minimum of ``sum_s popcount(w_s)`` over rank-one bilinear
    decompositions in the chosen output coordinates. ``schoolbook_incidences`` is what the naive
    one-wire-per-tensor-entry decomposition spends, so ``schoolbook_slack`` is how far that particular
    decomposition sits above the floor. None of these numbers bounds any gate count.
    """

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
        schoolbook_incidences=sum(value.bit_count() for row in table for value in row),
    )


def nonzero_multiplication_is_a_bijection(n: int) -> bool:
    """Check Fact 2 directly for one field: ``b -> a*b`` is injective for every nonzero ``a``.

    The general proof is that GF(2^n) is a field, so every nonzero element is invertible. This
    function is a concrete check of that premise on the pinned modulus, used by the tests; it is not
    the proof of the theorem.
    """
    limit = 1 << n
    for a in range(1, limit):
        seen = {gf_mul(n, a, b) for b in range(limit)}
        if len(seen) != limit:
            return False
    return True


if __name__ == "__main__":  # pragma: no cover - reporting helper
    for field in sorted(MODULI):
        info = budget(field)
        print(
            f"GF(2^{field:2d})  ranks={info.coordinate_ranks}  full_rank={info.full_rank}  "
            f"incidence_floor={info.incidence_floor}  schoolbook={info.schoolbook_terms} terms / "
            f"{info.schoolbook_incidences} incidences (slack {info.schoolbook_slack})  "
            f"irreducible={is_irreducible(field)}"
        )
