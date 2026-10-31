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


_LABS_MOVES = {
    "classical_transcript": "classical_transcript", "composition": "channel_composition",
    "cyclotomic": "cyclotomic", "importers": "importers", "ledger": "ledger",
    "phase": "dyadic_phase", "proof_graph": "proof_graph", "qasm3": "qasm3",
    "qcec": "qcec_adapter", "qualtran": "qualtran", "rename": "rename",
}


@pytest.mark.parametrize(("old", "new"), sorted(_LABS_MOVES.items()))
def test_moved_research_modules_keep_a_deprecated_alias(old, new):
    code = (
        "import importlib, warnings\n"
        "warnings.simplefilter('error', DeprecationWarning)\n"
        f"labs = importlib.import_module('symq.labs.{new}')\n"
        "try:\n"
        f"    importlib.import_module('symq.experimental.{old}')\n"
        "except DeprecationWarning as warning:\n"
        f"    assert 'symq.labs.{new}' in str(warning)\n"
        "else:\n"
        "    raise SystemExit('no DeprecationWarning')\n"
        "warnings.simplefilter('ignore', DeprecationWarning)\n"
        f"assert importlib.import_module('symq.experimental.{old}') is labs\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          check=False)
    assert done.returncode == 0, done.stderr + done.stdout


_RENAMED = [
    ("symq.labs.dyadic_phase", "PhaseProgram", "DyadicPhaseProgram"),
    ("symq.labs.dyadic_phase", "PhaseGate", "DyadicGate"),
    ("symq.labs.dyadic_phase", "PhaseVerdict", "DyadicVerdict"),
    ("symq.labs.dyadic_phase", "check_equivalence", "check_dyadic_equivalence"),
    ("symq.labs.dyadic_phase", "Program8", "DyadicPhaseProgram"),
    ("symq.labs.dyadic_phase", "Gate8", "DyadicGate"),
    ("symq.labs.dyadic_phase", "Verdict8", "DyadicVerdict"),
    ("symq.labs.dyadic_phase", "Symbolic8", "SymbolicPhase"),
    ("symq.labs.dyadic_phase", "Poly8", "Poly"),
    ("symq.experimental.contracts", "BACKENDS", "CONTRACT_BACKENDS"),
]


@pytest.mark.parametrize(("module", "old", "new"), _RENAMED)
def test_renamed_names_keep_a_deprecated_alias(module, old, new):
    import importlib

    target = importlib.import_module(module)
    with pytest.warns(DeprecationWarning, match=new):
        value = getattr(target, old)
    assert value is getattr(target, new)
    assert not hasattr(target, "no_such_name")


def test_old_dyadic_import_path_still_resolves_renamed_names():
    code = (
        "import warnings\n"
        "warnings.simplefilter('ignore', DeprecationWarning)\n"
        "from symq.experimental.phase import PhaseProgram, check_equivalence\n"
        "from symq.labs.dyadic_phase import DyadicPhaseProgram, check_dyadic_equivalence\n"
        "assert PhaseProgram is DyadicPhaseProgram\n"
        "assert check_equivalence is check_dyadic_equivalence\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          check=False)
    assert done.returncode == 0, done.stderr + done.stdout


def test_check_full_channel_is_a_deprecated_wrapper():
    from symq.experimental.channel import check_channel, check_full_channel
    from symq.phase import PhaseProgram

    left, right = PhaseProgram(1), PhaseProgram(1)
    left.mcz(0)
    right.mcz(0)
    with pytest.warns(DeprecationWarning, match="check_channel"):
        verdict = check_full_channel(left, right, backend="zdd")
    expected = check_channel(left, right, backend="zdd")
    assert (verdict.equivalent, verdict.theorem, verdict.left_sha256) == (
        expected.equivalent, expected.theorem, expected.left_sha256)


def test_nothing_outside_labs_imports_labs():
    from pathlib import Path

    root = Path(symq.__file__).parent
    offenders = [str(path.relative_to(root)) for path in root.rglob("*.py")
                 if path.parent.name != "labs" and path.stem not in _LABS_MOVES
                 and "symq.labs" in path.read_text(encoding="utf-8")]
    assert offenders == []
