"""symq: exact Boolean ANF and classical reversible circuits (experimental)."""
from .anf import ANF
from .backends import BACKENDS, has_native, make_algebra, simulate
from .circuit import Circuit, Gate, UnsupportedOperation
from .equivalence import (
    EquivalenceResult,
    InternalInconsistency,
    check_equivalence,
    check_equivalence_by_blocks,
)
from .order import POLICIES, algebra_order, order_for
from .phase import PhaseProgram, check_phase_equivalence, phase_semantics
from .resources import Budget, ResourceLimitExceeded
from .strategy import Choice, choose, features

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
    "ResourceLimitExceeded",
    "UnsupportedOperation",
    "algebra_order",
    "check_equivalence",
    "check_equivalence_by_blocks",
    "check_phase_equivalence",
    "choose",
    "features",
    "has_native",
    "make_algebra",
    "order_for",
    "phase_semantics",
    "simulate",
]
