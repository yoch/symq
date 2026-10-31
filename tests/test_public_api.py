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
    from symq.experimental.classical_transcript import TranscriptMismatch, UnprovedSubstitution
    from symq.experimental.ledger import UnresolvedPhaseDebt
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
