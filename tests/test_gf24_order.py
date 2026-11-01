"""GF24 source-pinned factor ordering, exact whole-stream proof and proxy costs."""
from __future__ import annotations

import hashlib
import random

import pytest

from symq import Budget
from symq.generators.bilinear_optimization import certify_decomposition
from symq.generators.gf2n import emit
from symq.labs.classical_transcript import (
    Program,
    Slot,
    UnprovedSubstitution,
    digest,
    verify_transcript,
)
from symq.labs.gf24_choice import choose_gf24
from symq.labs.gf24_order import (
    FACTOR_SHA256,
    PINNED_ORDER,
    reordered_gf24,
    reordered_gf24_circuit,
)
from symq.labs.gf24_tower import GF24_MODULUS, gf24_tower_factors


def _integer_product(a: int, b: int) -> int:
    result = 0
    for i in range(24):
        for j in range(24):
            if a >> i & b >> j & 1:
                result ^= 1 << (i + j)
    for degree in range(46, 23, -1):
        if result >> degree & 1:
            result ^= GF24_MODULUS << (degree - 24)
    return result


def test_pinned_order_preserves_exact_tensor_and_dirty_outputs():
    old = gf24_tower_factors()
    shuffled = reordered_gf24()
    assert len(shuffled) == len(old) == 99
    assert len(PINNED_ORDER) == len(set(PINNED_ORDER)) == 99
    assert set(shuffled) == set(old)
    certify_decomposition(24, shuffled, GF24_MODULUS)
    full = reordered_gf24_circuit()
    assert full.width == 72
    assert full.counts().get("ccx", 0) == 99
    assert full.counts().get("cx", 0) == 2646
    baseline = emit(24, list(old), strategy="pivot-scheduled").circuit
    assert baseline.counts().get("cx", 0) == 2750

    rng = random.Random(20261101)
    mask = (1 << 24) - 1
    examples = [0, (1 << 72) - 1] + [rng.getrandbits(72) for _ in range(96)]
    for state in examples:
        a, b, z = state & mask, (state >> 24) & mask, (state >> 48) & mask
        expected = a | (b << 24) | ((z ^ _integer_product(a, b)) << 48)
        assert full.run(state) == expected


def test_exact_packed_proof_of_new_order_against_old_gate_stream():
    old = emit(24, list(gf24_tower_factors()), strategy="pivot-scheduled").circuit
    new = reordered_gf24_circuit()
    reference, candidate = Program.freeze(old), Program.freeze(new)
    proof = verify_transcript(
        old, new, (Slot(reference, candidate, tuple(range(72))),),
        reference_sha256=digest(reference), candidate_sha256=digest(candidate),
        backend="packed", budget=Budget(max_seconds=30, max_terms=4000),
    )
    assert proof.equivalent and proof.backend == "packed"
    # Removing a single CCX provably changes the product.
    mutant = new.__class__(new.width, list(new.gates))
    first = next(i for i, g in enumerate(mutant.gates) if g.name == "ccx")
    del mutant.gates[first]
    damaged = Program.freeze(mutant)
    with pytest.raises(UnprovedSubstitution):
        verify_transcript(
            old, mutant, (Slot(reference, damaged, tuple(range(72))),),
            reference_sha256=digest(reference), candidate_sha256=digest(damaged),
            backend="packed", budget=Budget(max_seconds=30, max_terms=4000),
        )


def test_explicit_opt_in_cost_selection_and_fingerprint_guard(monkeypatch):
    choice = choose_gf24(
        ccx_weight=32, cx_weight=1, include_pinned_order=True
    )
    assert choice.method == "tower-99-pinned-order"
    assert choice.cost.ccx == 99
    assert choice.cost.cx == 2646
    assert choice.cost.weighted == 99 * 32 + 2646
    assert len(choice.alternatives) == 4
    legacy = choose_gf24(ccx_weight=32, cx_weight=1)
    assert len(legacy.alternatives) == 3
    assert legacy.cost.cx == 2750
    with pytest.raises(ValueError, match="bool"):
        choose_gf24(ccx_weight=32, cx_weight=1, include_pinned_order=1)

    import symq.labs.gf24_order as order_module

    assert len(FACTOR_SHA256) == 64
    original = order_module.FACTOR_SHA256
    monkeypatch.setattr(order_module, "FACTOR_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="factor snapshot"):
        reordered_gf24()
    monkeypatch.setattr(order_module, "FACTOR_SHA256", original)
    raw = ";".join(
        f"{t.left:x},{t.right:x},{t.into:x}" for t in gf24_tower_factors()
    ).encode("ascii")
    assert hashlib.sha256(raw).hexdigest() == FACTOR_SHA256
