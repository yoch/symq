"""External-method bilinear GF(64) certificate; research/benchmark use only.

The 15 triples were independently reconstructed using the GF(4) tower
GF(4)[z]/(z^3+z+1), five-point interpolation and three-term GF(4)
multiplication, then mapped into GF(64) with modulus x^6+x+1.
The construction follows Polytof's published mathematical approach:
https://github.com/ZIB-IOL/polytof (MIT, 0dcac107d15adc34dc646242d222f21ae7d32699)
https://arxiv.org/abs/2602.15285

This is not a source extraction from a Kaggle dataset, not a claim of optimal
bilinear rank, and not the official Kaggle gate-cost model.
"""
from __future__ import annotations

import hashlib
import json

from symq.circuit import Circuit
from symq.generators.gf2n import Term, expand, expected_tensor

# Canonical format: {"modulus":67,"n":6,"terms":[[u,v,w],...]},
# JSON with sort_keys=True and separators=(',', ':'); integer masks are LSB-first.
N = 6
MODULUS = 0x43
RAW_TERMS: tuple[tuple[int, int, int], ...] = (
    (23, 23, 13), (32, 32, 14), (55, 55, 3),
    (19, 19, 62), (6, 6, 22), (21, 21, 40),
    (29, 29, 34), (30, 30, 16), (3, 3, 50),
    (25, 25, 42), (56, 56, 9), (33, 33, 35),
    (44, 44, 5), (28, 28, 23), (48, 48, 18),
)
CERTIFICATE_SHA256 = "f01ea3a59be8f6b40de148286fc3f968b469f8eb97eea2d0bf9976155b48c39c"


def fingerprint() -> str:
    source = {"modulus": MODULUS, "n": N, "terms": RAW_TERMS}
    payload = json.dumps(source, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def certified_terms() -> list[Term]:
    """Check the exact GF(2) multiplication tensor, then return term records."""
    masks = (1 << N) - 1
    if len(RAW_TERMS) != 15 or any(
        not all(type(v) is int and 0 < v <= masks for v in row)
        for row in RAW_TERMS
    ):
        raise ValueError("malformed GF(64) rank-15 factor data")
    if fingerprint() != CERTIFICATE_SHA256:
        raise ValueError("GF(64) factor data fingerprint mismatch")
    out = [Term(*row) for row in RAW_TERMS]
    if expand(N, out) != expected_tensor(N):
        raise ValueError("invalid GF(64) tensor decomposition")
    return out


def borrowed_scratch_circuit() -> Circuit:
    """Compute (a,b,z,s) -> (a,b,z XOR a*b,s), including dirty s.

    The 19th wire is a *borrowed* scratch qubit.  Every term's product is
    computed/uncomputed with two CCX gates.  During the CX fanout it holds
    s XOR product, so the constant s disappears only because XOR of all 15
    output masks is exactly zero.  This guard is required for dirty scratch.
    The circuit never reads z, so its truth table at z=0 extends to all z.
    As it is a reversible permutation equal on every basis input, the same
    substitution is valid on coherent superpositions (no measurement/phase).
    """
    terms = certified_terms()
    checksum = 0
    for term in terms:
        checksum ^= term.into
    if checksum:
        raise ValueError("factor outputs do not cancel borrowed scratch offset")
    c = Circuit(3 * N + 1)
    scratch = 3 * N
    for term in terms:
        i = (term.left & -term.left).bit_length() - 1
        j = (term.right & -term.right).bit_length() - 1
        left_folds = tuple(k for k in range(N) if k != i and (term.left >> k) & 1)
        right_folds = tuple(k for k in range(N) if k != j and (term.right >> k) & 1)
        for k in left_folds:
            c.append("cx", k, i)
        for k in right_folds:
            c.append("cx", N + k, N + j)
        c.append("ccx", i, N + j, scratch)
        for k in range(N):
            if (term.into >> k) & 1:
                c.append("cx", scratch, 2 * N + k)
        c.append("ccx", i, N + j, scratch)
        for k in reversed(right_folds):
            c.append("cx", N + k, N + j)
        for k in reversed(left_folds):
            c.append("cx", k, i)
    return c


def pivot_fanout_circuit() -> Circuit:
    """Compute (a,b,z) -> (a,b,z XOR a*b), using one CCX per factor.

    One output bit is a temporary *dirty accumulator*, not an ancilla.
    For each other output bit k in the factor mask, CX(pivot,k) before
    and after CCX(a_parity,b_parity,pivot) eliminates the original pivot
    bit and adds only the product. This is exact on arbitrary z inputs.
    The input parities are folded/unfolded around the operation.
    """
    c = Circuit(3 * N)
    for term in certified_terms():
        left_pivot = (term.left & -term.left).bit_length() - 1
        right_pivot = (term.right & -term.right).bit_length() - 1
        output_pivot = (term.into & -term.into).bit_length() - 1
        left_extra = tuple(k for k in range(N) if k != left_pivot and term.left >> k & 1)
        right_extra = tuple(k for k in range(N) if k != right_pivot and term.right >> k & 1)
        other_outputs = tuple(k for k in range(N)
                              if k != output_pivot and term.into >> k & 1)
        for k in left_extra:
            c.append("cx", k, left_pivot)
        for k in right_extra:
            c.append("cx", N + k, N + right_pivot)
        for k in other_outputs:
            c.append("cx", 2 * N + output_pivot, 2 * N + k)
        c.append("ccx", left_pivot, N + right_pivot, 2 * N + output_pivot)
        for k in other_outputs:
            c.append("cx", 2 * N + output_pivot, 2 * N + k)
        for k in reversed(right_extra):
            c.append("cx", N + k, N + right_pivot)
        for k in reversed(left_extra):
            c.append("cx", k, left_pivot)
    return c
