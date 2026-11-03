"""Strict standalone parser for formal Lean theorem axiom reports in CI.

This is a *report validator*, not a proof checker; Lean's kernel produces the
proof artifacts. Missing theorem reports and unfamiliar axioms fail closed.

Two checks are needed because a report line is plain text:

* the log must contain no Lean diagnostic at all (a ``sorry`` in any
  declaration, listed or not, is only a *warning* and Lean still exits 0);
* the Lean sources must contain no command that can print arbitrary text or
  extend the language (``#eval``, ``#print "..."``, ``run_cmd``, macros,
  notations, ...), and exactly one ``#print axioms`` per listed theorem.
  Otherwise a source file could print a forged "does not depend on any
  axioms" line for a theorem whose real report was removed.

The checker pins theorem *names*, not statements: reviewers must still read
what each listed theorem says.
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
        "SymQFormal.xor_commutative",
        "SymQFormal.xor_zero",
        "SymQFormal.xor_one",
        "SymQFormal.xor_self",
        "SymQFormal.xor_complement",
        "SymQFormal.xor_cancel_left",
        "SymQFormal.xor_cancel_right",
        "SymQFormal.xor_signed_left",
        "SymQFormal.xor_signed_right",
        "SymQFormal.xor_signed_both",
        "SymQFormal.and_commutative",
        "SymQFormal.and_zero",
        "SymQFormal.and_one",
        "SymQFormal.and_self",
        "SymQFormal.and_complement",
        "SymQFormal.flatAnd_exact",
        "SymQFormal.flatXor_exact",
        "SymQFormal.flatPin_exact",
        "SymQFormal.flatPinned_exact",
        "SymQFormal.flatQuery_exact",
        "SymQFormal.physicalFromNodes_one",
        "SymQFormal.physicalFromNodes_read",
        "SymQFormal.flatQuery_sat_iff",
        "SymQFormal.flatQuery_unsat_iff",
        "SymQFormal.runtimeGateClauses_exact",
        "SymQFormal.runtimeMatches_of_satisfies",
        "SymQFormal.runtimeQuery_exact",
        "SymQFormal.runtimeQuery_unsat_sound",
        "SymQFormal.duplicateKeySourceAlwaysZero",
        "SymQFormal.duplicateKeyUnpinnedSAT",
        "SymQFormal.inputMatches_congr",
        "SymQFormal.source_exists_unique_keys",
        "SymQFormal.runtimeMatches_inputMatches",
        "SymQFormal.runtimeQuery_sat_complete_unique_keys",
        "SymQFormal.runtimeQuery_sat_iff_unique_keys",
        "SymQFormal.runtimeQuery_unsat_iff_unique_keys",
        "SymQFormal.uniqueInputKeys_iff_nodup",
    }
)
ALLOWED = frozenset({"propext", "Quot.sound", "Classical.choice"})
REPORT = re.compile(
    r"^'(?P<name>SymQFormal\.[A-Za-z_][A-Za-z_0-9]*)' "
    r"(?:(?:depends on axioms: \[(?P<axioms>[^\]]*)\])|"
    r"(?:does not depend on any axioms))",
    re.MULTILINE,
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
    diagnostic = DIAGNOSTIC.search(text)
    if diagnostic is not None or "declaration uses 'sorry'" in text:
        raise ValueError(f"Lean reported a diagnostic: {diagnostic.group(0) if diagnostic else 'sorry'}")
    return reports


# Lean diagnostics look like ``File.lean:12:8: warning: ...``; the clean log has none.
DIAGNOSTIC = re.compile(r"^[^\n]*:\d+:\d+: (?:warning|error|info): [^\n]*", re.MULTILINE)
# Forbidden anywhere outside comments: proof escapes, new axioms and any command or
# extension that can print text or change parsing/elaboration.
FORBIDDEN = re.compile(
    r"(?<![A-Za-z0-9_.'])(?:sorry|admit|axiom|native_decide|implemented_by|extern|unsafe|"
    r"opaque|partial|initialize|builtin_initialize|macro|macro_rules|syntax|notation|"
    r"infix|infixl|infixr|prefix|postfix|elab|elab_rules|run_cmd|run_elab|run_meta|"
    r"set_option|attribute|IO|Lean|trace|trace_state|dbg_trace|dbgTrace|logInfo|"
    r"logWarning|logError|throwError|MetaM|TermElabM|CommandElabM|by_elab)(?![A-Za-z0-9_'])"
)
HASH_COMMAND = re.compile(r"^\s*(#\S*)(.*)$", re.MULTILINE)
PRINT_AXIOMS = re.compile(r"#print axioms (?P<name>[A-Za-z_][A-Za-z_0-9.]*)\s*$")


def _strip_comments(source: str) -> str:
    out, i, depth = [], 0, 0
    while i < len(source):
        if source.startswith("/-", i):
            depth, i = depth + 1, i + 2
        elif depth and source.startswith("-/", i):
            depth, i = depth - 1, i + 2
        elif depth:
            out.append("\n" if source[i] == "\n" else " ")
            i += 1
        elif source.startswith("--", i):
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
        else:
            out.append(source[i])
            i += 1
    if depth:
        raise ValueError("unterminated Lean block comment")
    return "".join(out)


def validate_sources(directory: Path, namespace: str = "SymQFormal") -> dict[str, str]:
    """Check every ``*.lean`` file of the formal project before trusting its log."""
    printed: dict[str, str] = {}
    files = sorted(Path(directory).glob("*.lean"))
    if not files:
        raise ValueError(f"no Lean sources in {directory}")
    for path in files:
        if path.name == "lakefile.lean":
            continue
        code = _strip_comments(path.read_text(encoding="utf-8"))
        bad = FORBIDDEN.search(code)
        if bad is not None:
            raise ValueError(f"{path.name}: forbidden Lean construct {bad.group(0)!r}")
        if '"' in code:
            # No string literal can carry a forged report or hide a '#print axioms' line.
            raise ValueError(f"{path.name}: string literals are not allowed in formal sources")
        for hit in HASH_COMMAND.finditer(code):
            line = (hit.group(1) + hit.group(2)).strip()
            match = PRINT_AXIOMS.fullmatch(line)
            if match is None:
                raise ValueError(f"{path.name}: only '#print axioms NAME' commands are allowed: {line!r}")
            name = f"{namespace}.{match.group('name')}"
            if name in printed:
                raise ValueError(f"duplicate '#print axioms' for {name}")
            printed[name] = path.name
    if set(printed) != THEOREMS:
        raise ValueError(f"'#print axioms' commands do not match the theorem list: "
                         f"missing {sorted(THEOREMS - set(printed))}, extra {sorted(set(printed) - THEOREMS)}")
    return printed


CONTRACT = re.compile(
    r"^theorem (?P<contract>[A-Za-z_][A-Za-z_0-9]*)_contract\b[^\n]*:= by\n"
    r"  apply SymQFormal\.(?P<name>[A-Za-z_][A-Za-z_0-9]*) <;> assumption$",
    re.MULTILINE,
)


MODEL_FILES = ("GateCNF.lean", "PhaseBits.lean", "AcyclicDAG.lean", "GraphRewrites.lean")
DEFINITION = re.compile(r"^(?:def|abbrev)\s+([A-Za-z_][A-Za-z_0-9]*)", re.MULTILINE)
PIN = re.compile(r"^example\b.*?(?=^\S|\Z)", re.MULTILINE | re.DOTALL)
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _pinned_head(block: str) -> str | None:
    """The definition a pin restates: the first identifier of its statement.

    The statement follows the first ':' at bracket depth 0 before ':='; binders such
    as `(v : Valuation)` are skipped, so a name used only on a right-hand side or in
    a binder type does not count as pinned.
    """
    end = block.find(":=")
    if end < 0:
        return None
    depth, colon = 0, -1
    for index, char in enumerate(block[:end]):
        if char in "([{⟨":
            depth += 1
        elif char in ")]}⟩":
            depth -= 1
        elif char == ":" and depth == 0:
            colon = index
            break
    match = IDENTIFIER.search(block[colon + 1:end]) if colon >= 0 else None
    return match.group(0) if match else None


def validate_contracts(directory: Path, namespace: str = "SymQFormal") -> set[str]:
    """Check that Contracts.lean restates every listed theorem and is built by Lake.

    Names alone do not pin meaning: ``Contracts.lean`` restates each reviewed
    statement (and the definitions it relies on) and proves it only by applying
    the original theorem, so Lean rejects any weakened statement. This function
    checks the coverage of that file; Lean itself checks its content.
    """
    directory = Path(directory)
    lakefile = (directory / "lakefile.lean").read_text(encoding="utf-8")
    if not re.search(r"^@\[default_target\] lean_lib Contracts$", lakefile, re.MULTILINE):
        raise ValueError("Contracts must be a default Lake target so `lake build` checks it")
    code = _strip_comments((directory / "Contracts.lean").read_text(encoding="utf-8"))
    covered: set[str] = set()
    for hit in CONTRACT.finditer(code):
        if hit.group("contract") != hit.group("name"):
            raise ValueError(f"contract {hit.group('contract')} applies {hit.group('name')}")
        name = f"{namespace}.{hit.group('name')}"
        if name in covered:
            raise ValueError(f"duplicate statement contract for {name}")
        covered.add(name)
    if covered != THEOREMS:
        raise ValueError(f"statement contracts do not match the theorem list: "
                         f"missing {sorted(THEOREMS - covered)}, extra {sorted(covered - THEOREMS)}")
    # Every top-level definition of the model files must be restated in a definition pin
    # (`example ... := rfl`), so a changed definition cannot silently change a statement.
    defined: set[str] = set()
    for name in MODEL_FILES:
        defined |= set(DEFINITION.findall(_strip_comments((directory / name).read_text(encoding="utf-8"))))
    blocks = PIN.findall(code)
    pins = " ".join(blocks)
    pinned = {head for block in blocks if (head := _pinned_head(block))}
    if not defined or defined - pinned:
        raise ValueError(f"model definitions without an rfl pin in Contracts.lean: {sorted(defined - pinned)}")
    if "DAG.nil" not in pins or not all(f"DAG.{c}" in pins for c in ("input", "andGate", "xorGate")):
        raise ValueError("the DAG constructors must be restated in Contracts.lean")
    return covered


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[2] != "--sources":
        raise SystemExit("usage: python tools/check_formal_axioms.py LOG --sources DIR")
    validate_sources(Path(sys.argv[3]))
    validate_contracts(Path(sys.argv[3]))
    validate_report(Path(sys.argv[1]).read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
