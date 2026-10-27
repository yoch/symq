"""symq: exact Boolean ANF and classical reversible circuits (experimental)."""
from .anf import ANF
from .backends import BACKENDS, has_native, make_algebra, simulate
from .circuit import Circuit, Gate, UnsupportedOperation
from .equivalence import EquivalenceResult, InternalInconsistency, check_equivalence
from .phase import PhaseProgram, check_phase_equivalence, phase_semantics
from .resources import Budget, ResourceLimitExceeded

__all__ = [
    "ANF",
    "BACKENDS",
    "Budget",
    "Circuit",
    "EquivalenceResult",
    "Gate",
    "InternalInconsistency",
    "PhaseProgram",
    "ResourceLimitExceeded",
    "UnsupportedOperation",
    "check_equivalence",
    "check_phase_equivalence",
    "has_native",
    "make_algebra",
    "phase_semantics",
    "simulate",
]
