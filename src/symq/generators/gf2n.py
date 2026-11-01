"""Reversible GF(2^n) multipliers built from exact bilinear decompositions.

A multiplier circuit on ``3n`` wires computes ``(a, b, z) -> (a, b, z XOR a*b)`` in GF(2^n) modulo a
pinned irreducible polynomial (``MODULI``), with ``a`` on wires ``0..n-1``, ``b`` on ``n..2n-1``
and ``z`` on ``2n..3n-1`` (bit ``i`` of each register is the coefficient of ``x^i``). Three
decompositions of the multiplication tensor are available:

* ``schoolbook``: one Toffoli per incidence of the tensor (``n^2`` products before reduction);
* ``karatsuba``: three half-size products instead of four, reduction folded into the targets;
* ``rank_floor``: one product per row of a reduced basis of every coordinate slice.

Every term ``(u . a)(v . b)`` is emitted as fold / one Toffoli per target bit / unfold, without
ancilla. ``multiplier_expected_output`` is the integer reference used to check a circuit
exhaustively. Research analyses of these decompositions live in the separate labs package.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..circuit import Circuit
from ..errors import InternalInconsistency

__all__ = [
    "DECOMPOSITIONS",
    "MODULI",
    "Emitted",
    "Term",
    "coordinate_slices",
    "emit",
    "expand",
    "expected_tensor",
    "gf_mul",
    "is_irreducible",
    "karatsuba",
    "multiplier",
    "multiplier_expected_output",
    "rank_floor",
    "schoolbook",
    "tensor",
]

MODULI = {
    2: 0b111,
    3: 0b1011,
    4: 0b10011,
    5: 0b100101,
    6: 0b1000011,
    7: 0b10000011,
    8: 0b100011011,
    12: 0x1053,
    16: 0x1002B,
    24: 0x100001B,
}
"""Pinned irreducible polynomials whose fields the tables are computed over: x^2+x+1, x^3+x+1,
x^4+x+1, x^5+x^2+1, x^6+x+1, x^7+x+1, x^8+x^4+x^3+x+1, x^12+x^6+x^4+x+1,
x^16+x^5+x^3+x+1 and x^24+x^4+x^3+x+1.

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


@dataclass(frozen=True)
class Term:
    """``(u . a)(v . b)`` added into the accumulator bits named by ``into``."""

    left: int
    right: int
    into: int

    @property
    def left_weight(self) -> int:
        return self.left.bit_count()

    @property
    def right_weight(self) -> int:
        return self.right.bit_count()

    @property
    def fanout_weight(self) -> int:
        return self.into.bit_count()


def schoolbook(n: int) -> list[Term]:
    """One term per tensor entry: single-wire controls, full product mask as accumulator target."""
    return [Term(1 << i, 1 << j, gf_mul(n, 1 << i, 1 << j)) for i in range(n) for j in range(n)]


def _reduce_exponent(mask: int, n: int) -> int:
    """Reduce a polynomial of degree ``< 2*size`` modulo the pinned degree-``n`` polynomial.

    Applied top-down, one monomial at a time. A single shift per bit is *not* sufficient for a padded
    Karatsuba width, where exponents exceed ``2n`` and a second reduction pass is required; truncating
    instead silently drops high terms. That bug made GF(2^5) disagree with its truth table while
    GF(2^4) still passed.
    """
    tail = MODULI[n] ^ (1 << n)
    for bit in range(mask.bit_length() - 1, n - 1, -1):
        if mask >> bit & 1:
            mask ^= 1 << bit
            mask ^= tail << (bit - n)
    return mask


def _karatsuba(left: list[int], right: list[int]) -> list[tuple[int, int, int]]:
    """Karatsuba over coefficient masks; a zero coefficient is the mask 0."""
    size = len(left)
    if size == 1:
        if not left[0] or not right[0]:
            return []
        return [(left[0], right[0], 1)]
    half = size // 2
    lo_l, hi_l = left[:half], left[half:]
    lo_r, hi_r = right[:half], right[half:]
    low = _karatsuba(lo_l, lo_r)
    high = _karatsuba(hi_l, hi_r)
    middle = _karatsuba([a ^ b for a, b in zip(lo_l, hi_l)], [a ^ b for a, b in zip(lo_r, hi_r)])
    out = list(low)
    out.extend((a, b, m << half) for a, b, m in middle)
    out.extend((a, b, m << half) for a, b, m in low)
    out.extend((a, b, m << (2 * half)) for a, b, m in high)
    out.extend((a, b, m << half) for a, b, m in high)
    return out


