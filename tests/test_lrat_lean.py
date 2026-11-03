"""Lean emission is data transport, never itself a positive proof verdict."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from benchmarks.lean_phase_proofs import GATE_LEMMAS, axiom_audit, gate_source_audit
from symq.labs import lrat_lean, lrat_rup

CNF = 'p cnf 1 2\n1 0\n-1 0\n'
LRAT = '3 0 1 2 0\n'


def pin(text):
    return hashlib.sha256(text.encode('ascii')).hexdigest()


def test_exact_literal_translation_and_typed_proof_actions():
    result = lrat_lean.emit_lean(CNF, LRAT, expected_cnf_sha256=pin(CNF))
    assert result['status'] == 'emitted' and not result['verified_unsat']
    text = result['lean_source']
    assert '((Subtype.mk 1 (by decide)), true)' in text and '((Subtype.mk 1 (by decide)), false)' in text
    assert '.addEmpty 3 #[1, 2]' in text
    assert 'lratCheckerSound formula' in text and '(by decide +kernel)' in text
    assert 'native_decide' not in text and 'sorry' not in text and 'axiom ' not in text
    assert pin(text) == result['lean_sha256']
    assert result['toolchain'] == 'leanprover/lean4:v4.19.0'


def test_signed_variables_and_empty_formula_clause_are_not_dropped():
    cnf = 'p cnf 9 3\n9 -3 1 0\n-1 0\n0\n'
    result = lrat_lean.emit_lean(cnf, '4 0 3 0\n', expected_cnf_sha256=pin(cnf))
    assert result['status'] == 'emitted'
    formula = result['lean_source'].split('def formula')[0]
    literals = [int(n) * (1 if p == 'true' else -1)
                for n, p in re.findall(r'\(\(Subtype.mk (\d+) \(by decide\)\), (true|false)\)', formula)]
    assert literals == [9, -3, 1, -1]
    assert 'clause := []' in formula
    assert '.addEmpty 4 #[3]' in result['lean_source']


def test_invalid_trace_can_be_emitted_but_never_called_verified(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('emitter must not depend on Python inference acceptance')

    monkeypatch.setattr(lrat_rup, '_inference', forbidden)
    cnf = 'p cnf 2 2\n1 2 0\n-1 2 0\n'
    result = lrat_lean.emit_lean(cnf, '3 0 1 2 0\n', expected_cnf_sha256=pin(cnf))
    assert result['status'] == 'emitted'
    assert result['verified_unsat'] is False
    # The dedicated Lean campaign proves this non-unit-hint trace is rejected.


def test_gap_in_proof_ids_is_explicitly_outside_the_lean_profile():
    result = lrat_lean.emit_lean(CNF, '5 0 1 2 0\n', expected_cnf_sha256=pin(CNF))
    assert result['status'] == 'invalid' and not result['verified_unsat']
    assert 'contiguous' in result['reason']


@pytest.mark.parametrize('proof', [
    '', '3 0 0\n', '3 0 9 0\n', '3 0 -1 0\n', '3 0 1 2 0\n4 0 3 0\n',
    '3 d 1 0\n', '3 1 -1 0 1 2 0\n', '3 2 0 1 2 0\n4 0 3 0\n',
    '3 0 1 2 0\naxiom fabricated : False\n', '3 0 1 2 0\nsorry',
])
def test_closed_syntax_never_injects_lean(proof):
    result = lrat_lean.emit_lean(CNF, proof, expected_cnf_sha256=pin(CNF))
    assert result['status'] == 'invalid'
    assert result['lean_source'] is None and not result['verified_unsat']


def test_comment_is_not_lean_code_and_independent_formula_pin_is_required():
    cnf = 'c axiom fake : False\n' + CNF
    result = lrat_lean.emit_lean(cnf, LRAT, expected_cnf_sha256=pin(cnf))
    assert result['status'] == 'emitted' and 'fake' not in result['lean_source']
    assert lrat_lean.emit_lean(cnf, LRAT, expected_cnf_sha256=pin(CNF))['status'] == 'invalid'
    for invalid in (True, None, 'x' * 64, 'A' * 64):
        result = lrat_lean.emit_lean(cnf, LRAT, expected_cnf_sha256=invalid)
        assert result['status'] == 'invalid' and result['lean_source'] is None


def test_resource_expiry_clears_all_emission_metadata(monkeypatch):
    baseline = lrat_lean.emit_lean(CNF, LRAT, expected_cnf_sha256=pin(CNF))
    real_tick = lrat_rup.Meter.tick
    calls = [0]

    def count(self, amount=1):
        calls[0] += 1
        return real_tick(self, amount)

    with monkeypatch.context() as context:
        context.setattr(lrat_rup.Meter, 'tick', count)
        lrat_lean.emit_lean(CNF, LRAT, expected_cnf_sha256=pin(CNF))
    assert calls[0] > 5 and baseline['status'] == 'emitted'
    for point in range(calls[0]):
        remaining = [point]

        def expire(self, amount=1, remaining=remaining):
            if not remaining[0]:
                raise lrat_rup.ProofLimit('injected expiry')
            remaining[0] -= 1
            return real_tick(self, amount)

        with monkeypatch.context() as context:
            context.setattr(lrat_rup.Meter, 'tick', expire)
            result = lrat_lean.emit_lean(CNF, LRAT, expected_cnf_sha256=pin(CNF))
        assert result['status'] == 'inconclusive' and result['lean_source'] is None
        assert not result['verified_unsat']
        assert 'lean_sha256' not in result and 'cnf_sha256' not in result
    result = lrat_lean.emit_lean(CNF, LRAT, expected_cnf_sha256=pin(CNF),
                                 limits=lrat_rup.Limits(max_bytes=100))
    assert result['status'] == 'inconclusive'


# --- Qualification log/source audit (audit #171): a sorry is only a Lean warning. ---
GATES = Path(__file__).resolve().parents[1] / 'formal' / 'portable_lrat' / 'GateLemmas.lean'
CLEAN_LOG = '\n'.join(f"'{name}' does not depend on any axioms" for name in GATE_LEMMAS) + '\n'


def test_committed_gate_lemmas_and_clean_log_pass():
    gate_source_audit(GATES.read_text())
    assert axiom_audit(CLEAN_LOG, *GATE_LEMMAS) == []
    claim = "'SymQPortable.claim' depends on axioms: [propext, Classical.choice, Quot.sound]\n"
    assert axiom_audit(claim, 'SymQPortable.claim') == ['Classical.choice', 'Quot.sound', 'propext']


@pytest.mark.parametrize('log', [
    CLEAN_LOG + "GateLemmas.lean:40:8: warning: declaration uses 'sorry'\n",
    CLEAN_LOG + 'GateLemmas.lean:3:0: error: unknown identifier\n',
    CLEAN_LOG.replace("'SymQPortable.andClauses_iff' does not depend on any axioms\n", ''),
    CLEAN_LOG + "'SymQPortable.fibre_constancy' does not depend on any axioms\n",
    CLEAN_LOG.replace('does not depend on any axioms', 'depends on axioms: [sorryAx]', 1),
])
def test_axiom_audit_rejects_sorry_warnings_missing_and_repeated_reports(log):
    with pytest.raises(AssertionError):
        axiom_audit(log, *GATE_LEMMAS)


SPOOF = "'SymQPortable.andClauses_iff' does not depend on any axioms"


@pytest.mark.parametrize('transform', [
    lambda s: s.replace('#print axioms andClauses_iff', f'#eval IO.println "{SPOOF}"'),
    lambda s: s.replace('#print axioms andClauses_iff', f'#print "{SPOOF}"'),
    lambda s: s.replace('#print axioms andClauses_iff\n', ''),
    lambda s: s.replace('end SymQPortable', 'theorem bogus : 1 = 2 := by sorry\nend SymQPortable'),
    lambda s: s.replace('end SymQPortable', 'axiom cheat : False\nend SymQPortable'),
    lambda s: s.replace('end SymQPortable', 'set_option debug.skipKernelTC true\nend SymQPortable'),
])
def test_gate_source_audit_rejects_forged_reports_and_proof_escapes(transform):
    source = GATES.read_text()
    mutated = transform(source)
    assert mutated != source
    with pytest.raises(AssertionError):
        gate_source_audit(mutated)
