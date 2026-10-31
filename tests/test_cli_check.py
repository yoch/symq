"""``symq check``, ``symq anf`` and ``symq --version``: classical circuits from the command line."""
from __future__ import annotations

import json

import pytest

from symq import __version__
from symq.__main__ import main

QASM_IDENTITY = """OPENQASM 2.0;
include "qelib1.inc";
qreg q[3];
ccx q[0],q[1],q[2];
ccx q[0],q[1],q[2];
"""


@pytest.fixture()
def files(tmp_path):
    (tmp_path / "identity.qasm").write_text(QASM_IDENTITY)
    (tmp_path / "toffoli.json").write_text(json.dumps({"width": 3, "gates": [["ccx", [0, 1, 2]]]}))
    (tmp_path / "empty.json").write_text(json.dumps({"width": 3, "gates": []}))
    return tmp_path


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize("engine", ["auto", "sparse", "zdd", "truthtable"])
def test_equivalent_circuits_exit_zero(files, engine, capsys):
    assert main(["check", str(files / "identity.qasm"), str(files / "empty.json"),
                 "--engine", engine]) == 0
    assert capsys.readouterr().out.startswith("equivalent")


def test_a_difference_exits_one_with_a_replayable_witness(files, capsys):
    from symq import Circuit

    assert main(["check", str(files / "identity.qasm"), str(files / "toffoli.json"),
                 "--json"]) == 1
    record = json.loads(capsys.readouterr().out)
    assert record["outcome"] == "different" and record["kind"] == "symq_classical_check"
    assert Circuit(3).run(record["witness"]) != Circuit(3).ccx(0, 1, 2).run(record["witness"])


@pytest.mark.sat
def test_sat_contract_from_the_command_line(files):
    left, right = str(files / "identity.qasm"), str(files / "toffoli.json")
    assert main(["check", left, right, "--engine", "sat", "--observe", "0,1"]) == 0
    assert main(["check", left, right, "--engine", "sat", "--observe", "0,1",
                 "--restore", "2"]) == 1


def test_a_contract_needs_the_sat_engine(files, capsys):
    assert main(["check", str(files / "identity.qasm"), str(files / "toffoli.json"),
                 "--observe", "0"]) == 3
    assert "--engine sat" in capsys.readouterr().err


def test_resource_exhaustion_is_inconclusive(files):
    assert main(["check", str(files / "identity.qasm"), str(files / "toffoli.json"),
                 "--engine", "zdd", "--max-nodes", "1"]) == 2


def test_anf_prints_readable_polynomials(files, capsys):
    assert main(["anf", str(files / "toffoli.json")]) == 0
    assert capsys.readouterr().out.splitlines() == ["y0 = x0", "y1 = x1", "y2 = x2 + x0*x1"]
    assert main(["anf", str(files / "toffoli.json"), "--wire", "2", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["outputs"] == {"2": [3, 4]}


def test_bad_inputs_exit_three(files, tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps({"width": 2, "gates": [["h", [0]]]}))
    assert main(["check", str(tmp_path / "bad.json"), str(files / "empty.json")]) == 3
    assert main(["check", str(files / "identity.qasm"), str(tmp_path / "missing.qasm")]) == 3
    assert main(["anf", str(files / "toffoli.json"), "--wire", "7"]) == 3


def test_anf_string_form():
    from symq import ANF

    assert str(ANF()) == "0"
    assert str(ANF.constant(1)) == "1"
    assert str(ANF.variable(2) ^ ANF.constant(1) ^ (ANF.variable(0) * ANF.variable(1))) == \
        "1 + x2 + x0*x1"


def test_kickmix_files_are_accepted(tmp_path, capsys):
    from pathlib import Path

    corpus = Path(__file__).resolve().parents[1] / "benchmarks" / "corpus" / "kickmix"
    (tmp_path / "inc3.json").write_text(json.dumps(
        {"width": 3, "gates": [["ccx", [0, 1, 2]], ["cx", [0, 1]], ["x", [0]]]}))
    assert main(["check", str(corpus / "inc3.kmx"), str(tmp_path / "inc3.json")]) == 0
    assert main(["check", str(corpus / "inc8.kmx"), str(tmp_path / "inc3.json")]) == 3
    assert "to_phase_program" in capsys.readouterr().err


def test_circuit_counts():
    from symq import Circuit

    counts = Circuit(5).x(0).cx(0, 1).ccx(0, 1, 2).ccx(1, 2, 3).mcx(0, 1, 2, 4).counts()
    assert counts == {"ccx": 2, "cx": 1, "mcx": 1, "x": 1, "toffoli_like": 2, "multi_controlled": 1}


def test_auto_engine_picks_the_affine_backend_for_wide_cx_circuits(tmp_path, capsys):
    gates = [["cx", [q, q + 1]] for q in range(299)]
    left = {"width": 300, "gates": gates + gates[::-1]}
    (tmp_path / "left.json").write_text(json.dumps(left))
    (tmp_path / "right.json").write_text(json.dumps({"width": 300, "gates": []}))
    assert main(["check", str(tmp_path / "left.json"), str(tmp_path / "right.json"),
                 "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["engine"] == "linear"


def test_auto_engine_keeps_a_zdd_engine_for_toffoli_circuits(files, capsys):
    assert main(["check", str(files / "identity.qasm"), str(files / "empty.json"),
                 "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["engine"] in {"zdd-native", "zdd"}


def test_order_is_refused_for_engines_without_one(files, capsys):
    assert main(["check", str(files / "identity.qasm"), str(files / "empty.json"),
                 "--engine", "sparse", "--order", "reversed"]) == 3
    assert "--order" in capsys.readouterr().err
