"""The public bilinear KMB corpus: provenance, codec, and exact tower-multiplier rewrites."""
from __future__ import annotations

import pytest

from benchmarks import bilinear_kmb
from benchmarks.kmb import decode, encode
from symq import ANF, Circuit, make_algebra, simulate
from symq.generators.gf2n import tensor, tower_multiplier
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution


def test_the_corpus_matches_its_pinned_manifest_and_files():
    rows = bilinear_kmb.manifest()
    starts = bilinear_kmb.source_starts()
    assert len(rows) == len(starts) == 14
    assert {row["modulus"] for row in rows} == {0x13, 0x49}


def test_every_source_file_round_trips_through_the_codec():
    for raw in bilinear_kmb.source_starts().values():
        circuit = decode(raw)
        assert decode(encode(circuit)).gates == circuit.gates


@pytest.mark.parametrize(("n", "modulus"), [(4, 0x13), (6, 0x49)])
def test_the_candidate_computes_the_field_tensor_of_the_dataset_basis(n, modulus):
    algebra = make_algebra("packed", 3 * n)
    outputs = [algebra.to_anf(v) for v in simulate(tower_multiplier(n, modulus=modulus), algebra)]
    table = tensor(n, modulus=modulus)
    for k in range(n):
        monomials = {1 << (2 * n + k)} | {(1 << i) | (1 << (n + j)) for i in range(n)
                                          for j in range(n) if table[i][j] >> k & 1}
        assert outputs[2 * n + k] == ANF(frozenset(monomials))


def test_all_14_rewrites_are_proved_and_priced():
    report = bilinear_kmb.run()
    assert all(row["outcome"] == "equivalent" for row in report["cases"])
    assert all(row["candidate_ccx"] == row["known_bilinear_target"] for row in report["cases"])
    assert report["totals"] == {"source_ccx": 240, "source_cx": 1862,
                                "candidate_ccx": 168, "candidate_cx": 784}
    assert not report["receipt"]["symq_location"].startswith("/")


def test_a_wrong_basis_or_a_dropped_product_is_not_proved():
    row = next(r for r in bilinear_kmb.manifest() if r["modulus"] == 0x49)
    source = decode(bilinear_kmb.source_starts()[row["kmb"]])
    span = (0, len(source.gates))
    other_basis = tower_multiplier(6, modulus=0x43)
    assert check_substitution(source, span, other_basis, contract=SubstitutionContract(),
                              engine="packed").outcome == "not_proved"
    good = tower_multiplier(6, modulus=0x49)
    dropped = list(good.gates)
    dropped.remove(next(g for g in dropped if g.name == "ccx"))
    assert check_substitution(source, span, Circuit(18, dropped), contract=SubstitutionContract(),
                              engine="packed").outcome == "not_proved"


def test_corrupted_bytes_are_refused():
    raw = next(iter(bilinear_kmb.source_starts().values()))
    for bad in (raw[:50], b"\x00" * 16 + raw[16:], raw + b"\x00"):
        with pytest.raises(ValueError):
            decode(bad)
    with pytest.raises(ValueError, match="CX/CCX"):
        encode(Circuit(6).mcx(0, 1, 2, 3))
