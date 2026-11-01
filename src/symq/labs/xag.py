"""Research analyses of GF(2^n) multiplication decompositions (no API promise).

The field arithmetic, the three decompositions and the circuit emitter are maintained in
``symq.generators.gf2n``; this module keeps the analyses built on them: the incidence lower bound,
GF(2) ranks of the coordinate slices, exhaustive and symbolic proofs of emitted circuits, and cost
accounting of the per-term schedule.

Bilinear tensor of GF(2^n) multiplication and its incidence lower bound.

**Status of this module.** This module measures no particular circuit. It establishes a statement
about the *function*

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

from symq.backends import Algebra, make_algebra, simulate
from symq.circuit import Circuit
from symq.generators.gf2n import (
    MODULI,
    Emitted,
    Term,
    _pivot,
    coordinate_slices,
    emit,
    expand,
    gf_mul,
    is_irreducible,
    karatsuba,
    rank_floor,
    schoolbook,
    tensor,
)
from symq.generators.gf2n import expected_tensor as expected
from symq.resources import Budget as ResourceBudget

__all__ = [
    "MODULI", "Emitted", "IncidenceBudget", "Proof", "Term", "budget", "coordinate_slices", "emit",
    "exhaustive_failures", "expand", "expected", "fanout_shortcut", "form_multiplicity", "gf_mul",
    "greedy_cost", "is_irreducible", "karatsuba", "nonzero_multiplication_is_a_bijection",
    "prove", "prove_against_terms", "prove_equivalence", "rank_floor", "rank_gaussian",
    "rank_incremental", "reference_outputs", "schoolbook", "tensor", "term_outputs",
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
class IncidenceBudget:
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


def budget(n: int) -> IncidenceBudget:
    """Coordinate ranks plus the incidence floor, cross-checked by two rank algorithms."""
    slices = coordinate_slices(n)
    by_gaussian = [rank_gaussian(rows, n) for rows in slices]
    by_incremental = [rank_incremental(rows) for rows in slices]
    if by_gaussian != by_incremental:
        raise AssertionError(
            f"rank algorithms disagree for GF(2^{n}): {by_gaussian} vs {by_incremental}"
        )
    table = tensor(n)
    return IncidenceBudget(
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


@dataclass(frozen=True)
class Proof:
    """Outcome of an exact equivalence check."""

    equivalent: bool
    wires_checked: int
    mismatches: tuple[int, ...]
    backend: str

    def __str__(self) -> str:  # pragma: no cover - reporting helper
        verdict = "EQUIVALENT" if self.equivalent else f"DIFFERS on wires {self.mismatches}"
        return f"{verdict} ({self.wires_checked} wires, backend {self.backend})"


def _algebra(width: int, *, max_terms: int | None = None) -> Algebra:
    budget = ResourceBudget(max_terms=max_terms) if max_terms is not None else ResourceBudget()
    return make_algebra("sparse", width, budget)


def reference_outputs(n: int) -> list:
    """Expected ANF of every output wire of a ``3n``-wire GF(2^n) multiply-accumulate.

    Wire ``i < n`` must carry ``a_i``, wire ``n + j`` must carry ``b_j``, and wire ``2n + k`` must
    carry ``z_k`` XOR the ``k``-th bit of ``a*b``.
    """
    width = 3 * n
    algebra = _algebra(width)
    outputs = []
    for wire in range(width):
        if wire < 2 * n:
            outputs.append(algebra.variable(wire))
            continue
        bit = wire - 2 * n
        total = algebra.variable(wire)
        for i in range(n):
            for j in range(n):
                if gf_mul(n, 1 << i, 1 << j) >> bit & 1:
                    total = algebra.xor(
                        total,
                        algebra.product([algebra.variable(i), algebra.variable(n + j)]),
                    )
        outputs.append(total)
    return outputs


def term_outputs(n: int, terms: list[Term]) -> list:
    """Expected ANFs derived from a term set, independently of the circuit that emits it."""
    width = 3 * n
    algebra = _algebra(width)
    outputs = [algebra.variable(wire) for wire in range(width)]
    for term in terms:
        left = None
        for i in range(n):
            if term.left >> i & 1:
                var = algebra.variable(i)
                left = var if left is None else algebra.xor(left, var)
        right = None
        for j in range(n):
            if term.right >> j & 1:
                var = algebra.variable(n + j)
                right = var if right is None else algebra.xor(right, var)
        if left is None or right is None:
            raise ValueError("term with an empty form")
        product = algebra.product([left, right])
        for k in range(n):
            if term.into >> k & 1:
                outputs[2 * n + k] = algebra.xor(outputs[2 * n + k], product)
    return outputs


def prove(n: int, circuit: Circuit, *, max_terms: int | None = None) -> Proof:
    """Prove ``circuit`` implements the multiply-accumulate contract on every input.

    Compares the simulated ANF of each output wire against the reference built from the field table.
    ANFs are canonical, so wire-by-wire equality is functional equivalence.
    """
    if circuit.width != 3 * n:
        raise ValueError(f"expected width {3 * n}, got {circuit.width}")
    algebra = _algebra(3 * n, max_terms=max_terms)
    actual = simulate(circuit, algebra)
    reference = reference_outputs(n)
    if len(actual) != len(reference):
        raise AssertionError("simulation returned a different number of wires")
    mismatches = tuple(
        wire
        for wire, (got, want) in enumerate(zip(actual, reference))
        if not algebra.equal(got, want)
    )
    return Proof(not mismatches, len(reference), mismatches, algebra.name)


def prove_against_terms(
    n: int, circuit: Circuit, terms: list[Term], *, max_terms: int | None = None
) -> Proof:
    """Prove ``circuit`` equals the function its term set denotes, and that the term set is GF(2^n).

    The second half is the algebraic identity ``expand(terms) == expected(n)``: a check that the term
    set is a correct bilinear algorithm, independent of any circuit.
    """
    if expand(n, terms) != expected(n):
        raise AssertionError("term set does not compute GF(2^n) multiplication")
    if circuit.width != 3 * n:
        raise ValueError(f"expected width {3 * n}, got {circuit.width}")
    algebra = _algebra(3 * n, max_terms=max_terms)
    actual = simulate(circuit, algebra)
    reference = term_outputs(n, terms)
    mismatches = tuple(
        wire
        for wire, (got, want) in enumerate(zip(actual, reference))
        if not algebra.equal(got, want)
    )
    return Proof(not mismatches, len(reference), mismatches, algebra.name)


def prove_equivalence(left: Circuit, right: Circuit, *, max_terms: int | None = None) -> Proof:
    """Prove two circuits of equal width compute the same function, wire by wire."""
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    algebra = _algebra(left.width, max_terms=max_terms)
    actual_left = simulate(left, algebra)
    actual_right = simulate(right, algebra)
    mismatches = tuple(
        wire
        for wire, (a, b) in enumerate(zip(actual_left, actual_right))
        if not algebra.equal(a, b)
    )
    return Proof(not mismatches, len(actual_left), mismatches, algebra.name)
