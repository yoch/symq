"""Independent integer oracle and borrowed-ancilla mutation checks."""

from benchmarks.bilinear_rank15_gf64 import (
    CERTIFICATE_SHA256,
    MODULUS,
    RAW_TERMS,
    N,
    borrowed_scratch_circuit,
    certified_terms,
    fingerprint,
)
from benchmarks.bilinear_rank15_reconstruction import rank15_terms
from symq.generators.gf2n import emit, expand, expected_tensor, schoolbook


def _reference_product(a: int, b: int) -> int:
    # Independent of SymQ GF(2^n), including its reduction implementation.
    poly = 0
    for i in range(N):
        for j in range(N):
            if (a >> i) & (b >> j) & 1:
                poly ^= 1 << (i + j)
    for k in range(2 * N - 2, N - 1, -1):
        if (poly >> k) & 1:
            poly ^= MODULUS << (k - N)
    return poly


def _bilinear_product(a: int, b: int, factors=RAW_TERMS) -> int:
    result = 0
    for lmask, rmask, outputs in factors:
        if ((a & lmask).bit_count() & 1) and ((b & rmask).bit_count() & 1):
            result ^= outputs
    return result


def test_exact_certificate_and_pinned_provenance():
    assert fingerprint() == CERTIFICATE_SHA256
    terms = certified_terms()
    assert len(terms) == 15
    assert expand(N, terms) == expected_tensor(N)
    assert rank15_terms() == RAW_TERMS  # independently rederived, pinned factorization
    assert len(set(terms)) == 15


def test_exhaustive_4096_products_against_independent_oracle():
    for a in range(1 << N):
        for b in range(1 << N):
            assert _bilinear_product(a, b) == _reference_product(a, b)


def test_borrowed_scratch_full_classical_behavior():
    circuit = borrowed_scratch_circuit()
    assert circuit.width == 19
    assert len([g for g in circuit.gates if g.name == "ccx"]) == 30
    assert len([g for g in circuit.gates if g.name == "cx"]) == 156
    assert not any(g.name not in {"ccx", "cx"} for g in circuit.gates)
    assert not any(12 <= q < 18 for g in circuit.gates for q in g.qubits[:-1])
    assert not any(g.qubits[-1] == 18 and g.name != "ccx" for g in circuit.gates)
    assert not any(g.qubits[-1] >= 19 for g in circuit.gates)
    checksum = 0
    for _, _, w in RAW_TERMS:
        checksum ^= w
    assert checksum == 0  # permits borrowing a dirty scratch bit
    for a in range(1 << N):
        for b in range(1 << N):
            p = _reference_product(a, b)
            for borrowed in (0, 1):
                for z in (0, 1, 17, 63):
                    before = a | (b << N) | (z << (2 * N)) | (borrowed << (3 * N))
                    after = a | (b << N) | ((z ^ p) << (2 * N)) | (borrowed << (3 * N))
                    assert circuit.run(before) == after


def test_mutants_detected_by_independent_oracle():
    truncated = RAW_TERMS[:-1]
    modified = list(RAW_TERMS)
    u, v, w = modified[0]
    modified[0] = (u, v, w ^ 1)
    for bad in (truncated, modified):
        assert any(
            _bilinear_product(a, b, bad) != _reference_product(a, b)
            for a in range(1 << N) for b in range(1 << N)
        )


def test_cost_semantics_are_not_rank_count():
    baseline = emit(N, schoolbook(N))
    no_scratch = emit(N, certified_terms())
    assert baseline.ccx == 51 and baseline.width == 18
    assert no_scratch.ccx == 40 and no_scratch.width == 18
    assert no_scratch.cx == 116
    # The borrowed implementation uses 30 actual CCX on 19 wires.
