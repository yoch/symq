"""Pinned GF24 factor order obtained by a deterministic, bounded search.

The factor list (rank-99, modulus 0x100001B, GF16 root 0xB781C5,
outer beta 0x10) is sourced from SymQ's exact interpolation builder.
A separate reproducibility runner explores deterministic 2-opt tours
under a *surrogate* symmetric linear-frame cost, then scores each order
with the exact per-register dynamic program. The pinned ordering minimizes
the exact CX count among the searched candidates, not globally.

Only the order of the 99 commuting bilinear products changes.
All 24-bit input registers, an arbitrary dirty output register and all
linear frames are restored. No ancilla or unproven phase rewrite.
"""
from __future__ import annotations

import hashlib

from symq.generators.gf2n import Term, emit
from symq.labs.gf24_tower import gf24_tower_factors

__all__ = ["PINNED_ORDER", "reordered_gf24", "reordered_gf24_circuit"]

FACTOR_SHA256 = "549b1c30d2bee1a35fca79d96defd4ad99870a4fb59f0d9b9960fe125472c88a"
PINNED_ORDER: tuple[int, ...] = (
    91, 4, 7, 35, 76, 46, 34, 1, 6, 15, 2, 95, 90, 39, 75, 3, 0,
    87, 41, 23, 20, 59, 37, 36, 10, 97, 72, 32, 84, 68, 80, 38,
    86, 5, 94, 98, 81, 50, 21, 44, 78, 63, 18, 51, 55, 13, 25,
    16, 64, 48, 12, 9, 67, 77, 45, 14, 57, 65, 47, 83, 54, 31,
    53, 40, 49, 61, 71, 82, 88, 66, 56, 24, 26, 79, 30, 74,
    29, 28, 58, 89, 69, 60, 8, 17, 93, 92, 19, 85, 27, 11,
    33, 42, 70, 73, 52, 43, 62, 22, 96,
)


def _fingerprint(terms: tuple[Term, ...]) -> str:
    raw = ";".join(f"{t.left:x},{t.right:x},{t.into:x}" for t in terms).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def reordered_gf24() -> tuple[Term, ...]:
    """A pinned factor permutation; refuse a changed tensor/algorithm snapshot."""
    factors = gf24_tower_factors()
    if len(factors) != 99 or _fingerprint(factors) != FACTOR_SHA256:
        raise ValueError("unrecognized GF24 factor snapshot; cannot apply stored order")
    if len(PINNED_ORDER) != 99 or set(PINNED_ORDER) != set(range(99)):
        raise ValueError("invalid GF24 factor permutation")
    return tuple(factors[i] for i in PINNED_ORDER)


def reordered_gf24_circuit():
    """99 CCX + 2646 CX under the pinned factor order; all 72 wires are dirty."""
    # The standard 'pivot' emitter computes optimal parity pivots for a FIXED
    # term sequence, rather than changing this pinned sequence again.
    return emit(24, list(reordered_gf24()), strategy="pivot").circuit
