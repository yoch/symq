"""Stacked integration qualification for #124 contextual SAT and #126 bilinear cores.

The checked theorem is classical basis-state equality under a proven cut
predicate; neither this test nor its cost weights certify HMR or T-count.
"""
from __future__ import annotations

import pytest

from symq import Budget, Circuit
from symq.generators import gf2n
from symq.labs.bilinear_substitution import apply_tower_substitution
from symq.labs.contextual_substitution import (
    GateWeights,
    SubstitutionContract,
    apply_verified_substitution,
    check_substitution,
)

pytestmark = pytest.mark.sat


def _case():
    # This is 13 wires: twelve data/output wires plus a truly clean scratch.
    # Both multiplier variants leave the scratch untouched.
    width = 13
    raw_original = gf2n.emit(4, gf2n.schoolbook(4)).circuit
    raw_replacement = gf2n.tower_multiplier(4, modulus=0x13)
    old = Circuit(width, list(raw_original.gates))
    new = Circuit(width, list(raw_replacement.gates))
    prefix = Circuit(width).cx(0, 12).cx(0, 12).cx(2, 7)
    suffix = Circuit(width).ccx(3, 4, 11).cx(11, 0)
    source = Circuit(width, prefix.gates + old.gates + suffix.gates)
    span = (len(prefix.gates), len(prefix.gates) + len(old.gates))
    domain = SubstitutionContract(initial_constants=((12, 0),), clean_at_cut=(12,))
    return source, span, new, domain


def test_rank_nine_substitution_has_real_cut_proof_replay_and_cost():
    source, span, replacement, contract = _case()
    weights = GateWeights(cx=1, ccx=12)
    result = check_substitution(
        source, span, replacement, contract=contract, weights=weights,
        budget=Budget(max_seconds=25),
    )
    assert result.equivalent, (result.outcome, result.reason)
    assert result.cost.weighted_delta < 0
    assert [r.name for r in result.obligations] == [
        "domain", "prefix", "interface", "suffix",
        "restore_original", "restore_candidate",
    ]
    assert all(r.status == "passed" for r in result.obligations)

    applied = apply_verified_substitution(
        result, source, span, replacement, contract=contract,
        budget=Budget(max_seconds=25),
    )
    assert applied.proof.certified
    assert applied.contract == contract
    assert applied.proof.candidate_sha256 == result.candidate_sha256
    final = applied.candidate.circuit()
    for state in range(1 << source.width):
        if not state & (1 << 12):
            assert final.run(state) == source.run(state)


def test_missing_cut_assumption_and_mutant_fail_closed():
    source, span, replacement, contract = _case()
    without_initial_preparation = SubstitutionContract(clean_at_cut=(12,))
    cut_failed = check_substitution(
        source, span, replacement, contract=without_initial_preparation,
        budget=Budget(max_seconds=25),
    )
    assert cut_failed.outcome == "precondition_failed"
    assert not cut_failed.certified

    changed = Circuit(replacement.width, list(replacement.gates))
    changed.cx(0, 12)  # violates the output and clean-scratch restoration
    failed = check_substitution(
        source, span, changed, contract=contract, budget=Budget(max_seconds=25),
    )
    assert not failed.certified and not failed.different
    assert failed.outcome == "not_proved"

    valid = check_substitution(
        source, span, replacement, contract=contract, budget=Budget(max_seconds=25)
    )
    assert valid.equivalent
    with pytest.raises(ValueError, match="receipt differs"):
        apply_verified_substitution(
            valid, source, span, changed, contract=contract,
            budget=Budget(max_seconds=25),
        )


def test_field_representation_swap_is_rejected():
    source, span, _replacement, contract = _case()
    # A second irreducible polynomial describes a different coefficient basis.
    wrong_basis = Circuit(13, gf2n.tower_multiplier(4, modulus=0x19).gates)
    result = check_substitution(
        source, span, wrong_basis, contract=contract,
        budget=Budget(max_seconds=25),
    )
    assert not result.equivalent
    assert result.outcome == "not_proved"


def test_one_call_application_reproves_and_observes_declared_cost_model():
    source, span, _replacement, contract = _case()
    application = apply_tower_substitution(
        source, span, n=4, modulus=0x13, wires=tuple(range(12)),
        contract=contract, weights=GateWeights(cx=1, ccx=12),
        budget=Budget(max_seconds=25),
    )
    assert application.proof.certified
    assert application.proof.cost.weighted_delta < 0
    assert application.contract == contract
    for state in range(1 << 13):
        if not state & (1 << 12):
            assert source.run(state) == application.candidate.circuit().run(state)


def test_one_call_api_refuses_bad_mapping_basis_and_no_savings():
    source, span, _replacement, contract = _case()
    kwargs = {
        "contract": contract,
        "weights": GateWeights(cx=1, ccx=12),
        "budget": Budget(max_seconds=25),
    }
    with pytest.raises(ValueError, match="wires"):
        apply_tower_substitution(
            source, span, n=4, modulus=0x13,
            wires=tuple(list(range(11)) + [10]), **kwargs,
        )
    with pytest.raises(ValueError, match="not proved"):
        apply_tower_substitution(
            source, span, n=4, modulus=0x19,
            wires=tuple(range(12)), **kwargs,
        )
    with pytest.raises(ValueError, match="no saving"):
        apply_tower_substitution(
            source, span, n=4, modulus=0x13, wires=tuple(range(12)),
            contract=contract, weights=GateWeights(cx=1, ccx=1),
            budget=Budget(max_seconds=25),
        )