def karatsuba(n: int) -> list[Term]:
    """Multiplicity-free Karatsuba terms with reduction folded into the accumulator masks.

    ``A1 B0 + A0 B1 = (A0 + A1)(B0 + B1) + A0 B0 + A1 B1`` in characteristic two, so three half-size
    products replace four. A width that is not a power of two is padded with zero coefficients, and
    every term touching one is dropped: its product would be identically zero.
    """
    size = 1
    while size < n:
        size <<= 1
    left = [1 << i for i in range(n)] + [0] * (size - n)
    right = [1 << i for i in range(n)] + [0] * (size - n)
    merged: dict[tuple[int, int], int] = {}
    for lmask, rmask, into in _karatsuba(left, right):
        if not lmask or not rmask:
            continue
        reduced = _reduce_exponent(into, n)
        if not reduced:
            continue
        key = (lmask, rmask)
        merged[key] = merged.get(key, 0) ^ reduced
    return sorted(
        (Term(lmask, rmask, into) for (lmask, rmask), into in merged.items() if into),
        key=lambda term: (term.into, term.left, term.right),
    )


def _reduced_basis(rows: list[int]) -> list[tuple[int, int]]:
    """Row-reduced echelon basis of the span of ``rows``, as ``(vector, pivot)`` pairs."""
    basis: list[tuple[int, int]] = []
    for value in rows:
        vec = value
        for basis_vec, pivot in basis:
            if vec >> pivot & 1:
                vec ^= basis_vec
        if not vec:
            continue
        pivot = vec.bit_length() - 1
        basis = [
            (basis_vec ^ vec, other) if basis_vec >> pivot & 1 else (basis_vec, other)
            for basis_vec, other in basis
        ]
        basis.append((vec, pivot))
        basis.sort(key=lambda entry: entry[1], reverse=True)
    return basis


def _basis_coordinates(rows: list[int], basis: list[tuple[int, int]]) -> list[int]:
    """Express each row in ``basis``; one bitmask of basis indices per row."""
    out = []
    for value in rows:
        vec, mask = value, 0
        for index, (basis_vec, pivot) in enumerate(basis):
            if vec >> pivot & 1:
                vec ^= basis_vec
                mask ^= 1 << index
        if vec:
            raise ValueError("row is outside the supplied basis")
        out.append(mask)
    return out


def rank_floor(n: int) -> list[Term]:
    """One term per coordinate-slice basis vector: minimal incidences, wide forms.

    Coordinate ``k`` of ``a*b`` is ``sum_i a_i (row_i . b)`` with ``row_i`` row ``i`` of slice
    ``A_k``. Writing ``row_i = XOR_{t in c_i} v_t`` for a basis ``{v_t}`` gives
    ``sum_t (sum_{i : t in c_i} a_i)(v_t . b)``: one term per basis vector, each landing on the
    single accumulator bit ``k``.
    """
    terms: list[Term] = []
    for k, rows in enumerate(coordinate_slices(n)):
        basis = _reduced_basis(rows)
        coords = _basis_coordinates(rows, basis)
        for index, (basis_vec, _pivot) in enumerate(basis):
            comb = 0
            for row_index, mask in enumerate(coords):
                if mask >> index & 1:
                    comb |= 1 << row_index
            if not comb:
                raise InternalInconsistency("basis vector with no supporting row")
            terms.append(Term(comb, basis_vec, 1 << k))
    return terms


def expand(n: int, terms: list[Term]) -> list[list[int]]:
    """Recompute the tensor a term set denotes, for an independent algebraic check."""
    table = [[0] * n for _ in range(n)]
    for term in terms:
        for i in range(n):
            if not term.left >> i & 1:
                continue
            for j in range(n):
                if not term.right >> j & 1:
                    continue
                for k in range(n):
                    if term.into >> k & 1:
                        table[i][j] ^= 1 << k
    return table


def _pivot(mask: int) -> int:
    return (mask & -mask).bit_length() - 1


