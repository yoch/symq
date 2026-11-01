"""Rewrites and channels checked against the independent Kraus-trajectory oracle.

The oracle (``tests/testkit/kraus_oracle.py``) does not use the library's density-matrix
evolution; ``coherence_image`` is imported only to cross-check it.
"""
from __future__ import annotations

from itertools import product

from testkit.kraus_oracle import independent_kraus

from symq.experimental.hybrid import HOp, HybridProgram, coherence_image


def test_temporary_and_measurement_uncompute_independent_all_coherences():
    reference = HybridProgram(3, 1, [
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("ccx", (0, 1, 3)),
    ])
    candidate = HybridProgram(3, 1, [
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("hmr", (3,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ])
    mutant = HybridProgram(3, 1, candidate.ops[:-1])
    equal, off_diagonal_mutant = 0, False
    for x, y in product(range(1 << 3), repeat=2):
        expected = independent_kraus(reference, x, y)
        actual = independent_kraus(candidate, x, y)
        assert expected == actual
        # Independent trajectory oracle agrees with the installed density oracle.
        assert expected[()] == coherence_image(reference, x, y)
        assert actual[()] == coherence_image(candidate, x, y)
        wrong = independent_kraus(mutant, x, y)
        if x == y:
            assert wrong == expected
        elif wrong != expected:
            off_diagonal_mutant = True
        equal += 1
    assert equal == 64 and off_diagonal_mutant


def test_real_public_qualtran_m1_independent_channel_and_phase_mutant():
    from benchmarks.hmr_qualification import hybrid, load_manifest, programs

    cases = {c["id"]: c for c in load_manifest()["cases"]}
    reference, candidate = (hybrid(p) for p in programs(cases["m1-full-none"]))
    _, missing = (hybrid(p) for p in programs(cases["m1-full-missing_correction"]))
    assert reference.data == candidate.data == missing.data == 2
    off_diagonal_mutant = False
    for x, y in product(range(1 << 2), repeat=2):
        image = independent_kraus(reference, x, y)
        assert image == independent_kraus(candidate, x, y)
        assert image[()] == coherence_image(reference, x, y)
        bad = independent_kraus(missing, x, y)
        if x == y:
            assert image == bad
        elif image != bad:
            off_diagonal_mutant = True
    assert off_diagonal_mutant


def test_independent_full_coherent_oracle_exposes_borrowed_phase_error():
    identity = HybridProgram(2)
    dirty = HybridProgram(2, 0, [HOp("cz", (0, 1))])
    assert all(
        independent_kraus(dirty, x, x) == independent_kraus(identity, x, x)
        for x in range(4)
    )
    assert independent_kraus(dirty, 3, 1) != independent_kraus(identity, 3, 1)


def test_independent_oracle_distinguishes_observed_instrument_and_liveness():
    operations = (
        HOp("reset", (1,)), HOp("measure_z", (1,), slot="b0"),
    )
    reference = HybridProgram(2, 0, list(operations))
    inverted = HybridProgram(2, 0, list(operations) + [HOp("invert", slot="b0")])
    # If the record is forgotten and never used again, channels are equal.
    for x, y in product(range(4), repeat=2):
        assert independent_kraus(reference, x, y) == independent_kraus(inverted, x, y)
    # If b0 is observed, the instruments are not equivalent.
    assert independent_kraus(reference, 0, 0, ("b0",)) != independent_kraus(
        inverted, 0, 0, ("b0",)
    )
    # If b0 drives a later X, even the unconditional channels differ.
    suffix = [HOp("x", (0,), condition="b0")]
    left = HybridProgram(2, 0, list(operations) + suffix)
    right = HybridProgram(2, 0, list(inverted.ops) + suffix)
    assert independent_kraus(left, 0, 0) != independent_kraus(right, 0, 0)


def test_independent_kraus_covers_reset_measurement_swap_and_signs():
    programs = (
        HybridProgram(2, 1, [
            HOp("cx", (0, 2)), HOp("measure_z", (2,), slot="b0"),
            HOp("x", (1,), condition="!b0"), HOp("reset", (2,)),
        ]),
        HybridProgram(2, 1, [
            HOp("cswap", (2, 0, 1)), HOp("x", (2,)),
            HOp("swap", (0, 1)), HOp("ccz", (0, 1, 2)),
            HOp("hmr", (2,), slot="b0"), HOp("cz", (0, 1), condition="b0"),
        ]),
        HybridProgram(2, 0, [
            HOp("store", slot="b0", value=1), HOp("invert", slot="b0"),
            HOp("oxor", slot="b0", source="b0"), HOp("neg"),
            HOp("z", (0,)), HOp("cz", (0, 1), condition="!b0"),
        ]),
    )
    for program in programs:
        for x, y in product(range(1 << program.data), repeat=2):
            exact = independent_kraus(program, x, y)
            assert exact.get((), {}) == coherence_image(program, x, y)



def test_global_contextual_hmr_application_against_independent_choi_basis():
    """A complete connected 4-wire circuit, not just an isolated leaf lemma."""
    from symq.labs.channel_composition import HybridFragment
    from symq.labs.hybrid_substitution import check_hybrid_substitution

    prefix = (
        HOp("cx", (0, 1)), HOp("cx", (1, 2)),
    )
    reference = (
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("ccx", (0, 1, 3)),
    )
    candidate = (
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("hmr", (3,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    )
    suffix = (HOp("cx", (2, 0)), HOp("z", (1,)))
    source = HybridProgram(3, 1, list(prefix + reference + suffix))
    insert = (len(prefix), len(prefix) + len(reference))
    replacement = HybridFragment(4, candidate)
    receipt = check_hybrid_substitution(
        source, insert, replacement, wires=(0, 1, 2, 3), clean=(3,),
    )
    assert receipt.equivalent and receipt.candidate is not None
    whole_candidate = receipt.candidate.to_program()
    assert len(whole_candidate.ops) == len(prefix) + len(candidate) + len(suffix)

    wrong = HybridProgram(
        3, 1, list(prefix + candidate[:-1] + suffix),
    )
    offdiagonal_error = False
    for x, y in product(range(1 << 3), repeat=2):
        oracle_left = independent_kraus(source, x, y)
        oracle_right = independent_kraus(whole_candidate, x, y)
        assert oracle_left == oracle_right
        wrong_image = independent_kraus(wrong, x, y)
        if x == y:
            assert wrong_image == oracle_left
        elif wrong_image != oracle_left:
            offdiagonal_error = True
    assert offdiagonal_error
