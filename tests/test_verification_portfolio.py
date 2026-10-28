"""Safety and exact-theorem regression for the opt-in explicit verification facade."""

import pytest

from symq import Budget, Circuit, UnsupportedOperation
from symq.phase import PhaseProgram
from symq.sat import Contract, SatUnavailable, available
from symq.verification import THEOREMS, verify_explicit


def test_full_classical_reports_replayable_witness_and_digests():
    reference = Circuit(3)
    good = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    bad = Circuit(3).ccx(0, 1, 2)
    passed = verify_explicit(reference, good, theorem="classical_full", engine="sparse")
    failed = verify_explicit(reference, bad, theorem="classical_full", engine="sparse")
    assert passed.certified and passed.outcome == "equivalent"
    assert not failed.certified and failed.outcome == "different"
    assert failed.witness_kind == "input"
    assert reference.run(failed.witness) != bad.run(failed.witness)
    assert len(passed.left_sha256) == len(passed.right_sha256) == 64
    assert failed.left_sha256 == passed.left_sha256
    assert failed.right_sha256 != passed.right_sha256


@pytest.mark.skipif(not available(), reason="optional SAT unavailable")
def test_partial_contract_is_not_a_full_state_proof():
    left = Circuit(3)
    ignored_garbage = Circuit(3).x(2)
    partial = verify_explicit(
        left, ignored_garbage, theorem="classical_contract", engine="sat",
        contract=Contract(observed_outputs=(0, 1)),
    )
    full = verify_explicit(left, ignored_garbage, theorem="classical_full", engine="sat")
    assert partial.certified and not full.certified
    assert partial.theorem == "classical_contract"
    assert partial.contract_sha256 and full.contract_sha256 is None
    restored = verify_explicit(
        left, ignored_garbage, theorem="classical_contract", engine="sat",
        contract=Contract(observed_outputs=(0, 1), restored_wires=(2,)),
    )
    assert restored.outcome == "different" and restored.witness_kind == "input"
    assert not restored.certified


@pytest.mark.skipif(not available(), reason="optional SAT unavailable")
def test_sat_inconclusive_never_becomes_equivalent():
    result = verify_explicit(
        Circuit(3), Circuit(3), theorem="classical_full", engine="sat",
        budget=Budget(max_seconds=1e-9),
    )
    assert result.outcome == "inconclusive" and not result.certified


def test_resource_failure_is_an_inconclusive_symbolic_verdict():
    result = verify_explicit(
        Circuit(3).ccx(0, 1, 2), Circuit(3),
        theorem="classical_full", engine="sparse", budget=Budget(max_terms=1),
    )
    assert result.outcome == "inconclusive" and not result.certified


def test_phase_global_sign_is_explicitly_not_exact_equality():
    minus_identity = PhaseProgram(1).x(0).z(0).x(0).z(0)
    identity = PhaseProgram(1)
    strict = verify_explicit(
        minus_identity, identity, theorem="sign_phase_exact", engine="phase-reference",
    )
    global_ok = verify_explicit(
        minus_identity, identity, theorem="sign_phase_up_to_global",
        engine="phase-reference",
    )
    assert strict.outcome == "different" and strict.global_phase_exponent == 4
    assert not strict.certified
    assert global_ok.certified and global_ok.global_phase_exponent == 4


def test_unclean_ancilla_is_failed_precondition_not_non_equivalence():
    dirty = PhaseProgram(1, 1).cx(0, 1)
    value = verify_explicit(
        dirty, PhaseProgram(1, 1), theorem="sign_phase_exact", engine="phase-reference",
    )
    assert value.outcome == "precondition_failed" and not value.certified
    assert "O1:" in value.reason


def test_full_channel_is_explicitly_unavailable_not_a_strict_branch_result():
    left = PhaseProgram(1, 1)
    result = verify_explicit(
        left, left, theorem="full_channel", engine="channel-sat",
    )
    assert result.outcome == "unsupported" and not result.certified
    assert "research" in result.reason


def test_invalid_gate_and_cross_semantics_are_refused():
    with pytest.raises(UnsupportedOperation):
        Circuit(1).append("t", 0)
    with pytest.raises(UnsupportedOperation):
        PhaseProgram(1).append("h", 0)
    with pytest.raises(TypeError):
        verify_explicit(Circuit(1), PhaseProgram(1), theorem="classical_full", engine="sat")
    with pytest.raises(ValueError, match="cannot establish"):
        verify_explicit(Circuit(2), Circuit(2), theorem="classical_contract",
                        engine="sparse", contract=Contract(observed_outputs=(0,)))
    with pytest.raises(ValueError, match="explicit Contract"):
        verify_explicit(Circuit(2), Circuit(2), theorem="classical_contract", engine="sat")
    with pytest.raises(ValueError, match="does not accept"):
        verify_explicit(Circuit(2), Circuit(2), theorem="classical_full", engine="sat",
                        contract=Contract(observed_outputs=(0,)))


