"""Exact equivalence proof for GF(2^n) multiply-accumulate candidates at every width.

The emitters are verified by enumeration only up to ``n = 5`` (``2^15`` inputs). GF(2^12) has
``2^36`` inputs, so enumeration is impossible and the proof has to be symbolic: build the *expected*
output polynomial of each wire independently of the circuit, then compare canonical ANFs.

Two independent constructions of the reference are checked against each other, because an oracle that
was itself derived from the emitter would prove nothing:

1. **from the field table** -- wire ``z_k`` must equal ``z_k`` XOR bit ``k`` of ``a*b``, where
   ``a*b`` comes from :func:`tensor_budget.gf_mul`, and wires ``a``, ``b`` must be unchanged. Each
   ``(a_i, b_j)`` monomial is expanded by XOR-ing the ANF monomial ``a_i b_j`` into every output bit
   the field product touches.
2. **from the term set** -- the emitter's own terms, expanded algebraically. Agreement of the two
   means the emitter computes the intended function.

This proves functional equivalence of the emitted circuit to ``(a, b, z) -> (a, b, z xor a*b)``, which
is strictly stronger than testing the 144 basis products: it holds for every one of the ``2^36``
inputs at once.
"""

from __future__ import annotations

from dataclasses import dataclass

from decompositions import Term, expand, expected
from tensor_budget import gf_mul

from symq.backends import Algebra, make_algebra, simulate
from symq.circuit import Circuit
from symq.resources import Budget


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
    budget = Budget(max_terms=max_terms) if max_terms is not None else Budget()
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


if __name__ == "__main__":  # pragma: no cover - reporting helper
    from decompositions import emit, karatsuba, rank_floor, schoolbook

    for field in (4, 5):
        for label, builder in (
            ("schoolbook", schoolbook),
            ("karatsuba", karatsuba),
            ("rank-floor", rank_floor),
        ):
            terms = builder(field)
            proof = prove_against_terms(field, emit(field, terms).circuit, terms)
            print(f"GF(2^{field}) {label:10s} {proof}")

    for label, builder in (
        ("schoolbook", schoolbook),
        ("karatsuba", karatsuba),
        ("rank-floor", rank_floor),
    ):
        terms = builder(12)
        proof = prove_against_terms(12, emit(12, terms).circuit, terms)
        print(f"GF(2^12) {label:10s} {proof}")
