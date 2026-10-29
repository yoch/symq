"""Public, standalone GF(2^d) HMR phase-debt reference (no private fixtures).

A completely independent mathematical oracle for the *declared* polynomial
multiply-accumulate family in public PR #94. No SymQ import: Python stdlib only.
This does NOT claim to reproduce a real external compiler output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from fractions import Fraction


def multiply(a: int, b: int, degree: int, modulus: int) -> int:
    """Schoolbook polynomial multiplication in GF(2), followed by reduction."""
    p = 0
    for i in range(degree):
        for j in range(degree):
            p ^= (((a >> i) & 1) & ((b >> j) & 1)) << (i + j)
    while p.bit_length() > degree:
        p ^= modulus << (p.bit_length() - degree - 1)
    return p


def output(x: int, degree: int, modulus: int) -> int:
    mask = (1 << degree) - 1
    a, b = x & mask, (x >> degree) & mask
    return x ^ (multiply(a, b, degree, modulus) << (2 * degree))


def kraus_column(x: int, m: int, degree: int, modulus: int,
                 corrected: bool) -> tuple[int, int]:
    """Unnormalised relative sign per HMR outcome, and output basis index.

    The common positive Kraus amplitude is 2**(-degree/2). On matrix
    units K_m |x><y| K_m^dagger, it becomes exactly Fraction(1,2**degree).
    """
    mask = (1 << degree) - 1
    product = multiply(x & mask, (x >> degree) & mask, degree, modulus)
    hmr_phase = (m & product).bit_count() % 2
    feedback_phase = hmr_phase if corrected else 0
    return output(x, degree, modulus), (-1 if hmr_phase ^ feedback_phase else 1)


def coherence_coefficient(x: int, y: int, degree: int, modulus: int,
                          corrected: bool) -> Fraction:
    """Exact (outcome-forgotten) coefficient of |F(x)><F(y)|."""
    total = Fraction(0)
    for m in range(1 << degree):
        left, sx = kraus_column(x, m, degree, modulus, corrected)
        right, sy = kraus_column(y, m, degree, modulus, corrected)
        assert left == output(x, degree, modulus)
        assert right == output(y, degree, modulus)
        total += Fraction(sx * sy, 1 << degree)
    return total


def verify(degree: int, modulus: int, samples: int = 160) -> dict:
    if degree not in (2, 3) or (modulus not in (0b111, 0b1011)):
        raise ValueError("only the declared GF4 and GF8 instances are supported")
    if (degree, modulus) not in ((2, 0b111), (3, 0b1011)):
        raise ValueError("modulus/degree pair is invalid")
    width = 3 * degree
    size = 1 << width
    rng = random.Random(20261029 + degree)
    pairs = [(x, x) for x in range(size)]
    pairs.extend((rng.randrange(size), rng.randrange(size)) for _ in range(samples))
    # Force off-diagonal pairs with distinct bilinear products.
    pairs.extend([(0, (1 << degree) | 1), (0, size - 1)])
    counterexample = None
    for x, y in pairs:
        corrected = coherence_coefficient(x, y, degree, modulus, True)
        if corrected != 1:
            raise AssertionError(("corrected-channel", degree, x, y, corrected))
        raw = coherence_coefficient(x, y, degree, modulus, False)
        gx = multiply(x & ((1 << degree)-1), (x >> degree) & ((1 << degree)-1),
                      degree, modulus)
        gy = multiply(y & ((1 << degree)-1), (y >> degree) & ((1 << degree)-1),
                      degree, modulus)
        expected = Fraction(int(gx == gy), 1)
        if raw != expected:
            raise AssertionError(("uncorrected-kernel", degree, x, y, raw, expected))
        if expected == 0 and counterexample is None:
            counterexample = {"x":x,"y":y,"uncorrected":0,"corrected":1}
    if counterexample is None:
        raise AssertionError("missing coherence-loss counterexample")
    return {
        "family":"standalone_public_field_mac_hmr",
        "degree":degree,"modulus_binary":bin(modulus),
        "data_bits":width,"scratch_bits":degree,"hmr_events":degree,
        "all_data_basis_inputs_checked":size,
        "coherence_pairs_checked":len(pairs),
        "kernel_counterexample":counterexample,
        "oracle":"independent_stdlib_fraction_exact_Kraus_sum",
        "no_external_private_compiler_claim":True,
    }


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--degree",type=int,choices=(2,3),default=3)
    parser.add_argument("--samples",type=int,default=160)
    args=parser.parse_args()
    modulus={2:0b111,3:0b1011}[args.degree]
    report=verify(args.degree,modulus,args.samples)
    payload=json.dumps(report,sort_keys=True,separators=(",",":"))
    print(json.dumps({**report,"report_sha256":hashlib.sha256(payload.encode()).hexdigest()},
                     indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
