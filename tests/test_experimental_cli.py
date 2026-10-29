from __future__ import annotations

import json
import subprocess
import sys

import pytest

from symq.__main__ import main
from symq.experimental import VerificationContract
from symq.experimental.serialization import save_contract, save_program
from symq.phase import PhaseProgram


@pytest.fixture
def documents(tmp_path):
    reference = PhaseProgram(2, 1)
    candidate = PhaseProgram(2, 1).ccx(0, 1, 2)
    event = candidate.hmr(2)
    candidate.cz_if(event, 0, 1)
    mutant = PhaseProgram(2, 1).ccx(0, 1, 2)
    mutant.hmr(2)
    for name, program in (("reference", reference), ("candidate", candidate), ("mutant", mutant)):
        save_program(program, tmp_path / f"{name}.json")
    save_contract(VerificationContract(theorem="full_channel", backend="zdd"),
                  tmp_path / "contract.json")
    return tmp_path


def test_cli_verify_and_replay_bind_complete_sources_and_contract(documents, capsys):
    artifact = documents / "result.json"
    assert main(["verify", str(documents / "reference.json"), str(documents / "candidate.json"),
                 "--contract", str(documents / "contract.json"), "--report", str(artifact)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["result"]["outcome"] == "equivalent"
    assert main(["replay", str(artifact)]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "equality_recomputed"
    report["reference"]["ops"] = [{"kind": "mcx", "qubits": [0], "outcome": None}]
    artifact.write_text(json.dumps(report))
    assert main(["replay", str(artifact)]) == 3
    assert "hash mismatch" in capsys.readouterr().err


def test_cli_mutant_replays_an_off_diagonal_witness(documents, capsys):
    artifact = documents / "difference.json"
    assert main(["verify", str(documents / "reference.json"), str(documents / "mutant.json"),
                 "--theorem", "full-channel", "--engine", "python", "--report", str(artifact)]) == 1
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["witness"][0] != result["witness"][1]
    assert main(["replay", str(artifact)]) == 1
    assert json.loads(capsys.readouterr().out)["mode"] == "witness_replayed"


def test_cli_inspection_is_not_an_equivalence_claim(documents, capsys):
    assert main(["inspect", str(documents / "candidate.json"), "--other",
                 str(documents / "reference.json"), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == "symq_capabilities"
    assert all("outcome" not in entry for entry in report["engines"])


def test_cli_profile_uses_same_verifier_and_exports_html(documents, capsys):
    html = documents / "profile.html"
    assert main(["profile", str(documents / "reference.json"),
                 str(documents / "candidate.json"), "--contract", str(documents / "contract.json"),
                 "--no-isolate", "--html", str(html)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["result"]["outcome"] == "equivalent"
    assert report["timing"]["sum_stage_seconds"] == pytest.approx(
        report["timing"]["whole_call_wall_seconds"])
    assert "independent proof certificate" in html.read_text()


def test_cli_isolation_and_explicit_contract_conflict(documents, capsys):
    common = ["verify", str(documents / "reference.json"), str(documents / "candidate.json"),
              "--contract", str(documents / "contract.json")]
    assert main(common + ["--isolate"]) == 0
    assert json.loads(capsys.readouterr().out)["execution"]["exitcode"] == 0
    assert main(common + ["--engine", "native"]) == 3
    assert "conflicts" in capsys.readouterr().err


def test_late_report_serialization_withdraws_decisive_artifact(documents, capsys, monkeypatch):
    from symq import resources
    from symq.experimental import serialization
    clock = [0.0]
    monkeypatch.setattr(resources.time, "perf_counter", lambda: clock[0])
    save = serialization.save_json

    def delayed_save(value, path):
        save(value, path)
        clock[0] = 2.0

    monkeypatch.setattr(serialization, "save_json", delayed_save)
    artifact = documents / "late.json"
    assert main(["verify", str(documents / "reference.json"), str(documents / "candidate.json"),
                 "--contract", str(documents / "contract.json"), "--timeout", "1",
                 "--report", str(artifact)]) == 2
    assert json.loads(capsys.readouterr().out)["outcome"] == "inconclusive"
    assert json.loads(artifact.read_text())["result"]["outcome"] == "inconclusive"


def test_module_cli_profile_uses_importable_spawn_target(documents):
    run = subprocess.run(
        [sys.executable, "-m", "symq", "profile", str(documents / "reference.json"),
         str(documents / "candidate.json"), "--contract", str(documents / "contract.json")],
        cwd=documents, capture_output=True, text=True, check=False, timeout=10,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["result"]["outcome"] == "equivalent"
