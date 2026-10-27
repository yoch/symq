import pytest

from symq import Circuit, UnsupportedOperation
from symq.qasm import QasmSyntaxError, parse_qasm

QASM3 = """// i 0 1 2 3
// o 0 1 2 3
OPENQASM 3.0;
include "stdgates.inc";
qubit[4] q;
x q[0];
cx q[0], q[1];  // trailing comment
ccx q[0], q[1], q[2];
ctrl(3) @ x q[0], q[1], q[2], q[3];
ctrl @ cx q[3], q[0], q[1];
"""


def test_qasm3_subset_is_normalized():
    circuit = parse_qasm(QASM3)
    expected = Circuit(4).x(0).cx(0, 1).ccx(0, 1, 2).mcx(0, 1, 2, 3).ccx(3, 0, 1)
    assert circuit == expected


def test_qasm2_and_mcx():
    text = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg r[3];\nmcx r[2], r[1], r[0];\n/* c */ x r[1];'
    assert parse_qasm(text) == Circuit(3).ccx(2, 1, 0).x(1)


@pytest.mark.parametrize(
    "statement",
    [
        "h q[0];",
        "ctrl @ U(pi/2,-pi/2,pi/2) q[0], q[1];",
        "negctrl @ x q[0], q[1];",
        "inv @ x q[0];",
        "measure q[0];",
        "barrier q[0], q[1];",
        "x q;",
        "qubit[2] r;",
        "bit[2] c;",
    ],
)
def test_out_of_model_statements_rejected(statement):
    with pytest.raises(UnsupportedOperation):
        parse_qasm(f"OPENQASM 3.0;\nqubit[2] q;\n{statement}\n")


@pytest.mark.parametrize("header", ["// i 1 0", "// o 0 2 1"])
def test_nontrivial_permutation_annotations_rejected(header):
    with pytest.raises(UnsupportedOperation, match="permutation"):
        parse_qasm(f"{header}\nOPENQASM 3.0;\nqubit[3] q;\nx q[0];\n")


@pytest.mark.parametrize(
    "text",
    [
        "OPENQASM 3.0;\nqubit[2] q;\ncx q[0];",
        "OPENQASM 3.0;\nqubit[2] q;\ncx q[0], p[1];",
        "OPENQASM 3.0;\nqubit[2] q;\nx q[0]",
        "OPENQASM 3.0;",
    ],
)
def test_syntax_errors(text):
    with pytest.raises(QasmSyntaxError):
        parse_qasm(text)


def test_out_of_range_qubit_rejected():
    with pytest.raises(ValueError, match="out of range"):
        parse_qasm("OPENQASM 3.0;\nqubit[2] q;\nx q[2];")
