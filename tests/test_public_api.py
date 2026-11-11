"""The top-level ``symq`` namespace: every advertised name resolves, errors share one base."""
from __future__ import annotations

import subprocess
import sys

import pytest

import symq
from symq import errors


@pytest.mark.parametrize("name", symq.__all__)
def test_every_advertised_name_resolves(name):
    assert getattr(symq, name) is not None


def test_unknown_attributes_still_raise():
    with pytest.raises(AttributeError):
        symq.no_such_entry_point  # noqa: B018


def test_version_is_a_string():
    assert isinstance(symq.__version__, str) and symq.__version__


@pytest.mark.parametrize("name", errors.__all__)
def test_every_error_derives_from_symq_error(name):
    assert issubclass(getattr(errors, name), errors.SymqError)


@pytest.mark.parametrize(("name", "builtin"), [
    ("ResourceLimitExceeded", RuntimeError),
    ("InternalInconsistency", RuntimeError),
    ("SatUnavailable", RuntimeError),
    ("UnsupportedOperation", ValueError),
    ("QasmSyntaxError", ValueError),
])
def test_errors_keep_their_historical_builtin_base(name, builtin):
    """``except RuntimeError`` / ``except ValueError`` written before the hierarchy still work."""
    assert issubclass(getattr(errors, name), builtin)


def test_historical_import_locations_are_the_same_classes():
    from symq.circuit import UnsupportedOperation
    from symq.equivalence import InternalInconsistency
    from symq.qasm import QasmSyntaxError
    from symq.resources import ResourceLimitExceeded
    from symq.sat import SatUnavailable

    assert UnsupportedOperation is errors.UnsupportedOperation
    assert InternalInconsistency is errors.InternalInconsistency
    assert QasmSyntaxError is errors.QasmSyntaxError
    assert ResourceLimitExceeded is errors.ResourceLimitExceeded
    assert SatUnavailable is errors.SatUnavailable


def test_experimental_errors_join_the_hierarchy():
    from symq.experimental.channel import EmptyDomain
    from symq.labs.classical_transcript import TranscriptMismatch, UnprovedSubstitution
    from symq.labs.ledger import UnresolvedPhaseDebt
    from symq.sat.assumptions import ExprError

    for cls in (EmptyDomain, TranscriptMismatch, UnprovedSubstitution, UnresolvedPhaseDebt,
                ExprError):
        assert issubclass(cls, errors.SymqError) and issubclass(cls, ValueError)


def test_importing_symq_does_not_load_the_sat_engine_or_the_baselines():
    code = ("import sys, symq; "
            "print(sorted(m for m in ('symq.sat', 'symq.verification', 'symq.external', "
            "'pysat') if m in sys.modules))")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          check=True)
    assert done.stdout.strip() == "[]"


_REMOVED_MODULES = ("classical_transcript", "composition", "cyclotomic", "importers", "ledger",
                    "phase", "proof_graph", "qasm3", "qcec", "qualtran", "rename")


@pytest.mark.parametrize("name", _REMOVED_MODULES)
def test_research_modules_have_no_alias_under_experimental(name):
    """These paths were never in a released package: they left before the first release."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"symq.experimental.{name}")


_REMOVED_NAMES = [
    ("symq.labs.dyadic_phase", "PhaseProgram"), ("symq.labs.dyadic_phase", "PhaseGate"),
    ("symq.labs.dyadic_phase", "PhaseVerdict"), ("symq.labs.dyadic_phase", "check_equivalence"),
    ("symq.labs.dyadic_phase", "Program8"), ("symq.labs.dyadic_phase", "Gate8"),
    ("symq.labs.dyadic_phase", "Verdict8"), ("symq.labs.dyadic_phase", "Symbolic8"),
    ("symq.labs.dyadic_phase", "Poly8"), ("symq.experimental.contracts", "BACKENDS"),
    ("symq.experimental.channel", "check_full_channel"),
]


@pytest.mark.parametrize(("module", "name"), _REMOVED_NAMES)
def test_former_names_are_gone_without_a_silent_fallback(module, name):
    import importlib
    import warnings

    target = importlib.import_module(module)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert not hasattr(target, name)


# The only places outside ``symq.labs`` allowed to import it: the experimental CLI commands.
_LABS_IMPORTERS = {"__main__.py": {"_rewrite", "_replay_rewrite", "_locate",
                                    "_prepare_rewrite", "_kmx_window", "_kmb_window"}}


def _labs_imports(path, root):
    """``(enclosing function or None, line)`` for each import of ``symq.labs`` in ``path``."""
    import ast

    package = ["symq", *path.parent.relative_to(root).parts]
    found = []

    def visit(node, function):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, function or child.name)
                continue
            names = []
            if isinstance(child, ast.Import):
                names = [alias.name for alias in child.names]
            elif isinstance(child, ast.ImportFrom):
                base = package[:len(package) - child.level + 1] if child.level else []
                module = ".".join([*base, *(child.module or "").split(".")]).strip(".")
                names = [module] + [f"{module}.{alias.name}" for alias in child.names]
            if any(name == "symq.labs" or name.startswith("symq.labs.") for name in names):
                found.append((function, child.lineno))
            visit(child, function)

    visit(ast.parse(path.read_text(encoding="utf-8")), None)
    return found


def test_only_labs_and_the_labs_cli_commands_import_labs():
    from pathlib import Path

    root = Path(symq.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if relative.parts[0] == "labs":
            continue
        allowed = _LABS_IMPORTERS.get(str(relative), set())
        offenders += [f"{relative}:{line}" for function, line in _labs_imports(path, root)
                      if function not in allowed]
    assert offenders == []


def test_the_labs_import_guard_sees_relative_and_absolute_imports(tmp_path):
    root = tmp_path / "symq"
    (root / "sub").mkdir(parents=True)
    module = root / "sub" / "mod.py"
    module.write_text("from ..labs import rewrite\nimport symq.labs.ledger\n"
                      "def f():\n    from ..labs.rewrite import Weights\n"
                      "from ..resources import Budget\n")
    assert _labs_imports(module, root) == [(None, 1), (None, 2), ("f", 4)]


def test_the_cli_loads_labs_only_for_the_experimental_rewrite_command():
    """``symq rewrite`` imports labs lazily; importing the CLI module itself does not."""
    code = ("import sys, symq, symq.__main__; "
            "print(sorted(m for m in sys.modules if m.startswith('symq.labs')))")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          check=True)
    assert done.stdout.strip() == "[]"
