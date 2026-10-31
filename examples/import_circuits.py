"""Import OpenQASM and Qualtran kickmix circuits, then verify them."""
from pathlib import Path

from symq import PhaseProgram, check_equivalence, check_phase_equivalence, parse_qasm
from symq.kickmix import load_kmx

QASM = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
ccx q[0],q[1],q[2];
cx q[0],q[1];
x q[0];
"""
corpus = Path(__file__).resolve().parents[1] / "benchmarks" / "corpus" / "kickmix"

# The same 3-bit increment written in OpenQASM and in kickmix text.
from_qasm = parse_qasm(QASM)
from_kmx = load_kmx(corpus / "inc3.kmx").to_circuit()
print("QASM == kickmix:", check_equivalence(from_qasm, from_kmx).equivalent)

# A measurement-based increment (HMR + conditional CZ corrections) against the textbook one.
inc8 = load_kmx(corpus / "inc8.kmx")
print("inc8 operations:", inc8.counts())
textbook = PhaseProgram(8, 0)
for i in range(7, 0, -1):
    textbook.mcx(*range(i), i)
textbook.x(0)
verdict = check_phase_equivalence(inc8.to_phase_program(data=range(8)), textbook)
print("inc8 == MCX increment:", verdict.equivalent)