@dataclass
class Emitted:
    """A circuit plus the accounting of where its gates went."""

    circuit: Circuit
    ccx: int
    cx: int
    fold_cx: int
    n: int
    terms: int
    incidences: int

    @property
    def width(self) -> int:
        return self.circuit.width

    @property
    def depth(self) -> int:
        """Gate depth, charging every gate to all of its wires."""
        per_wire = [0] * self.circuit.width
        for gate in self.circuit.gates:
            level = 1 + max(per_wire[q] for q in gate.qubits)
            for q in gate.qubits:
                per_wire[q] = level
        return max(per_wire, default=0)


def emit(n: int, terms: list[Term], *, share: bool = False) -> Emitted:
    """Emit fold / CCX-per-incidence / unfold for each term on ``3n`` wires, no ancilla.

    Every term pays its own fold and unfold, so each term starts from the original basis. This is a
    per-term schedule, **not** a stateful one: no linear basis survives from one product to the next.

    ``share=True`` groups terms whose ``(left, right)`` pair is exactly identical, folding that pair
    once. That tests one narrow hypothesis -- *repeated identical forms* -- and nothing else: it does
    not test overlapping forms, partial sharing, or basis-state reuse between distinct products. On
    the term sets here every ``(left, right)`` pair has multiplicity one, so the grouping changes
    nothing; that negative result is scoped to these term sets.
    """
    if n not in MODULI:
        raise ValueError(f"no pinned modulus for GF(2^{n})")
    a_base, b_base, z_base = 0, n, 2 * n
    gates: list[tuple[str, tuple[int, ...]]] = []
    fold_cx = 0

    if share:
        grouped: dict[tuple[int, int], list[Term]] = {}
        for term in terms:
            grouped.setdefault((term.left, term.right), []).append(term)
        groups = list(grouped.values())
    else:
        groups = [[term] for term in terms]

    for group in groups:
        head = group[0]
        left_pivot = _pivot(head.left)
        right_pivot = _pivot(head.right)
        left_extra = [i for i in range(n) if head.left >> i & 1 and i != left_pivot]
        right_extra = [j for j in range(n) if head.right >> j & 1 and j != right_pivot]

        for off in left_extra:
            gates.append(("cx", (a_base + off, a_base + left_pivot)))
        for off in right_extra:
            gates.append(("cx", (b_base + off, b_base + right_pivot)))
        fold_cx += len(left_extra) + len(right_extra)

        for term in group:
            for bit in range(n):
                if term.into >> bit & 1:
                    gates.append(("ccx", (a_base + left_pivot, b_base + right_pivot, z_base + bit)))

        for off in reversed(right_extra):
            gates.append(("cx", (b_base + off, b_base + right_pivot)))
        for off in reversed(left_extra):
            gates.append(("cx", (a_base + off, a_base + left_pivot)))
        fold_cx += len(left_extra) + len(right_extra)

    circuit = Circuit(3 * n)
    for name, qubits in gates:
        circuit.append(name, *qubits)
    ccx = sum(1 for name, _ in gates if name == "ccx")
    return Emitted(
        circuit,
        ccx,
        len(gates) - ccx,
        fold_cx,
        n,
        len(terms),
        sum(term.fanout_weight for term in terms),
    )


def expected_tensor(n: int) -> list[list[int]]:
    """The multiplication tensor ``T[i][j] = x^i * x^j`` (alias of ``tensor``)."""
    return tensor(n)


DECOMPOSITIONS = {"schoolbook": schoolbook, "karatsuba": karatsuba, "rank_floor": rank_floor}


def multiplier(n: int, method: str = "karatsuba") -> Circuit:
    """A reversible GF(2^n) multiplier ``(a, b, z) -> (a, b, z XOR a*b)`` on ``3n`` wires."""
    try:
        decomposition = DECOMPOSITIONS[method]
    except KeyError:
        raise ValueError(f"unknown decomposition {method!r}; choose from {sorted(DECOMPOSITIONS)}") \
            from None
    return emit(n, decomposition(n)).circuit


def multiplier_expected_output(n: int, x: int) -> int:
    """The image of the assignment ``x`` (LSB-first over ``3n`` wires) by plain field arithmetic."""
    if n not in MODULI:
        raise ValueError(f"no pinned modulus for GF(2^{n})")
    if not 0 <= x < 1 << (3 * n):
        raise ValueError("assignment outside 3n wires")
    mask = (1 << n) - 1
    a, b, z = x & mask, (x >> n) & mask, (x >> 2 * n) & mask
    return a | (b << n) | ((z ^ gf_mul(n, a, b)) << (2 * n))
