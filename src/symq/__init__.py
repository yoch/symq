"""symq: exact Boolean ANF and classical reversible circuits (experimental).

The names below are the supported entry points. Heavier ones (the SAT engine and the explicit
verification facade) are imported on first access, so ``import symq`` stays cheap.
"""
from importlib import metadata as _metadata
from typing import Any

from .anf import ANF
from .backends import BACKENDS, has_native, make_algebra, simulate
from .circuit import Circuit, Gate
from .equivalence import EquivalenceResult, check_equivalence, check_equivalence_by_blocks
from .errors import (
    InternalInconsistency,
    QasmSyntaxError,
    ResourceLimitExceeded,
    SatUnavailable,
    SymqError,
    UnsupportedOperation,
)
from .order import POLICIES, algebra_order, order_for
from .phase import PhaseProgram, check_phase_equivalence, phase_semantics
from .qasm import load_qasm, parse_qasm
from .resources import Budget
from .strategy import Choice, choose, features

try:
    __version__ = _metadata.version("symq")
except _metadata.PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0+unknown"

_LAZY = {
    "check_sat_equivalence": ("symq.sat", "check_sat_equivalence"),
    "SatVerdict": ("symq.sat", "SatVerdict"),
    "verify_explicit": ("symq.verification", "verify_explicit"),
    "VerificationRecord": ("symq.verification", "VerificationRecord"),
    "verify": ("symq.facade", "verify"),
    "Verdict": ("symq.facade", "Verdict"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY[name]
    except KeyError:
        raise AttributeError(f"module 'symq' has no attribute {name!r}") from None
    from importlib import import_module

    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "ANF",
    "BACKENDS",
    "POLICIES",
    "Budget",
    "Choice",
    "Circuit",
    "EquivalenceResult",
    "Gate",
    "InternalInconsistency",
    "PhaseProgram",
    "QasmSyntaxError",
    "ResourceLimitExceeded",
    "SatUnavailable",
    "SatVerdict",
    "SymqError",
    "UnsupportedOperation",
    "Verdict",
    "VerificationRecord",
    "__version__",
    "algebra_order",
    "check_equivalence",
    "check_equivalence_by_blocks",
    "check_phase_equivalence",
    "check_sat_equivalence",
    "choose",
    "features",
    "has_native",
    "load_qasm",
    "make_algebra",
    "order_for",
    "parse_qasm",
    "phase_semantics",
    "simulate",
    "verify",
    "verify_explicit",
]
