"""Independent small coherent-oracle regression for affine reset analysis."""
from __future__ import annotations

import random

import pytest

from symq.experimental.hybrid import HybridProgram, coherence_image
from symq.labs.reset_support import (
    AffineSupport,
    build_clean_reset_candidate,
    prove_clean_resets,
)
from symq.resources import Budget


def _without_resets(program: HybridProgram) -> HybridProgram:
    return HybridProgram(program.data, program.ancillas,
                         [op for op in program.ops if op.kind != "reset"])


def test_clean_reset_is_identity_on_every_legal_matrix_unit():
    p = (HybridProgram(2, 1).cx(0, 2).cx(0, 2).z(1)
         .reset(2).cz(0, 1).reset(2))
    support = AffineSupport(3, 0, (1, 2))
    report = prove_clean_resets(p, support)
    assert report["status"] == "proved_clean"
    assert [s["index"] for s in report["resets"]] == [3, 5]
    assert all(s["status"] == "proved_clean" for s in report["resets"])
    for x in range(1 << p.data):
        for y in range(1 << p.data):
            assert coherence_image(p, x, y) == coherence_image(_without_resets(p), x, y)


def test_nonclean_basis_witness_replays_and_coherent_channel_changes():
    p = HybridProgram(1, 1).cx(0, 1).reset(1)
    report = prove_clean_resets(p, AffineSupport(2, 0, (1,)))
    assert report["status"] == "not_proved"
    assert report["obligation"] == "nonclean_reset"
    witness = report["resets"][0]
    assert witness["status"] == "proved_nonclean"
    assert witness["input"] == 1
    assert coherence_image(p, 1, 1) != coherence_image(_without_resets(p), 1, 1)


def test_phase_diagonals_preserve_cleanliness_but_no_phase_equivalence_claim():
    p = HybridProgram(2, 1).z(0).cz(0, 1).ccz(0, 1, 2).neg().reset(2)
    report = prove_clean_resets(p, AffineSupport(3, 0, (1, 2)))
    assert report["status"] == "proved_clean"
    assert report["proof_kind"] == "affine_anf_reversible_prefix_reset_identity"
    assert not report["portable_certificate"]
    for x in range(4):
        for y in range(4):
            assert coherence_image(p, x, y) == coherence_image(_without_resets(p), x, y)


def test_correlated_affine_domain_and_nonclean_mutation():
    # q2 is q0 XOR q1 on the legal support, not a free independent target.
    support = AffineSupport(3, 0, (0b101, 0b110))
    p = HybridProgram(3).cx(0, 2).cx(1, 2).reset(2)
    report = prove_clean_resets(p, support)
    assert report["status"] == "proved_clean"
    for u in range(4):
        x = support.input_at(u)
        for v in range(4):
            y = support.input_at(v)
            assert coherence_image(p, x, y) == coherence_image(_without_resets(p), x, y)
    p = HybridProgram(3).cx(0, 2).reset(2)
    other = prove_clean_resets(p, support)
    assert other["status"] == "not_proved"
    value = other["resets"][0]["input"]
    assert (value >> 2 ^ value >> 0) & 1
    assert coherence_image(p, value, value) != coherence_image(
        _without_resets(p), value, value
    )


def test_research_40_wires_rank35_89_clean_resets_without_enumeration():
    p = HybridProgram(40)
    for _ in range(89):
        p.reset(39)
    support = AffineSupport(40, 0, tuple(1 << bit for bit in range(35)))
    report = prove_clean_resets(p, support)
    assert report["status"] == "proved_clean"
    assert report["checked_resets"] == 89
    assert report["peak_terms"] == 35
    assert report["products"] == 0
    p = HybridProgram(40).cx(0, 39).reset(39)
    bad = prove_clean_resets(p, support)
    assert bad["status"] == "not_proved"
    assert bad["resets"][0]["input"] == 1
    # This is a *synthetic* test shape and not a real 89-reset loader certificate.


