"""Strict standalone parser for formal Lean theorem axiom reports in CI.

This is a *report validator*, not a proof checker; Lean's kernel produces the
proof artifacts. Missing theorem reports and unfamiliar axioms fail closed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

THEOREMS = frozenset(
    {
        "SymQFormal.andCNF_exact",
        "SymQFormal.xorCNF_exact",
        "SymQFormal.encode_exact",
        "SymQFormal.unsat_excludes_gate_counterexample",
        "SymQFormal.fullAdder_exact",
        "SymQFormal.addWords_exact",
        "SymQFormal.restrict_extend",
        "SymQFormal.finalBit_extend",
        "SymQFormal.extend_restrict_final",
        "SymQFormal.execute_satisfies",
        "SymQFormal.satisfies_unique",
        "SymQFormal.unique_model",
        "SymQFormal.andClauses_exact",
        "SymQFormal.xorClauses_exact",
        "SymQFormal.pinnedCNF_exact",
        "SymQFormal.pinnedCNF_unique_model",
        "SymQFormal.pinnedCNF_root_unsat",
    }
)
ALLOWED = frozenset({"propext", "Quot.sound", "Classical.choice"})
REPORT = re.compile(
    r"'(?P<name>SymQFormal\.[A-Za-z_][A-Za-z_0-9]*)' "
    r"(?:(?:depends on axioms: \[(?P<axioms>[^\]]*)\])|"
    r"(?:does not depend on any axioms))"
)


def validate_report(text: str) -> dict[str, list[str]]:
    if type(text) is not str:
        raise ValueError("Lean output must be text")
    reports: dict[str, list[str]] = {}
    for hit in REPORT.finditer(text):
        name = hit.group("name")
        if name in reports:
            raise ValueError(f"duplicate axiom report: {name}")
        if name not in THEOREMS:
            raise ValueError(f"unexpected theorem report: {name}")
        deps = [] if hit.group("axioms") is None else [
            a.strip() for a in hit.group("axioms").split(",") if a.strip()
        ]
        illegal = set(deps) - ALLOWED
        if illegal:
            raise ValueError(f"untrusted axiom for {name}: {sorted(illegal)}")
        reports[name] = deps
    absent = THEOREMS - reports.keys()
    if absent:
        raise ValueError(f"missing theorem reports: {sorted(absent)}")
    if "sorryAx" in text or "Lean.trustCompiler" in text or "Lean.ofReduce" in text:
        raise ValueError("untrusted reduction axiom mentioned in Lean output")
    return reports


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/check_formal_axioms.py LOG")
    validate_report(Path(sys.argv[1]).read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
