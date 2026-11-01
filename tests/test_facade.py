"""``symq.verify`` routes each theorem to its owning engine and never weakens it."""
from __future__ import annotations

import pytest

from symq import Budget, Circuit, PhaseProgram, Verdict, verify


def _hmr_pair():
    reference = PhaseProgram(2, 1)
    candidate = PhaseProgram(2, 1).ccx(0, 1, 2)
    event = candidate.hmr(2)
    candidate.cz_if(event, 0, 1)
    return reference, candidate


def test_classical_theorem_returns_a_checked_witness():
    verdict = verify(Circuit(3), Circuit(3).ccx(0, 1, 2), theorem="classical_full",
                     engine="sparse")
    assert isinstance(verdict, Verdict)
    assert verdict.outcome == "different" and not verdict.equivalent
    assert Circuit(3).run(verdict.witness) != Circuit(3).ccx(0, 1, 2).run(verdict.witness)


def test_strict_branch_theorem():
    left = PhaseProgram(2, 0).cz(0, 1).cz(0, 1)
    verdict = verify(left, PhaseProgram(2, 0), theorem="sign_phase_exact",
                     engine="phase-reference", budget=Budget(max_seconds=10))
    assert verdict.equivalent and verdict.certified


def test_channel_theorem_goes_to_the_experimental_engine():
    reference, candidate = _hmr_pair()
    verdict = verify(reference, candidate, theorem="full_channel", engine="zdd",
                     budget=Budget(max_seconds=10))
    assert isinstance(verdict, Verdict)
    assert verdict.equivalent and verdict.theorem == "full_channel"


def test_a_contract_must_match_the_requested_theorem():
    from symq.experimental import VerificationContract

    reference, candidate = _hmr_pair()
    contract = VerificationContract(theorem="full_channel", backend="zdd")
    with pytest.raises(ValueError, match="different theorem"):
        verify(reference, candidate, theorem="full_channel", engine="hybrid-exact",
               contract=contract)


def test_unknown_theorems_are_refused():
    with pytest.raises(ValueError, match="unknown theorem"):
        verify(Circuit(1), Circuit(1), theorem="classical", engine="sparse")


def test_not_equivalent_is_not_a_proof_of_difference():
    """``equivalent`` and ``different`` are both False when nothing was decided."""
    from symq.experimental.contracts import VerificationResult
    from symq.verification import VerificationRecord

    circuit, toffoli = Circuit(3), Circuit(3).ccx(0, 1, 2)
    decided = {
        "equivalent": verify(circuit, circuit, theorem="classical_full", engine="sparse"),
        "different": verify(circuit, toffoli, theorem="classical_full", engine="sparse"),
        "inconclusive": verify(circuit, toffoli, theorem="classical_full", engine="zdd",
                               budget=Budget(max_nodes=1)),
    }
    for outcome, verdict in decided.items():
        assert verdict.outcome == outcome
        assert verdict.equivalent == (outcome == "equivalent")
        assert verdict.different == (outcome == "different")
    for cls in (VerificationRecord, VerificationResult):
        for outcome in ("inconclusive", "unsupported", "precondition_failed"):
            fields = {name: None for name in cls.__dataclass_fields__}
            fields.update(outcome=outcome)
            record = cls(**fields)
            assert not record.equivalent and not record.different and not record.certified


def test_different_is_part_of_the_verdict_protocol():
    class Partial:
        outcome = theorem = reason = "equivalent"
        witness = witness_kind = None
        equivalent = certified = True

    class Complete(Partial):
        different = False

    assert not isinstance(Partial(), Verdict)
    assert isinstance(Complete(), Verdict)