def test_malformed_affine_input_fails_closed_and_resource_limit_is_inconclusive():
    p = HybridProgram(2).reset(1)
    for domain in (
        AffineSupport(2, 0, (1, 1)),
        AffineSupport(2, 0, (0,)),
        AffineSupport(2, 4, (1,)),
        AffineSupport(2, 0, (1, 3, 2)),
    ):
        with pytest.raises(ValueError):
            prove_clean_resets(p, domain)
    with pytest.raises(ValueError, match="ancillas"):
        prove_clean_resets(HybridProgram(1, 1).reset(1), AffineSupport(2, 2, (1,)))
    with pytest.raises(ValueError, match="node/byte"):
        prove_clean_resets(p, AffineSupport(2, 0, (1,)),
                           budget=Budget(max_nodes=1))
    large = prove_clean_resets(HybridProgram(2).cx(0, 1).reset(1),
                               AffineSupport(2, 0, (1, 2)),
                               budget=Budget(max_terms=1))
    assert large["status"] == "inconclusive"


def test_measurement_and_feedforward_refused_as_unsupported():
    for p in (
        HybridProgram(2).measure_z(0, "b0").reset(1),
        HybridProgram(2).hmr(0, "b0").reset(1),
        HybridProgram(2).store("b0", 0).x(0, condition="b0").reset(1),
    ):
        r = prove_clean_resets(p, AffineSupport(2, 0, (1, 2)))
        assert r["status"] == "unsupported"
        assert r["checked_resets"] == 0


def test_random_basis_and_coherent_differential():
    rng = random.Random(20261103)
    for width in (2, 3, 4):
        support = AffineSupport(width, 0, tuple(1 << q for q in range(width)))
        for _ in range(25):
            p = HybridProgram(width)
            for _ in range(5):
                choice = rng.randrange(6)
                q = rng.randrange(width)
                if choice == 0:
                    p.x(q)
                elif choice == 1:
                    p.z(q)
                elif choice == 2:
                    c = (q + 1) % width
                    p.cx(c, q)
                elif choice == 3:
                    c = (q + 1) % width
                    p.cz(c, q)
                elif choice == 4:
                    p.swap(q, (q + 1) % width)
                elif width >= 3:
                    other = (q + 1) % width
                    p.ccx(other, (q + 2) % width, q)
            target = rng.randrange(width)
            p.reset(target)
            report = prove_clean_resets(p, support)
            assert report["status"] in {"not_proved", "proved_clean"}
            equal = all(
                coherence_image(p, x, y) == coherence_image(_without_resets(p), x, y)
                for x in range(1 << width)
                for y in range(1 << width)
            )
            assert (report["status"] == "proved_clean") == equal
            if not equal:
                witness = report["resets"][0]["input"]
                assert coherence_image(p, witness, witness) != coherence_image(
                    _without_resets(p), witness, witness
                )


def test_candidate_is_emitted_only_with_fresh_complete_reset_identity():
    original = HybridProgram(2, 1).cx(0, 2).cx(0, 2).reset(2).reset(2)
    reference = HybridProgram(
        original.data, original.ancillas, list(original.ops)
    )
    candidate, proof = build_clean_reset_candidate(
        original, AffineSupport(3, 0, (1, 2))
    )
    assert proof["status"] == "proved_clean"
    assert proof["checked_resets"] == 2
    assert candidate is not None
    assert not any(op.kind == "reset" for op in candidate.ops)
    for x in range(1 << original.data):
        for y in range(1 << original.data):
            assert coherence_image(reference, x, y) == coherence_image(candidate, x, y)
    # Mutating the caller-owned original after the proof cannot change
    # the candidate's frozen stream.
    original.x(1)
    assert candidate.ops != original.ops
    for x in range(1 << reference.data):
        for y in range(1 << reference.data):
            assert coherence_image(reference, x, y) == coherence_image(candidate, x, y)


def test_nonclean_unsupported_or_budget_limited_source_never_emits_candidate():
    support = AffineSupport(2, 0, (1,))
    bad = HybridProgram(1, 1).cx(0, 1).reset(1)
    candidate, report = build_clean_reset_candidate(bad, support)
    assert candidate is None and report["status"] == "not_proved"
    assert report["resets"][0]["input"] == 1

    measured = HybridProgram(1, 1).measure_z(0, "b0").reset(1)
    candidate, report = build_clean_reset_candidate(measured, support)
    assert candidate is None and report["status"] == "unsupported"

    exhausted = HybridProgram(2, 1).reset(2)
    candidate, report = build_clean_reset_candidate(
        exhausted, AffineSupport(3, 0, (1, 2)),
        budget=Budget(max_terms=1),
    )
    assert candidate is None and report["status"] == "inconclusive"
