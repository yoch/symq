"""Matched Z8-versus-MQT-QCEC unitary comparisons; QCEC remains OPTIONAL."""

import sys
from pathlib import Path

import pytest

qcec = pytest.importorskip("mqt.qcec")
QuantumComputation = pytest.importorskip("mqt.core.ir").QuantumComputation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "phase8"))

from phase8 import Program8, check_equivalence

CONFIG = {
    "run_alternating_checker": True,
    "run_simulation_checker": False,
    "run_zx_checker": False,
    "run_construction_checker": False,
    "parallel": False,
}

CONCLUSIVE = {
    "equivalent": True,
    "equivalent_up_to_global_phase": True,
    "not_equivalent": False,
}


def to_mqt(program):
    """Strict common subgrammar: no H, measurements, resets, extra ancillas."""
    program.validate()
    qc = QuantumComputation(program.width)
    for gate in program.gates:
        name, wires = gate.name, gate.wires
        if name in {"x", "t", "tdg", "s", "sdg", "z"}:
            getattr(qc, name)(wires[0])
        elif name in {"cx", "cz"}:
            getattr(qc, name)(wires[0], wires[1])
        elif name in {"ccx", "mcx"}:
            qc.mcx(set(wires[:-1]), wires[-1])
        else:
            raise ValueError(f"unsupported matched gate {name!r}")
    return qc


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (Program8(1).t(0).tdg(0), Program8(1)),
        (Program8(1).s(0).s(0), Program8(1).z(0)),
        (Program8(1).x(0).t(0).x(0).t(0), Program8(1)),
        (Program8(2).cx(0, 1).t(1), Program8(2).t(0).t(1).cx(0, 1)),
        (Program8(1).x(0).t(0), Program8(1).t(0).x(0)),
        (Program8(2).cx(0, 1).t(1).tdg(1), Program8(2).cx(0, 1)),
        (Program8(2).cz(0, 1), Program8(2).cz(0, 1).z(0).z(0)),
    ],
)
def test_matched_qcec_unitary_equivalence(left, right):
    local = check_equivalence(left, right)
    qresult = qcec.verify(to_mqt(left), to_mqt(right), timeout=10, **CONFIG)
    verdict = qresult.equivalence.name
    assert verdict in CONCLUSIVE, f"QCEC inconclusive: {verdict}"
    assert CONCLUSIVE[verdict] == (local.status in ("equal", "global_phase")), (
        verdict, local
    )
