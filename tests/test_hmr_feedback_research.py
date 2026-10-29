"""Proof-carrying HMR late-feedback synthesis: independent oracle and negative gates."""
import random

import pytest

from research.hmr_feedback.repair import (
    PhaseDebtUnresolved,
    fingerprint,
    synthesize_feedback,
)
from symq import Budget, PhaseProgram, ResourceLimitExceeded
from symq.backends import has_native
from symq.phase import check_phase_equivalence, phase_semantics
from symq.phase_oracle import run_program


def assert_all_branches(program, receipt):
    sem = phase_semantics(program)
    assert not sem.violations()
    for x in range(1 << program.data):
        outputs = [
            sum(f.evaluate(x) << q for q, f in enumerate(sem.outputs))
        ][0]
        sign = -1 if sem.phase.evaluate(x) else 1
        for m in range(1 << program.measurements):
            assert run_program(program, x, m) == {outputs: sign}
    assert receipt.original_event_count == program.measurements


def temporary_and():
    p = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    p.hmr(3)
    return p


def test_temporary_and_repairs_exact_coherent_input_semantics():
    raw = temporary_and()
    before = fingerprint(raw)
    repaired, proof = synthesize_feedback(raw)
    assert before == fingerprint(raw)
    assert {(r.outcome, r.controls) for r in proof.repairs} == {(0, (0, 1))}
    proof.assert_fresh(raw, repaired)
    assert_all_branches(repaired, proof)
    target = PhaseProgram(3).ccx(0, 1, 2)
    assert check_phase_equivalence(repaired, target).equivalent
    broken = temporary_and()
    assert not check_phase_equivalence(broken, target).equivalent


def test_deferred_correction_after_noncommuting_cx_is_synthesized_on_final_wires():
    raw = temporary_and().cx(0, 1)
    repaired, proof = synthesize_feedback(raw, max_arity=2)
    assert proof.repairs
    ref = PhaseProgram(3).ccx(0, 1, 2).cx(0, 1)
    assert check_phase_equivalence(repaired, ref).equivalent
    assert_all_branches(repaired, proof)


def test_linear_only_repair_refuses_quadratic_debt():
    with pytest.raises(PhaseDebtUnresolved, match="outside the span"):
        synthesize_feedback(temporary_and(), max_arity=1)


def test_global_outcome_sign_is_not_strictly_repairable_without_constant_live_wire():
    p = PhaseProgram(1, 1).x(1)
    p.hmr(1)
    with pytest.raises(PhaseDebtUnresolved, match="outside the span"):
        synthesize_feedback(p)


def test_dirty_ancilla_is_not_mistaken_for_reconstructed_zero():
    p = PhaseProgram(2, 1).ccx(0, 1, 2)
    with pytest.raises(PhaseDebtUnresolved, match="dirty"):
        synthesize_feedback(p)


@pytest.mark.parametrize("seed", range(15))
def test_random_small_repair_matches_independent_kraus_branches(seed):
    r = random.Random(seed)
    p = PhaseProgram(3, 1)
    p.ccx(0, 1, 3).cx(3, 2)
    p.hmr(3)
    for _ in range(r.randrange(3)):
        p.cx(*r.sample(range(3), 2))
    repaired, receipt = synthesize_feedback(p, max_arity=3)
    assert_all_branches(repaired, receipt)


def test_native_coefficient_audit_is_opt_in_and_explicit():
    raw = temporary_and()
    if has_native():
        repaired, receipt = synthesize_feedback(raw, audit_backend="zdd-native")
        assert receipt.native_audit == "zdd-native"
        assert_all_branches(repaired, receipt)
    else:
        with pytest.raises(ValueError, match="native"):
            synthesize_feedback(raw, audit_backend="zdd-native")


def test_resource_and_stale_receipts_fail_closed():
    p = temporary_and()
    with pytest.raises(ResourceLimitExceeded):
        synthesize_feedback(p, budget=Budget(max_seconds=1e-12))
    with pytest.raises(ResourceLimitExceeded):
        synthesize_feedback(p, max_candidates=1)
    with pytest.raises(ValueError, match="max_nodes"):
        synthesize_feedback(p, budget=Budget(max_nodes=20))
    repaired, receipt = synthesize_feedback(p)
    repaired.x(0)
    with pytest.raises(ValueError, match="changed"):
        receipt.assert_fresh(p, repaired)
