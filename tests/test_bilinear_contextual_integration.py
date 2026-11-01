"""Tower-multiplier rewrite proved at a real cut whose clean scratch the replacement relies on.

The checked theorem is classical basis-state equality under a proven cut predicate; neither this
test nor its declared weights certify HMR behaviour or a T-count.
"""
from __future__ import annotations

import pytest

from symq import Budget, Circuit
from symq.generators import gf2n
from symq.labs.bilinear_substitution import apply_tower_substitution, mapped_tower_multiplier
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.rewrite import ReceiptMismatch, Weights

pytestmark = pytest.mark.sat
WEIGHTS = Weights.from_mapping({"cx": 1, "ccx": 12})
SCRATCH = 12


def _case():
    """13 wires: a GF(16) schoolbook multiplier on 0..11 and a scratch wire 12.

    The prefix computes and uncomputes into the scratch, so only the declared initial constant
    makes it clean at the cut. The replacement adds ``ccx(12, 1, 8)``, the identity exactly when
    the scratch is 0: it is correct only under the cut contract.
    """
    width = 13
    old = Circuit(width, list(gf2n.emit(4, gf2n.schoolbook(4)).circuit.gates))
    new = Circuit(width, list(gf2n.tower_multiplier(4, modulus=0x13).gates)).ccx(SCRATCH, 1, 8)
    prefix = Circuit(width).cx(0, SCRATCH).cx(0, SCRATCH).cx(2, 7)
    suffix = Circuit(width).ccx(3, 4, 11).cx(11, 0)
    source = Circuit(width, prefix.gates + old.gates + suffix.gates)
    span = (len(prefix.gates), len(prefix.gates) + len(old.gates))
    contract = SubstitutionContract(initial_constants=((SCRATCH, 0),), clean_at_cut=(SCRATCH,))
    return source, span, new, contract


def _rewritten(source, span, replacement):
    return Circuit(source.width, source.gates[:span[0]] + replacement.gates
                   + source.gates[span[1]:])


def test_the_contract_is_needed_and_the_rewrite_is_proved_under_it():
    source, span, replacement, contract = _case()
    candidate = _rewritten(source, span, replacement)
    clean = [s for s in range(1 << 13) if not s >> SCRATCH & 1]
    dirty = [s for s in range(1 << 13) if s >> SCRATCH & 1]
    assert all(candidate.run(s) == source.run(s) for s in clean)
    assert any(candidate.run(s) != source.run(s) for s in dirty)  # the contract matters

    result = check_substitution(source, span, replacement, contract=contract, weights=WEIGHTS,
                                budget=Budget(max_seconds=25))
    assert result.equivalent, (result.outcome, result.reason)
    assert result.cost.weighted_delta < 0
    assert [r.name for r in result.obligations] == [
        "domain", "prefix", "interface", "suffix", "restore_original", "restore_candidate"]
    final = result.candidate.circuit()
    assert all(final.run(s) == source.run(s) for s in clean)


def test_without_the_initial_constant_the_cut_is_not_established():
    source, span, replacement, _contract = _case()
    result = check_substitution(source, span, replacement,
                                contract=SubstitutionContract(clean_at_cut=(SCRATCH,)),
                                budget=Budget(max_seconds=25))
    assert result.outcome == "precondition_failed" and result.candidate is None


def test_a_wrong_basis_or_a_scratch_leak_is_not_proved():
    source, span, replacement, contract = _case()
    leaking = Circuit(13, list(replacement.gates)).cx(0, SCRATCH)
    for bad in (Circuit(13, gf2n.tower_multiplier(4, modulus=0x19).gates), leaking):
        result = check_substitution(source, span, bad, contract=contract,
                                    budget=Budget(max_seconds=25))
        assert result.outcome == "not_proved" and not result.different


def test_receipts_bind_the_replacement():
    source, span, replacement, contract = _case()
    from symq.labs.contextual_substitution import replay_substitution

    valid = check_substitution(source, span, replacement, contract=contract,
                               budget=Budget(max_seconds=25))
    with pytest.raises(ReceiptMismatch):
        replay_substitution(valid, source, span, Circuit(13, list(replacement.gates)).x(0),
                            contract=contract)


def test_one_call_tower_rewrite_and_its_cost_policy():
    source, span, _replacement, contract = _case()
    kwargs = {"contract": contract, "budget": Budget(max_seconds=25)}
    applied = apply_tower_substitution(source, span, n=4, modulus=0x13,
                                       wires=tuple(range(12)), weights=WEIGHTS, **kwargs)
    assert applied.equivalent and applied.candidate is not None
    assert applied.cost.weighted_delta < 0
    with pytest.raises(ValueError, match="wires"):
        mapped_tower_multiplier(13, 4, 0x13, tuple(list(range(11)) + [10]))
    wrong = apply_tower_substitution(source, span, n=4, modulus=0x19,
                                     wires=tuple(range(12)), weights=WEIGHTS, **kwargs)
    assert wrong.outcome == "not_proved" and wrong.candidate is None
    flat = apply_tower_substitution(source, span, n=4, modulus=0x13, wires=tuple(range(12)),
                                    weights=Weights(), **kwargs)
    assert flat.equivalent and flat.candidate is None and "no saving" in flat.reason
