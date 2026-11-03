"""Axiom report checks fail closed on missing/forged proof authority."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.check_formal_axioms import (
    THEOREMS,
    validate_contracts,
    validate_report,
    validate_sources,
)

ROOT = Path(__file__).resolve().parents[1]
FORMAL = ROOT / "formal" / "symq_runtime"


def valid_report():
    return "\n".join(f"'{name}' does not depend on any axioms" for name in sorted(THEOREMS))


def test_exact_theorem_reports_with_no_axioms():
    assert len(validate_report(valid_report())) == len(THEOREMS) == 54


def test_recognizes_ordinary_lean_axioms():
    one = next(iter(THEOREMS))
    report = valid_report().replace(
        f"'{one}' does not depend on any axioms",
        f"'{one}' depends on axioms: [propext, Classical.choice, Quot.sound]",
    )
    assert set(validate_report(report)[one]) == {"propext", "Classical.choice", "Quot.sound"}


@pytest.mark.parametrize(
    "bad",
    [
        lambda x: x.split("\n", 1)[1],
        lambda x: x + "\n'" + next(iter(THEOREMS)) + "' does not depend on any axioms",
        lambda x: x + "\n'SymQFormal.some_fake' does not depend on any axioms",
        lambda x: x.replace("does not depend on any axioms", "depends on axioms: [sorryAx]", 1),
        lambda x: x.replace("does not depend on any axioms", "depends on axioms: [myCustomAx]", 1),
        lambda x: x + "\nLean.trustCompiler",
    ],
)
def test_rejects_missing_duplicate_or_untrusted_reports(bad):
    with pytest.raises(ValueError):
        validate_report(bad(valid_report()))


@pytest.mark.parametrize(
    "diagnostic",
    [
        "GraphRewrites.lean:70:8: warning: declaration uses 'sorry'",
        "AcyclicDAG.lean:3:0: error: unknown identifier 'x'",
        "GateCNF.lean:1:1: warning: unused variable `h`",
    ],
)
def test_rejects_any_lean_diagnostic_even_for_unlisted_declarations(diagnostic):
    # A sorry in an unlisted theorem is only a warning and Lean exits 0.
    with pytest.raises(ValueError, match="diagnostic"):
        validate_report(valid_report() + "\n" + diagnostic)


def test_the_committed_sources_pass_the_source_scan():
    assert set(validate_sources(FORMAL)) == THEOREMS


def _mutated(tmp_path, transform):
    for path in FORMAL.glob("*.lean"):
        shutil.copy(path, tmp_path / path.name)
    target = tmp_path / "GraphRewrites.lean"
    target.write_text(transform(target.read_text(encoding="utf-8")), encoding="utf-8")
    return tmp_path


SPOOF = "'SymQFormal.xor_zero' does not depend on any axioms"


@pytest.mark.parametrize(
    "transform",
    [
        # A forged report printed by #eval in place of the real #print axioms.
        lambda s: s.replace("#print axioms xor_zero", f'#eval IO.println "{SPOOF}"'),
        # The same forgery through #print of a string literal.
        lambda s: s.replace("#print axioms xor_zero", f'#print "{SPOOF}"'),
        # An unlisted theorem closed by sorry (Lean only warns).
        lambda s: s.replace("end SymQFormal", "theorem bogus : 1 = 2 := by sorry\nend SymQFormal"),
        lambda s: s.replace("end SymQFormal", "axiom cheat : False\nend SymQFormal"),
        lambda s: s.replace("end SymQFormal", "macro \"x\" : term => `(1)\nend SymQFormal"),
        lambda s: s.replace("end SymQFormal", "set_option debug.skipKernelTC true\nend SymQFormal"),
        lambda s: s.replace("end SymQFormal", "run_cmd pure ()\nend SymQFormal"),
        # Missing and duplicated reports.
        lambda s: s.replace("#print axioms xor_zero\n", ""),
        lambda s: s.replace("#print axioms xor_zero", "#print axioms xor_zero\n#print axioms xor_zero"),
        lambda s: s + "\n/- unterminated comment",
        # A forged report logged by a tactic, with the real #print hidden in a string literal.
        lambda s: s.replace("#print axioms xor_zero\n", "").replace(
            "end SymQFormal",
            'def hidden : String := "\n#print axioms xor_zero\n"\n'
            f'example : True := by\n  trace "{SPOOF}"\n  trivial\nend SymQFormal'),
        lambda s: s.replace("end SymQFormal", 'def hidden : String := "x"\nend SymQFormal'),
        lambda s: s.replace("end SymQFormal", "example : True := by\n  dbg_trace 1; trivial\nend SymQFormal"),
        lambda s: s.replace("end SymQFormal", "open Lean in\ndef x := 1\nend SymQFormal"),
    ],
)
def test_source_scan_rejects_forgeries_and_escapes(tmp_path, transform):
    with pytest.raises(ValueError):
        validate_sources(_mutated(tmp_path, transform))


def test_forbidden_words_inside_comments_are_ignored(tmp_path):
    directory = _mutated(tmp_path, lambda s: s.replace(
        "end SymQFormal", "-- no sorry, axiom or #eval here\n/- nor #print \"x\" -/\nend SymQFormal"))
    assert set(validate_sources(directory)) == THEOREMS


def test_report_lines_must_start_a_line():
    prefixed = valid_report().replace("'SymQFormal.xor_zero'", "x 'SymQFormal.xor_zero'", 1)
    with pytest.raises(ValueError):
        validate_report(prefixed)


def test_command_line_requires_the_source_scan(tmp_path):
    log = tmp_path / "theorems.log"
    log.write_text(valid_report())
    script = ROOT / "tools" / "check_formal_axioms.py"
    bare = subprocess.run([sys.executable, str(script), str(log)], check=False, capture_output=True)
    assert bare.returncode != 0
    full = subprocess.run([sys.executable, str(script), str(log), "--sources", str(FORMAL)],
                          check=False, capture_output=True)
    assert full.returncode == 0, full.stderr


def test_every_listed_theorem_has_a_statement_contract_built_by_lake():
    assert validate_contracts(FORMAL) == THEOREMS


def _contracts_copy(tmp_path, transform_contracts=None, transform_lakefile=None):
    for path in FORMAL.glob("*.lean"):
        shutil.copy(path, tmp_path / path.name)
    if transform_contracts:
        target = tmp_path / "Contracts.lean"
        target.write_text(transform_contracts(target.read_text(encoding="utf-8")), encoding="utf-8")
    if transform_lakefile:
        target = tmp_path / "lakefile.lean"
        target.write_text(transform_lakefile(target.read_text(encoding="utf-8")), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "contracts, lakefile",
    [
        # A contract removed: its theorem's meaning is no longer pinned.
        (lambda s: s.replace("  apply SymQFormal.runtimeQuery_unsat_sound <;> assumption",
                             "  sorry"), None),
        # A contract proved from a different theorem.
        (lambda s: s.replace("apply SymQFormal.xor_zero <;>", "apply SymQFormal.xor_one <;>"), None),
        # A definition pin removed: gateCNF could change without breaking any contract.
        (lambda s: s.replace("example (z : Nat) (a b : Literal) : gateCNF (.andGate z a b) = andCNF z a b := rfl\n",
                             "").replace("example (n : Nat) : gateCNF (.input n) = [] := rfl\n", "").replace(
            "example (z : Nat) (a b : Literal) : gateCNF (.xorGate z a b) = xorCNF z a b := rfl\n", ""), None),
        # Contracts no longer built by `lake build`.
        (None, lambda s: s.replace("@[default_target] lean_lib Contracts\n", "")),
    ],
)
def test_contract_coverage_is_enforced(tmp_path, contracts, lakefile):
    with pytest.raises(ValueError):
        validate_contracts(_contracts_copy(tmp_path, contracts, lakefile))
