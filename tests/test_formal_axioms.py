"""Axiom report checks fail closed on missing/forged proof authority."""
from __future__ import annotations

import pytest

from tools.check_formal_axioms import THEOREMS, validate_report


def valid_report():
    return "\n".join(f"'{name}' does not depend on any axioms" for name in sorted(THEOREMS))


def test_exact_six_theorem_reports_with_no_axioms():
    assert len(validate_report(valid_report())) == len(THEOREMS) == 37


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
