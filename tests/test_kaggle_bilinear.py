"""Reproduction tests on byte-identical Kaggle public KMB data, not a sealed holdout."""

import pytest

from benchmarks.kaggle_bilinear_eval import (
    candidate,
    independent_product,
    manifest,
    run,
    source_starts,
    verify_tensor,
)
from benchmarks.kaggle_bilinear_kmb import parse, simulate
from benchmarks.kaggle_bilinear_towers import build_terms


def test_public_corpus_provenance_and_original_sha256():
    rows = manifest()
    originals = source_starts()
    assert len(rows) == len(originals) == 14
    assert len([row for row in rows if row["width"] == 4]) == 7
    assert len([row for row in rows if row["width"] == 6]) == 7
    assert {row["modulus"] for row in rows} == {0x13, 0x49}
    for row in rows:
        width, ops = parse(originals[row["kmb"]])
        assert width == row["qubits"]
        assert sum(op[0] == 49 for op in ops) == row["start_ccx"]


@pytest.mark.parametrize("n,modulus,rank", [(4, 0x13, 9), (6, 0x49, 15)])
def test_independent_rank_certificate_and_mutants(n, modulus, rank):
    terms, _generator = build_terms(n, modulus)
    assert len(terms) == rank
    verify_tensor(n, modulus, terms)
    with pytest.raises(ValueError, match="tensor mismatch"):
        verify_tensor(n, modulus, terms[:-1])
    mutant = list(terms)
    a, b, target = mutant[0]
    mutant[0] = (a, b, target ^ 1)
    with pytest.raises(ValueError, match="tensor mismatch"):
        verify_tensor(n, modulus, mutant)
    for a in range(1 << n):
        for b in range(1 << n):
            from_terms = 0
            for u, v, w in terms:
                if (a & u).bit_count() & (b & v).bit_count() & 1:
                    from_terms ^= w
            assert from_terms == independent_product(a, b, n, modulus)


def test_field_polynomial_is_pinned():
    assert candidate(6, 0x49)[0] != candidate(4, 0x13)[0]
    with pytest.raises(ValueError, match="no certified"):
        candidate(6, 0x43)
    with pytest.raises(ValueError, match="no certified"):
        candidate(4, 0x19 ^ 1)


@pytest.mark.parametrize("n,modulus,expected_ccx", [(4, 19, 9), (6, 73, 15)])
def test_every_basis_input_with_dirty_target(n, modulus, expected_ccx):
    raw, _terms = candidate(n, modulus)
    width, ops = parse(raw)
    assert width == 3 * n
    assert sum(op[0] == 49 for op in ops) == expected_ccx
    for a in range(1 << n):
        for b in range(1 << n):
            product = independent_product(a, b, n, modulus)
            for t in range(1 << n):
                src = a | (b << n) | (t << (2 * n))
                goal = a | (b << n) | ((t ^ product) << (2 * n))
                assert simulate(ops, src) == goal


def test_all_14_source_to_optimized_pairs(tmp_path):
    results = run(candidate_dir=tmp_path)
    assert results["case_count"] == results["target_reached_count"] == 14
    assert results["ccx_before"] == 240
    assert results["ccx_after"] == 168
    assert sum(item["saved_ccx"] for item in results["cases"]) == 72
    for item in results["cases"]:
        assert (tmp_path / item["candidate_file"]).is_file()


def test_adversarial_corruption_fails_closed(monkeypatch):
    from benchmarks import kaggle_bilinear_eval as audit

    original_digest = audit.PACKED_SHA256
    monkeypatch.setattr(audit, "PACKED_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        source_starts()
    monkeypatch.setattr(audit, "PACKED_SHA256", original_digest)
