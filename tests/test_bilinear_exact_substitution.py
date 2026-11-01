"""Adversarial tests for exact 72-wire bilinear cut proof and frozen replay."""
from __future__ import annotations

import random
from dataclasses import replace

import pytest

from symq import Budget, Circuit
from symq.circuit import Gate
from symq.errors import ResourceLimitExceeded
from symq.generators import gf2n
from symq.labs.bilinear_exact_substitution import (
    BilinearProofFailure,
    BilinearWeights,
    apply_bilinear_substitution,
    check_bilinear_substitution,
    optimize_gf24_substitution,
)
from symq.labs.gf24_schedule import pinned_gf24_emitted
from symq.labs.gf24_tower import GF24_MODULUS


def _embed(block: Circuit, width: int, wires: tuple[int, ...]) -> Circuit:
    return Circuit(
        width, [
            Gate(g.name, tuple(wires[i] for i in g.qubits))
            for g in block.gates
        ],
    )


def _gf24_case():
    width = 78
    wires = tuple(range(2, 74))
    source_block = _embed(
        gf2n.emit(24, gf2n.karatsuba(24), strategy="pivot-scheduled").circuit,
        width, wires,
    )
    candidate = _embed(
        pinned_gf24_emitted().circuit,
        width, wires,
    )
    prefix = Circuit(width).cx(0, wires[0]).ccx(wires[1], 1, 77)
    suffix = Circuit(width).cx(wires[71], 0).mcx(2, 3, 74, 77)
    source = Circuit(width, prefix.gates + source_block.gates + suffix.gates)
    span = (len(prefix.gates), len(prefix.gates) + len(source_block.gates))
    return source, span, candidate, wires


def _gf16_case():
    width = 16
    wires = (2, 3, 4, 5, 8, 9, 10, 11, 13, 14, 0, 1)
    reference = _embed(gf2n.emit(4, gf2n.schoolbook(4)).circuit, width, wires)
    candidate = _embed(gf2n.tower_multiplier(4, modulus=0x13), width, wires)
    prefix = Circuit(width).cx(15, 2).cx(1, 12)
    suffix = Circuit(width).ccx(0, 15, 12).cx(4, 5)
    full = Circuit(width, prefix.gates + reference.gates + suffix.gates)
    return full, (len(prefix.gates), len(prefix.gates) + len(reference.gates)), candidate, wires


def _gf24_proof():
    source, span, candidate, wires = _gf24_case()
    proof = check_bilinear_substitution(
        source, span, candidate,
        n=24, modulus=GF24_MODULUS, wires=wires,
        weights=BilinearWeights(ccx=32, cx=1),
        budget=Budget(max_seconds=25),
    )
    return source, span, candidate, wires, proof


def test_exact_gf24_with_larger_unrestricted_context():
    source, span, candidate, _wires, proof = _gf24_proof()
    assert proof.equivalent
    assert proof.theorem == "exact_total_bilinear_permutation_unitary_v1"
    assert (proof.reference_ccx, proof.reference_cx) == (162, 1856)
    assert (proof.replacement_ccx, proof.replacement_cx) == (99, 2634)
    assert proof.weighted_delta == (99 * 32 + 2634) - (162 * 32 + 1856) == -1238
    assert proof.source_sha256 != proof.candidate_sha256
    assert len(proof.tensor_sha256) == 64

    application = apply_bilinear_substitution(
        proof, source, span, candidate, budget=Budget(max_seconds=25)
    )
    assert application.candidate.width == source.width
    assert application.proof == proof
    assert application.proof.candidate_sha256 == proof.candidate_sha256

    # Independent whole-stream execution exercises arbitrary dirty Z, extra
    # context wires, a non-identity prefix, and a nontrivial common suffix.
    rng = random.Random(0xABCD24)
    for x in (0, (1 << 78) - 1, 1 << 2, (1 << 78) - 1 ^ (1 << 53)):
        assert application.candidate.circuit().run(x) == source.run(x)
    for _ in range(40):
        x = rng.randrange(1 << source.width)
        assert application.candidate.circuit().run(x) == source.run(x)