def test_unavailable_solver_and_non_enforceable_limits_fail_closed(monkeypatch):
    import symq.verification as portfolio

    def unavailable(*args, **kwargs):
        raise SatUnavailable("no solver")
    monkeypatch.setattr(portfolio, "check_sat_equivalence", unavailable)
    outcome = verify_explicit(Circuit(1), Circuit(1),
                              theorem="classical_full", engine="sat")
    assert outcome.outcome == "unsupported" and not outcome.certified
    with pytest.raises(ValueError, match="symbolic term/node budgets"):
        verify_explicit(Circuit(1), Circuit(1), theorem="classical_full",
                        engine="sat", budget=Budget(max_nodes=1))
    with pytest.raises(ValueError, match="no resource budget"):
        verify_explicit(PhaseProgram(1), PhaseProgram(1),
                        theorem="sign_phase_exact", engine="phase-reference",
                        budget=Budget(max_seconds=10))


def test_digests_change_with_contract_and_program_mutation():
    a, b = Circuit(3), Circuit(3)
    mode = {"theorem": "classical_contract", "engine": "sat"}
    if not available():
        pytest.skip("optional SAT unavailable")
    first = verify_explicit(a, b, contract=Contract(observed_outputs=(0,)), **mode)
    second = verify_explicit(a, b, contract=Contract(observed_outputs=(1,)), **mode)
    assert first.contract_sha256 != second.contract_sha256
    b.x(0)
    mutated = verify_explicit(a, b, contract=Contract(observed_outputs=(1,)), **mode)
    assert mutated.right_sha256 != second.right_sha256
    assert mutated.outcome == "equivalent"


def test_theorem_vocabulary_is_explicit_and_no_selector_used():
    assert "classical_full" in THEOREMS and "full_channel" in THEOREMS
    assert "auto" not in THEOREMS
    with pytest.raises(ValueError, match="unknown theorem"):
        verify_explicit(Circuit(1), Circuit(1), theorem="quantum_general", engine="sat")



def test_verifier_rejects_late_symbolic_yes_and_no(monkeypatch):
    """A backend may complete after its own check; do not certify an over-budget result."""
    import time

    import symq.verification as portfolio

    original = portfolio.check_equivalence

    def late(*args, **kwargs):
        value = original(*args, **kwargs)
        time.sleep(0.025)
        return value

    monkeypatch.setattr(portfolio, "check_equivalence", late)
    for right in (Circuit(2), Circuit(2).x(0)):
        result = verify_explicit(
            Circuit(2), right, theorem="classical_full", engine="sparse",
            budget=Budget(max_seconds=0.010),
        )
        assert result.outcome == "inconclusive" and not result.certified
        assert result.witness is None


def test_optional_qcec_is_unchanged_but_cannot_certify_late_results(monkeypatch):
    """External QCEC timed verdicts are subject to the facade's whole-call deadline."""
    import time
    from types import SimpleNamespace

    from symq import external

    passed_timeouts = []

    def late_equivalence(_left, _right, *, timeout):
        passed_timeouts.append(timeout)
        time.sleep(0.025)
        return SimpleNamespace(equivalent=True, verdict="equivalent")

    monkeypatch.setattr(external, "qcec_check", late_equivalence)
    result = verify_explicit(
        Circuit(2), Circuit(2), theorem="classical_full", engine="qcec",
        budget=Budget(max_seconds=0.010),
    )
    assert result.outcome == "inconclusive" and not result.certified
    assert passed_timeouts and 0 < passed_timeouts[0] <= 0.010


def test_absent_native_zdd_is_unsupported_not_false_proof_or_wrong_contract(monkeypatch):
    import symq.verification as portfolio

    monkeypatch.delitem(portfolio.BACKENDS, "zdd-native", raising=False)
    verdict = verify_explicit(
        Circuit(2), Circuit(2), theorem="classical_full", engine="zdd-native",
    )
    assert verdict.outcome == "unsupported" and not verdict.certified
    with pytest.raises(ValueError, match="cannot establish"):
        verify_explicit(
            Circuit(2), Circuit(2), theorem="classical_contract",
            engine="zdd-native", contract=Contract(observed_outputs=(0,)),
        )
