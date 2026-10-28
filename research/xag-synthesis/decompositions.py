"""Three exact bilinear decompositions of GF(2^n) multiplication, emitted and measured.

**Scope.** The private ``yoch/qant`` GF(2^12) block is unreadable from this environment (HTTP 404 on
the repository, the pinned commit and every referenced path; no local copy exists). Nothing here
reproduces that circuit or claims one of its numbers. What it does is emit three decompositions of the
*same function*, verify each one exactly, and compare their gate costs -- which is what the mission
asks for, done on data I can actually authenticate.

## The decompositions

A bilinear algorithm is a set of terms ``(u, v, w)``: add ``(u . a)(v . b)`` to the accumulator bits
named by ``w``. Writing ``p = popcount(u)``, ``q = popcount(v)``, ``s = popcount(w)``, a term costs

    fold and unfold  2(p-1) + 2(q-1) CX     one CCX per accumulator bit  s CCX

* **schoolbook** -- one term per tensor entry, ``p = q = 1``. No fold work, ``n^2`` CCX, ``sum s``
  spread over the accumulator.
* **karatsuba** -- multiplicity-free polynomial Karatsuba with the field reduction applied to the
  result masks. Fewer terms, wide forms, so both CCX and fold cost appear.
* **rank floor** -- one term per basis vector of each coordinate slice's row space, ``s = 1``.
  Minimal incidences (``n^2``), but both forms are wide.

Schoolbook and rank floor are the two extremes of the same trade-off; Karatsuba sits between them.

## The dirty accumulator

``z`` enters dirty and ``a``, ``b`` must be restored. That forbids the tempting optimisation of
writing a product into one accumulator bit and copying it to the others with CX: a copy propagates
the bit's pre-existing value into every new bit. ``fanout_shortcut`` is that invalid circuit, kept
because the tests use it to show the exhaustive check rejects a circuit a careless optimiser would
accept. A legal design must either pay one CCX per accumulator bit, or absorb the spread into a
tracked linear basis of ``z`` that is undone at the end -- which is the architecture the mission
describes.
"""

from __future__ import annotations

from dataclasses import dataclass

from tensor_budget import MODULI, coordinate_slices, gf_mul

from symq.circuit import Circuit


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
                raise AssertionError("basis vector with no supporting row")
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


def expected(n: int) -> list[list[int]]:
    return [[gf_mul(n, 1 << i, 1 << j) for j in range(n)] for i in range(n)]


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

    ``share=True`` groups terms by their ``(u, v)`` pair so a repeated form is folded once. It is kept
    because the mission asks whether reusing live forms saves CX; the measurement says it does not
    fire on these term sets, since every form has multiplicity one.
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


def exhaustive_failures(n: int, emitted: Emitted) -> int:
    """Run every ``(a, b, z)``; returns the number of inputs violating the contract."""
    if emitted.width > 18:
        raise ValueError("exhaustive check limited to 18 wires")
    mask = (1 << n) - 1
    failures = 0
    for assignment in range(1 << emitted.width):
        result = emitted.circuit.run(assignment)
        a = assignment & mask
        b = (assignment >> n) & mask
        z = (assignment >> (2 * n)) & mask
        if (
            result & mask != a
            or (result >> n) & mask != b
            or (result >> (2 * n)) & mask != z ^ gf_mul(n, a, b)
        ):
            failures += 1
    return failures


def fanout_shortcut(n: int, terms: list[Term]) -> Circuit:
    """The *invalid* shortcut: one CCX per term, then CX copies to the remaining accumulator bits.

    Sound only when every accumulator bit starts at zero, because a copy propagates the source bit's
    pre-existing value into its neighbours. Kept as the counterexample the tests use to show the
    exhaustive check rejects a plausible-looking optimisation.
    """
    a_base, b_base, z_base = 0, n, 2 * n
    gates: list[tuple[str, tuple[int, ...]]] = []
    for term in terms:
        left_pivot = _pivot(term.left)
        right_pivot = _pivot(term.right)
        left_extra = [i for i in range(n) if term.left >> i & 1 and i != left_pivot]
        right_extra = [j for j in range(n) if term.right >> j & 1 and j != right_pivot]
        for off in left_extra:
            gates.append(("cx", (a_base + off, a_base + left_pivot)))
        for off in right_extra:
            gates.append(("cx", (b_base + off, b_base + right_pivot)))
        bits = [k for k in range(n) if term.into >> k & 1]
        if bits:
            gates.append(("ccx", (a_base + left_pivot, b_base + right_pivot, z_base + bits[0])))
            for bit in bits[1:]:
                gates.append(("cx", (z_base + bits[0], z_base + bit)))
        for off in reversed(right_extra):
            gates.append(("cx", (b_base + off, b_base + right_pivot)))
        for off in reversed(left_extra):
            gates.append(("cx", (a_base + off, a_base + left_pivot)))
    circuit = Circuit(3 * n)
    for name, qubits in gates:
        circuit.append(name, *qubits)
    return circuit


def greedy_cost(terms: list[Term]) -> int:
    """The mission's per-product cost summed: ``2(w(u)-1) + 2(w(v)-1) + (w(into)-1)``."""
    return sum(
        2 * (term.left_weight - 1) + 2 * (term.right_weight - 1) + (term.fanout_weight - 1)
        for term in terms
    )


def form_multiplicity(terms: list[Term]) -> dict[tuple[int, int], int]:
    """How often each ``(u, v)`` pair appears, i.e. where a sharing schedule could save CX."""
    counts: dict[tuple[int, int], int] = {}
    for term in terms:
        counts[(term.left, term.right)] = counts.get((term.left, term.right), 0) + 1
    return counts


if __name__ == "__main__":  # pragma: no cover - reporting helper
    for field in (4, 5):
        reference = expected(field)
        for label, terms in (
            ("schoolbook", schoolbook(field)),
            ("karatsuba", karatsuba(field)),
            ("rank-floor", rank_floor(field)),
        ):
            if expand(field, terms) != reference:
                raise AssertionError(f"{label} does not expand to the GF(2^{field}) tensor")
            emitted = emit(field, terms)
            shared = emit(field, terms, share=True)
            print(
                f"GF(2^{field}) {label:10s} terms={emitted.terms:3d} "
                f"incidences={emitted.incidences:3d} ccx={emitted.ccx:3d} cx={emitted.cx:3d} "
                f"(fold {emitted.fold_cx:3d}) depth={emitted.depth:3d} "
                f"failures={exhaustive_failures(field, emitted)} "
                f"shared_cx={shared.cx:3d} greedy={greedy_cost(terms):3d}"
            )
    print()
    for label, terms in (
        ("schoolbook", schoolbook(12)),
        ("karatsuba", karatsuba(12)),
        ("rank-floor", rank_floor(12)),
    ):
        if expand(12, terms) != expected(12):
            raise AssertionError(f"{label} does not expand to the GF(2^12) tensor")
        emitted = emit(12, terms)
        shared = emit(12, terms, share=True)
        multiplicity = form_multiplicity(terms)
        print(
            f"GF(2^12) {label:10s} terms={emitted.terms:3d} "
            f"incidences={emitted.incidences:3d} ccx={emitted.ccx:3d} cx={emitted.cx:3d} "
            f"(fold {emitted.fold_cx:3d}) depth={emitted.depth:3d} width={emitted.width} "
            f"shared_cx={shared.cx:3d} greedy={greedy_cost(terms):4d} "
            f"max_form_multiplicity={max(multiplicity.values())}"
        )