def test_gf16_exhaustive_16_wire_context_and_reversed_ccx_controls():
    source, span, candidate, wires = _gf16_case()
    # CCX control ordering is arbitrary: A/B may be swapped.
    changed = Circuit(candidate.width, [
        Gate("ccx", (g.qubits[1], g.qubits[0], g.qubits[2]))
        if g.name == "ccx" else g
        for g in candidate.gates
    ])
    weights = BilinearWeights(cx=1, ccx=32)
    receipt = check_bilinear_substitution(
        source, span, changed, n=4, modulus=0x13, wires=wires, weights=weights
    )
    applied = apply_bilinear_substitution(receipt, source, span, changed)
    for x in range(1 << source.width):
        assert source.run(x) == applied.candidate.circuit().run(x)


@pytest.mark.parametrize("kind", [
    "delete_ccx", "extra_cx", "cross_a_b_cx", "unsupported_x",
    "unsupported_mcx", "nonlocal_cx", "bad_output_target",
])
def test_structural_and_tensor_mutants_fail_closed(kind):
    source, span, candidate, wires = _gf24_case()
    mutated = Circuit(candidate.width, list(candidate.gates))
    if kind == "delete_ccx":
        index = next(i for i, g in enumerate(mutated.gates) if g.name == "ccx")
        del mutated.gates[index]
    elif kind == "extra_cx":
        mutated.cx(wires[0], wires[1])  # unrestored A frame
    elif kind == "cross_a_b_cx":
        mutated.cx(wires[0], wires[24])  # forbidden cross-register control
    elif kind == "unsupported_x":
        mutated.x(wires[0])
    elif kind == "unsupported_mcx":
        mutated.mcx(wires[0], wires[24], wires[48])
    elif kind == "nonlocal_cx":
        mutated.cx(0, wires[0])  # external wire inside replacement
    elif kind == "bad_output_target":
        mutated.ccx(wires[0], wires[24], wires[2])
    with pytest.raises(BilinearProofFailure):
        check_bilinear_substitution(
            source, span, mutated, n=24, modulus=GF24_MODULUS,
            wires=wires, weights=BilinearWeights(ccx=32, cx=1),
        )


def test_exact_certificate_cannot_authorize_stale_or_forged_source():
    source, span, candidate, _wires, proof = _gf24_proof()
    forged = replace(proof, weighted_delta=-99999)
    with pytest.raises(ValueError, match="receipt differs"):
        apply_bilinear_substitution(forged, source, span, candidate)
    mutated_source = Circuit(source.width, list(source.gates)).cx(0, 75)
    with pytest.raises(ValueError, match="receipt differs"):
        apply_bilinear_substitution(proof, mutated_source, span, candidate)
    mutated_candidate = Circuit(candidate.width, list(candidate.gates)).cx(75, 76)
    with pytest.raises(BilinearProofFailure):
        apply_bilinear_substitution(proof, source, span, mutated_candidate)
    with pytest.raises(ValueError):
        apply_bilinear_substitution(proof, source, (span[0] + 1, span[1]), candidate)
    with pytest.raises(ValueError, match="unsupported proof theorem"):
        apply_bilinear_substitution(replace(proof, theorem="fake"), source, span, candidate)
    with pytest.raises(TypeError, match="typed"):
        apply_bilinear_substitution(proof.__dict__, source, span, candidate)


def test_wrong_polynomial_and_bad_mapping_rejected():
    source, span, candidate, wires = _gf24_case()
    options = {"n": 24, "modulus": GF24_MODULUS,
               "wires": wires, "weights": BilinearWeights(ccx=32, cx=1)}
    with pytest.raises(ValueError, match="modulus"):
        check_bilinear_substitution(
            source, span, candidate, **{**options, "modulus": GF24_MODULUS ^ 1}
        )
    with pytest.raises(ValueError, match="wires"):
        check_bilinear_substitution(
            source, span, candidate, **{**options, "wires": wires[:-1] + (wires[-2],)}
        )
    with pytest.raises(BilinearProofFailure):
        changed = (wires[1], wires[0], *wires[2:])
        check_bilinear_substitution(
            source, span, candidate, **{**options, "wires": changed}
        )
    with pytest.raises(ValueError, match="span"):
        check_bilinear_substitution(
            source, (span[0], span[0]), candidate, **options
        )


