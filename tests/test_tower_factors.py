"""Exact small-field tower factors: certificates, fingerprints and dirty-register semantics.

A public open-set corpus is regression evidence, not a blind holdout.
"""
from __future__ import annotations

import hashlib

import pytest

from symq import Budget, check_equivalence
from symq.circuit import Circuit
from symq.generators import gf2n

FINGERPRINTS = {
    (4, 0x13): "bd7b174c1c7cf7fa8ae28b933fe0430fbbf3983c258282f2422cc8e5916c6bda",
    (6, 0x43): "5ef19b50be6927e964857bacd31f1d3b62c283c0b214e28a4cf9d2ddab48d5a0",
    (6, 0x49): "9c887fff443b5a6f086ca1ce1f8a8862ae98c235967149cbc0a203285e97296f",
}


def independent_product(a: int, b: int, n: int, modulus: int) -> int:
    """Polynomial convolution then long division: a different algorithm from gf2n.gf_mul."""
    coefficients = 0
    for i in range(n):
        for j in range(n):
            if a >> i & b >> j & 1:
                coefficients ^= 1 << (i + j)
    for degree in range(2 * n - 2, n - 1, -1):
        if coefficients >> degree & 1:
            coefficients ^= modulus << (degree - n)
    return coefficients


@pytest.mark.parametrize(
    "n,modulus,rank,cx",
    [(4, 0x13, 9, 30), (6, 0x43, 15, 92), (6, 0x49, 15, 82)],
)
def test_tower_certification_and_complete_dirty_register_semantics(n, modulus, rank, cx):
    factors = gf2n.tower_factors(n, modulus=modulus)
    assert len(factors) == rank
    gf2n.certify_bilinear_decomposition(n, factors, modulus=modulus)
    encoded = ";".join(f"{t.left:x},{t.right:x},{t.into:x}" for t in factors).encode()
    assert hashlib.sha256(encoded).hexdigest() == FINGERPRINTS[(n, modulus)]

    circuit = gf2n.tower_multiplier(n, modulus=modulus)
    assert circuit.width == 3 * n
    counts = circuit.counts()
    assert counts.get("ccx", 0) == rank
    assert counts.get("cx", 0) == cx
    assert {g.name for g in circuit.gates} <= {"cx", "ccx"}

    # Exhaust all operand pairs. Four unrelated, dirty accumulator words
    # ensure that no output preparation assumption is smuggled in.
    mask = (1 << n) - 1
    for a in range(1 << n):
        for b in range(1 << n):
            product = independent_product(a, b, n, modulus)
            for z in (0, mask, ((a << 1) ^ b) & mask, 1):
                x = a | (b << n) | (z << (2 * n))
                expected = a | (b << n) | ((z ^ product) << (2 * n))
                assert circuit.run(x) == expected


def test_returned_factor_lists_are_independent():
    terms = gf2n.tower_factors(6, modulus=0x43)
    original = tuple(terms)
    terms.pop()
    assert tuple(gf2n.tower_factors(6, modulus=0x43)) == original


@pytest.mark.parametrize("n,modulus", [(4, 0x15), (6, 0x41), (6, 0x43)])
def test_validation_rejects_bad_fields_and_wrong_basis(n, modulus):
    if modulus != 0x43:
        with pytest.raises(ValueError, match="irreducible"):
            gf2n.tower_factors(n, modulus=modulus)
    else:
        foreign = gf2n.tower_factors(6, modulus=0x49)
        with pytest.raises(ValueError, match="tensor mismatch"):
            gf2n.certify_bilinear_decomposition(6, foreign, modulus=modulus)


@pytest.mark.parametrize("n,modulus", [(3, 0xB), (5, 0x25), (True, 0x13), (6, True)])
def test_tower_unsupported_arguments_fail_closed(n, modulus):
    with pytest.raises(ValueError):
        gf2n.tower_factors(n, modulus=modulus)


def test_tower_mutation_detected_and_legacy_default_unchanged():
    terms = gf2n.tower_factors(4, modulus=0x13)
    bad = list(terms)
    old = bad[0]
    bad[0] = gf2n.Term(old.left, old.right, old.into ^ 1)
    with pytest.raises(ValueError, match="tensor mismatch"):
        gf2n.certify_bilinear_decomposition(4, bad, modulus=0x13)
    before = gf2n.multiplier(4, "schoolbook")
    assert before.counts().get("ccx", 0) == gf2n.emit(
        4, gf2n.schoolbook(4), strategy="incidence"
    ).ccx
    after = gf2n.tower_multiplier(4, modulus=0x13)
    assert after.counts()["ccx"] == 9


def test_tower_is_safe_in_full_context_and_mutant_replays():
    # This checks the complete reversible permutation (including a nontrivial
    # common prefix/suffix), not the contextual SAT cut theorem.
    n, mod = 4, 0x13
    basic = [
        gf2n.Term(1 << i, 1 << j, independent_product(1 << i, 1 << j, n, mod))
        for i in range(n) for j in range(n)
    ]
    baseline = gf2n.emit(n, basic).circuit
    optimized = gf2n.tower_multiplier(n, modulus=mod)
    before = Circuit(3 * n).cx(0, 2 * n).cx(2 * n + 1, 2)
    after = Circuit(3 * n).ccx(4, 3, 11).cx(11, 0)
    original = Circuit(3 * n, before.gates + baseline.gates + after.gates)
    improved = Circuit(3 * n, before.gates + optimized.gates + after.gates)
    verdict = check_equivalence(original, improved, backend="zdd", budget=Budget(max_seconds=20))
    assert verdict.equivalent

    mutated = Circuit(improved.width, list(improved.gates))
    first_ccx = next(i for i, gate in enumerate(optimized.gates) if gate.name == "ccx")
    del mutated.gates[len(before.gates) + first_ccx]  # definitely changes the product
    wrong = check_equivalence(original, mutated, backend="zdd", budget=Budget(max_seconds=20))
    assert not wrong.equivalent
    assert original.run(wrong.witness) != mutated.run(wrong.witness)
