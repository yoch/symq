"""MQT QCEC adapter: equivalence of two circuits as quantum circuits (unitaries).

An X/CX/MCX circuit is a permutation matrix, so its unitary determines exactly the classical
function compared by ``symq.check_equivalence``. Up to a global phase, two permutation matrices
are equal only when they are identical. QCEC gives verdicts, not polynomials:
symbolic simulation is not applicable. Requires ``mqt.qcec``.
"""
from __future__ import annotations

from dataclasses import dataclass

from mqt import qcec
from mqt.core.ir import QuantumComputation

from ..circuit import Circuit

CONFIGURATION = {
    "run_alternating_checker": True,
    "run_simulation_checker": False,
    "run_zx_checker": False,
    "run_construction_checker": False,
    "parallel": False,
}
"""Only the complete decision-diagram alternating checker: no random simulations and no ZX
rewriting, so every conclusive verdict is a proof."""

CONCLUSIVE = {"equivalent": True, "equivalent_up_to_global_phase": True, "not_equivalent": False}


@dataclass(frozen=True)
class QcecResult:
    verdict: str
    """QCEC's ``EquivalenceCriterion`` name."""
    equivalent: bool | None
    """``None`` when the verdict is not a proof (``probably_*``, ``no_information``, …)."""
    check_seconds: float
    preprocessing_seconds: float


def to_quantum_computation(circuit: Circuit) -> QuantumComputation:
    qc = QuantumComputation(circuit.width)
    for gate in circuit.gates:
        *controls, target = gate.qubits
        if not controls:
            qc.x(target)
        elif len(controls) == 1:
            qc.cx(controls[0], target)
        else:
            qc.mcx(set(controls), target)
    return qc


def qcec_check(left: Circuit, right: Circuit, *, timeout: float = 0.0) -> QcecResult:
    """Run QCEC on two circuits of equal width; ``timeout`` in seconds, 0 for none."""
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    result = qcec.verify(
        to_quantum_computation(left), to_quantum_computation(right),
        timeout=timeout, **CONFIGURATION,
    )
    verdict = result.equivalence.name
    return QcecResult(verdict, CONCLUSIVE.get(verdict), result.check_time,
                      result.preprocessing_time)
