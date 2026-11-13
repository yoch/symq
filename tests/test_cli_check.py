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


@pytest.mark.parametrize("flag", ["--max-nodes", "--max-terms"])
@pytest.mark.parametrize("contract", [[], ["--observe", "0,1", "--restore", "2"]])
@pytest.mark.parametrize("output", [[], ["--json"]])
def test_sat_refuses_unsupported_symbolic_budgets(files, capsys, flag, contract, output):
    """A requested cap must not disappear before the verifier checks its eligibility."""
    assert main(["check", str(files / "toffoli.json"), str(files / "toffoli.json"),
                 "--engine", "sat", flag, "1", *contract, *output]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "sat cannot enforce symbolic term/node budgets" in captured.err


@pytest.mark.sat
@pytest.mark.parametrize("contract", [[], ["--observe", "0,1", "--restore", "2"]])
@pytest.mark.parametrize("output", [[], ["--json"]])
def test_sat_accepts_a_timeout_without_symbolic_budgets(files, capsys, contract, output):
    assert main(["check", str(files / "identity.qasm"), str(files / "empty.json"),
                 "--engine", "sat", "--timeout", "5", *contract, *output]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    if output:
        assert json.loads(captured.out)["outcome"] == "equivalent"
    else:
        assert captured.out.startswith("equivalent")


@pytest.mark.parametrize("engine", ["sat", "qcec"])
@pytest.mark.parametrize("flag", ["--max-nodes", "--max-terms"])
def test_unsupported_budgets_are_refused_before_reading_the_inputs(tmp_path, capsys, engine,
                                                                   flag):
    # The files do not exist: the refusal depends on the flags alone and comes first.
    assert main(["check", str(tmp_path / "missing.json"), str(tmp_path / "missing.json"),
                 "--engine", engine, flag, "1", "--json"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""  # documented: usage errors print nothing on stdout
    assert f"{engine} cannot enforce symbolic term/node budgets" in captured.err


def test_auto_and_symbolic_engines_still_accept_symbolic_budgets(files, capsys):
    for engine in ("auto", "zdd", "python"):
        assert main(["check", str(files / "toffoli.json"), str(files / "toffoli.json"),
                     "--engine", engine, "--max-nodes", "1000", "--max-terms", "1000"]) == 0
    capsys.readouterr()


def test_a_contract_needs_the_sat_engine(files, capsys):
    assert main(["check", str(files / "identity.qasm"), str(files / "toffoli.json"),
                 "--observe", "0"]) == 3
    assert "--engine sat" in capsys.readouterr().err


@pytest.mark.parametrize("arguments", [
    ["check"], ["check", "only-one.json"], ["frobnicate"], ["check", "a", "b", "--timeout", "soon"],
    ["anf"], ["doctor", "--no-such-option"], [],
])
def test_a_usage_error_exits_with_3_not_with_the_inconclusive_code(arguments, capsys):
    """argparse exits with 2 by default, which here means "inconclusive"."""
    with pytest.raises(SystemExit) as exit_info:
        main(arguments)
    assert exit_info.value.code == 3
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize(("error", "code"), [
    (RuntimeError("boom"), 4), (AssertionError("boom"), 4), (ZeroDivisionError("boom"), 4),
    (RecursionError("boom"), 4), (MemoryError(), 2), (OverflowError("too large"), 3),
])
@pytest.mark.parametrize("command", ["check", "anf", "doctor"])
def test_no_failure_of_the_program_exits_with_the_code_of_a_proved_difference(
        files, monkeypatch, capsys, command, error, code):
    """Python exits with 1 after an uncaught exception, and 1 means "different" here."""
    import symq.__main__ as cli
    import symq.doctor

    def crash(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "_check", crash)
    monkeypatch.setattr(cli, "_anf", crash)
    monkeypatch.setattr(symq.doctor, "doctor", crash)
    arguments = {"check": ["check", str(files / "toffoli.json"), str(files / "empty.json")],
                 "anf": ["anf", str(files / "toffoli.json")], "doctor": ["doctor"]}[command]
    assert main(arguments) == code != 1
    captured = capsys.readouterr()
    assert captured.out == ""  # nothing that could be parsed as a result
    if code == 4:
        assert "internal error" in captured.err and "Traceback" in captured.err


def test_an_internal_inconsistency_is_not_reported_as_a_difference(files, monkeypatch):
    """A detected engine defect must stop the command, not look like a verdict."""
    import symq.facade
    from symq import InternalInconsistency

    def verify(*args, **kwargs):
        raise InternalInconsistency("replayed witness does not separate the circuits")

    monkeypatch.setattr(symq.facade, "verify", verify)
    assert main(["check", str(files / "toffoli.json"), str(files / "empty.json")]) == 4


def test_anf_out_of_budget_speaks_the_format_it_was_asked_for(files, capsys):
    arguments = ["anf", str(files / "toffoli.json"), "--max-nodes", "1"]
    assert main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "inconclusive" in captured.err
    assert main([*arguments, "--json"]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data["schema_version"] == 1 and data["kind"] == "symq_anf"
    assert data["outcome"] == "inconclusive" and "nodes limit" in data["reason"]


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


def test_a_kmx_file_outside_the_closed_grammar_is_an_input_error(tmp_path, capsys):
    (tmp_path / "bad.kmx").write_text("X q0\nX_IF q1\n")
    (tmp_path / "id.json").write_text(json.dumps({"width": 2, "gates": []}))
    assert main(["check", str(tmp_path / "bad.kmx"), str(tmp_path / "id.json")]) == 3
    assert "line 2" in capsys.readouterr().err


def test_input_errors_name_the_file_and_kmb_is_refused_clearly(tmp_path, capsys):
    from symq.circuit import load_circuit
    from symq.errors import UnsupportedOperation

    good = tmp_path / "good.json"
    good.write_text('{"width": 1, "gates": [["x", [0]]]}')
    broken = tmp_path / "broken.json"
    broken.write_text('{"width": 1}')
    assert main(["check", str(good), str(broken)]) == 3
    assert "broken.json" in capsys.readouterr().err
    for name in ("a.kmb", "A.KMB"):
        (tmp_path / name).write_bytes(b"\xd7\x50\xc7\xd5")
        with pytest.raises(UnsupportedOperation, match="binary .kmb format"):
            load_circuit(str(tmp_path / name))
