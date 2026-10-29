"""Source-cleared multi-bit finite-field HMR correction case, independent of private data.

A small polynomial-basis binary-field multiply-accumulate provides genuinely
multi-output phase debts. The reference is a reversible classical permutation
and the interpreter enumerates every small input and measurement outcome.
"""
from __future__ import annotations

import pytest

from research.hmr_feedback.repair import synthesize_feedback
from symq.phase import PhaseProgram, check_phase_equivalence, phase_semantics
from symq.phase_oracle import run_program


def _reduce(poly: int, degree: int, irreducible: int) -> int:
    while poly.bit_length() > degree:
        poly ^= irreducible << (poly.bit_length() - degree - 1)
    return poly


def _multiply(a: int, b: int, degree: int, irreducible: int) -> int:
    result = 0
    for i in range(degree):
        for j in range(degree):
            if (a >> i & 1) and (b >> j & 1):
                result ^= 1 << (i + j)
    return _reduce(result, degree, irreducible)


def _build(degree: int, irreducible: int) -> tuple[PhaseProgram, PhaseProgram]:
    """Independent coherent product/erase vs direct in-place field MAC.

    Quantum data wires are arbitrary A, B and accumulator C (each degree bits);
    ancilla product T is guaranteed |0> at entry and is HMR-cleaned at exit.
    """
    data = 3 * degree
    raw = PhaseProgram(data, degree)
    reference = PhaseProgram(data, degree)

    # Multiplication by polynomial convolution and reduction. Every output
    # coefficient is a sum of independently controlled AND terms.
    for i in range(degree):
        for j in range(degree):
            word = _reduce(1 << (i + j), degree, irreducible)
            for k in range(degree):
                if word >> k & 1:
                    raw.ccx(i, degree + j, data + k)
                    reference.ccx(i, degree + j, 2 * degree + k)

    for k in range(degree):
        raw.cx(data + k, 2 * degree + k)
    for k in range(degree):
        raw.hmr(data + k)
    return raw, reference


@pytest.mark.parametrize("degree,irreducible", [(2, 0b111), (3, 0b1011)])
def test_repair_full_field_multiply_accumulate_across_multiple_hmr(degree, irreducible):
    raw, reference = _build(degree, irreducible)
    before = phase_semantics(raw)
    assert any("O2" in violation for violation in before.violations())
    assert raw.measurements == degree

    repaired, receipt = synthesize_feedback(
        raw, max_arity=2, max_data=3 * degree,
        max_candidates=200, max_ops=512,
    )
    receipt.assert_fresh(raw, repaired)
    assert repaired.measurements == degree
    assert {repair.outcome for repair in receipt.repairs} == set(range(degree))
    assert phase_semantics(repaired).outputs == before.outputs
    assert not phase_semantics(repaired).violations()
    verdict = check_phase_equivalence(repaired, reference)
    assert verdict.equivalent and verdict.up_to_global_phase

    # This is not merely an oracle-to-itself comparison: the expected output
    # is calculated by a separate polynomial-basis integer field multiplier.
    mask = (1 << degree) - 1
    for x in range(1 << (3 * degree)):
        a = x & mask
        b = (x >> degree) & mask
        expected = x ^ (
            _multiply(a, b, degree, irreducible) << (2 * degree)
        )
        for m in range(1 << degree):
            assert run_program(repaired, x, m) == {expected: 1}, (
                degree, x, m
            )


def test_field_mac_missing_one_feedback_is_detected():
    degree, poly = 2, 0b111
    raw, reference = _build(degree, poly)
    repaired, _ = synthesize_feedback(
        raw, max_arity=2, max_data=6, max_candidates=128,
    )
    correction = next(i for i, op in enumerate(repaired.ops) if op.kind == "mcz_if")
    wrong = PhaseProgram(repaired.data, repaired.ancillas, list(repaired.ops))
    wrong.ops.pop(correction)
    verdict = check_phase_equivalence(wrong, reference)
    assert not verdict.equivalent
    assert verdict.violations
    # A concrete branch must distinguish the missing correction.
    mask = (1 << degree) - 1
    witnesses = []
    for x in range(1 << (3 * degree)):
        a, b = x & mask, (x >> degree) & mask
        expected = x ^ (_multiply(a, b, degree, poly) << (2 * degree))
        for m in range(1 << degree):
            if run_program(wrong, x, m) != {expected: 1}:
                witnesses.append((x, m))
    assert witnesses
