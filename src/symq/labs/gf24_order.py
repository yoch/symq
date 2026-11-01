"""Pinned order of the 99 GF(2^24) tower products: 99 CCX and 2634 CX.

A restricted deterministic research search identified this term order:
1,000 seeded fast-distance 2-opt starts, each evaluated by an exact
per-register dynamic-programming pivot scheduler, followed by bounded
exact local segment reversals. It is an *upper-bound construction*, not
a globally optimal CNOT network, field basis or proven shortest path.

Unlike a mutable optimizer state, both the factor identity and order
are checked before emitting any candidate. The general SymQ
`pivot-scheduled` emitter remains unchanged; this specialization
passes a pre-ordered factor list to the fixed-order `pivot` emitter.
"""
from __future__ import annotations

import hashlib

from symq.circuit import Circuit
from symq.generators.gf2n import Emitted, emit
from symq.labs.gf24_tower import gf24_tower_factors

__all__ = ["PINNED_FACTOR_SHA256", "PINNED_ORDER", "PINNED_ORDER_SHA256", "pinned_gf24_circuit",
           "pinned_gf24_emitted"]

PINNED_FACTOR_SHA256 = "549b1c30d2bee1a35fca79d96defd4ad99870a4fb59f0d9b9960fe125472c88a"
PINNED_ORDER_SHA256 = "8cbeef54ef072eb20f6360ac61038fe84ca158a8ce401b868043033af62730b6"

PINNED_ORDER: tuple[int, ...] = (
    91, 4, 7, 35, 76, 46, 34, 1, 15, 6, 2, 95, 90, 39, 75, 3, 0, 87,
    41, 23, 20, 59, 37, 36, 10, 97, 72, 32, 84, 68, 80, 38, 86, 5, 94,
    98, 81, 50, 21, 44, 78, 63, 18, 51, 55, 13, 25, 16, 64, 48, 12,
    9, 67, 77, 45, 14, 57, 65, 47, 83, 54, 31, 53, 88, 82, 71, 61,
    49, 40, 66, 56, 24, 26, 79, 30, 74, 29, 28, 58, 89, 69, 60,
    8, 17, 93, 92, 19, 85, 27, 11, 33, 42, 70, 73, 52, 43, 62, 22, 96,
)


def pinned_gf24_emitted() -> Emitted:
    """Emit a fully tensor-certified GF24 multiplier at 99 CCX / 2634 CX.

    Recompute and pin the exact source factor bytes, exact permutation
    order and emitted physical gate counts; none is taken from a label
    or historic cached receipt.
    """
    factors = gf24_tower_factors()
    encoded = ";".join(f"{t.left:x},{t.right:x},{t.into:x}" for t in factors).encode("ascii")
    if hashlib.sha256(encoded).hexdigest() != PINNED_FACTOR_SHA256:
        raise ValueError("source GF24 factorization fingerprint changed")
    if (len(PINNED_ORDER) != 99 or sorted(PINNED_ORDER) != list(range(99))
            or hashlib.sha256(",".join(map(str, PINNED_ORDER)).encode("ascii")).hexdigest()
            != PINNED_ORDER_SHA256):
        raise ValueError("GF24 factor-order permutation is corrupted")
    emitted = emit(24, [factors[index] for index in PINNED_ORDER], strategy="pivot")
    if emitted.ccx != 99 or emitted.cx != 2634 or emitted.width != 72:
        raise ValueError("pinned GF24 gate-count contract unexpectedly changed")
    return emitted


def pinned_gf24_circuit() -> Circuit:
    """The pinned 72-wire multiplier ``(a, b, z) -> (a, b, z XOR a*b)`` modulo ``0x100001B``."""
    return pinned_gf24_emitted().circuit