def test_cost_policy_and_bounded_qualifier():
    source, span, candidate, wires = _gf16_case()
    weights = BilinearWeights(ccx=1, cx=1)
    p = check_bilinear_substitution(
        source, span, candidate, n=4, modulus=0x13, wires=wires, weights=weights
    )
    assert p.weighted_delta > 0
    with pytest.raises(ValueError, match="not cheaper"):
        apply_bilinear_substitution(p, source, span, candidate)
    allowed = apply_bilinear_substitution(
        p, source, span, candidate, require_saving=False
    )
    assert allowed.proof == p
    with pytest.raises(ValueError, match="more than"):
        check_bilinear_substitution(
            source, span, candidate, n=4, modulus=0x13, wires=wires,
            weights=weights, max_block_gates=1,
        )
    with pytest.raises(ValueError, match="width exceeds"):
        check_bilinear_substitution(
            source, span, candidate, n=4, modulus=0x13, wires=wires,
            weights=weights, max_global_width=15,
        )
    with pytest.raises(ResourceLimitExceeded):
        check_bilinear_substitution(
            source, span, candidate, n=4, modulus=0x13, wires=wires,
            weights=weights, budget=Budget(max_seconds=1e-12),
        )
    with pytest.raises(ValueError, match="only enforces"):
        check_bilinear_substitution(
            source, span, candidate, n=4, modulus=0x13, wires=wires,
            weights=weights, budget=Budget(max_nodes=100),
        )


@pytest.mark.parametrize("bad", [
    (True, 1), (1.5, 2), (1, True), (-1, 2), (0, 0), (1, -3),
])
def test_bad_declared_cost_weights(bad):
    with pytest.raises(ValueError, match="weights"):
        BilinearWeights(ccx=bad[0], cx=bad[1])



def test_auto_choose_and_prove_with_nonidentity_global_wires():
    source, span, _candidate, wires = _gf24_case()
    method, applied = optimize_gf24_substitution(
        source, span, wires=wires, weights=BilinearWeights(ccx=32, cx=1),
        budget=Budget(max_seconds=25),
    )
    assert method == "tower-99-pinned-order"
    assert applied.proof.equivalent
    assert (applied.proof.replacement_ccx, applied.proof.replacement_cx) == (99, 2634)
    assert applied.proof.weighted_delta == -1238
    rng = random.Random(0xFEED24)
    candidate = applied.candidate.circuit()
    for _ in range(40):
        x = rng.getrandbits(source.width)
        assert candidate.run(x) == source.run(x)


def test_auto_choose_obeys_declared_weights_and_fail_closed_policy():
    source, span, candidate, wires = _gf24_case()
    # For a Karatsuba source and very expensive CNOTs, schoolbook becomes
    # the cheapest valid, *profitable* declared alternative.
    method, applied = optimize_gf24_substitution(
        source, span, wires=wires, weights=BilinearWeights(ccx=1, cx=100),
        budget=Budget(max_seconds=25),
    )
    assert method == "schoolbook-incidence"
    assert applied.proof.equivalent
    assert applied.proof.weighted_delta < 0

    # When source already uses the selected tower method, a second rewrite
    # has zero saving and must fail closed unless explicitly permitted.
    same = Circuit(
        source.width,
        source.gates[:span[0]] + candidate.gates + source.gates[span[1]:],
    )
    same_span = (span[0], span[0] + len(candidate.gates))
    with pytest.raises(ValueError, match="not cheaper"):
        optimize_gf24_substitution(
            same, same_span, wires=wires, weights=BilinearWeights(ccx=32, cx=1),
            budget=Budget(max_seconds=25),
        )
    unchanged_method, unchanged = optimize_gf24_substitution(
        same, same_span, wires=wires, weights=BilinearWeights(ccx=32, cx=1),
        budget=Budget(max_seconds=25), require_saving=False,
    )
    assert unchanged_method == "tower-99-pinned-order"
    assert unchanged.proof.equivalent
    assert unchanged.proof.weighted_delta == 0
    with pytest.raises(ValueError, match="wires"):
        optimize_gf24_substitution(
            source, span, wires=wires[:-1] + (wires[-2],),
            weights=BilinearWeights(ccx=32, cx=1),
        )
