"""``symq rewrite`` and ``symq replay`` on rewrite reports: requests, exit codes, tampering."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from symq import Circuit
from symq.__main__ import main
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.channel_composition import HybridFragment
from symq.labs.rewrite_request import candidate_stream, fragment_to_dict

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "rewrite"
pytestmark = pytest.mark.sat


def _example(tmp_path: Path, **changes) -> Path:
    for name in ("source.qasm", "replacement.json"):
        shutil.copy(EXAMPLE / name, tmp_path / name)
    request = json.loads((EXAMPLE / "request.json").read_text())
    request.update(changes)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    return path


def _run(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    return code, (json.loads(captured.out) if captured.out.strip() else None), captured.err


def test_classical_request_is_proved_once_applied_and_replayed(tmp_path, capsys):
    request = _example(tmp_path)
    code, out, _ = _run(["rewrite", str(request), "--report", str(tmp_path / "r.json")], capsys)
    assert code == 0 and out["application"] == "applied"
    assert out["result"]["theorem"] == "classical_contextual_full"
    report = json.loads((tmp_path / "r.json").read_text())
    assert set(report["file_sha256"]) == {"request", "source", "replacement"}
    source, candidate = Circuit(5).cx(0, 4).cx(0, 4).mcx(0, 1, 2, 3).cx(3, 0), \
        candidate_stream(report)
    assert all(candidate.run(x) == source.run(x) for x in range(32) if not x >> 4 & 1)
    assert report["result"]["cost"]["weighted_delta"] == -4  # mcx 10 -> 3 x ccx 2
    for name in ("source.qasm", "replacement.json", "request.json"):
        (tmp_path / name).unlink()  # replay needs only the self-contained report
    code, out, _ = _run(["replay", str(tmp_path / "r.json")], capsys)
    assert code == 0 and out["mode"] == "rewrite_recomputed"
    assert out["replayed"]["stored_outcome"] == "equivalent"


def test_an_unestablished_cut_is_exit_2_and_never_applied(tmp_path, capsys):
    request = _example(tmp_path, contract={"clean_at_cut": [4]})
    code, out, _ = _run(["rewrite", str(request)], capsys)
    assert code == 2
    assert out["result"]["outcome"] == "precondition_failed"
    assert out["application"] == "not_proved"


def test_a_cut_assumption_is_proved_not_assumed(tmp_path, capsys):
    assumption = {"kind": "not", "operand": {"kind": "var", "name": "u.4"}}
    request = _example(tmp_path, contract={"cut_assumption": assumption, "clean_at_cut": []})
    code, out, _ = _run(["rewrite", str(request)], capsys)
    assert code == 2 and out["result"]["outcome"] == "precondition_failed"
    request = _example(tmp_path, contract={"cut_assumption": assumption,
                                           "initial_constants": [[4, 0]]})
    code, out, _ = _run(["rewrite", str(request)], capsys)
    assert code == 0 and out["application"] == "applied"


def test_edited_reports_are_refused_and_a_slow_replay_is_inconclusive(tmp_path, capsys):
    request = _example(tmp_path)
    report_path = tmp_path / "r.json"
    assert _run(["rewrite", str(request), "--report", str(report_path)], capsys)[0] == 0
    report = json.loads(report_path.read_text())
    edits = {
        "pinned hash": lambda r: r["result"].update(candidate_sha256="0" * 64),
        "cost": lambda r: r["result"]["cost"].update(candidate_weighted=-1),
        "candidate": lambda r: r["candidate"]["gates"].append(["x", [0]]),
    }
    for edit in edits.values():
        edited = json.loads(json.dumps(report))
        edit(edited)
        report_path.write_text(json.dumps(edited))
        code, _, err = _run(["replay", str(report_path)], capsys)
        assert code == 3, err
        assert "does not describe" in err or "not the stream the checker proved" in err
    report_path.write_text(json.dumps(report))
    code, _out, _ = _run(["replay", str(report_path), "--timeout", "1e-9"], capsys)
    assert code == 2  # a timeout is inconclusive, not tampering


def test_input_errors_are_exit_3(tmp_path, capsys):
    request = _example(tmp_path)
    assert _run(["rewrite", str(request), "--report", str(request)], capsys)[0] == 3
    assert _run(["rewrite", str(request), "--report", str(tmp_path / "source.qasm")],
                capsys)[0] == 3
    bad = _example(tmp_path, contract={"unknown": 1})
    assert _run(["rewrite", str(bad)], capsys)[0] == 3
    bad = _example(tmp_path, contract={"cut_assumption": {"kind": "or"}})
    assert _run(["rewrite", str(bad)], capsys)[0] == 3
    bad = _example(tmp_path, source="../outside.qasm")
    assert _run(["rewrite", str(bad)], capsys)[0] == 3
    bad = _example(tmp_path, theorem="unitary")
    assert _run(["rewrite", str(bad)], capsys)[0] == 3
    # The theorem is checked before the files are parsed, so the error names the real problem.
    bad = _example(tmp_path, theorem="Classical")
    code, _, err = _run(["rewrite", str(bad)], capsys)
    assert code == 3 and "theorem must be one of" in err


def test_isolated_input_errors_are_exit_3_too(tmp_path, capsys):
    bad = _example(tmp_path, span=[2, 99])
    assert _run(["rewrite", str(bad)], capsys)[0] == 3
    code, _, err = _run(["rewrite", str(bad), "--isolate"], capsys)
    assert code == 3 and "span" in err


def test_a_candidate_on_a_report_that_applied_nothing_is_refused(tmp_path, capsys):
    request = _example(tmp_path)
    path = tmp_path / "r.json"
    _run(["rewrite", str(request), "--report", str(path)], capsys)
    proved = json.loads(path.read_text())
    for edit in ({"application": "refused_by_cost_policy"},
                 {"result": {**proved["result"], "outcome": "not_proved"}}):
        edited = {**proved, **edit}
        assert candidate_stream(edited) is None
        path.write_text(json.dumps(edited))
        assert _run(["replay", str(path)], capsys)[0] == 3


def test_replay_refuses_non_objects_and_honours_or_refuses_every_limit(tmp_path, capsys):
    listing = tmp_path / "list.json"
    listing.write_text("[]")
    assert _run(["replay", str(listing)], capsys)[0] == 3
    request = _example(tmp_path)
    path = tmp_path / "r.json"
    _run(["rewrite", str(request), "--report", str(path)], capsys)
    # The SAT theorem cannot enforce a term limit: it is refused, not silently ignored.
    code, _, err = _run(["replay", str(path), "--max-terms", "1000"], capsys)
    assert code == 3 and "SAT cannot enforce" in err


def test_the_pinned_digests_are_those_of_the_proved_files(tmp_path):
    import hashlib

    from symq.labs.rewrite_request import load_request
    from symq.qasm import load_qasm

    request_path = _example(tmp_path)
    request, digests = load_request(request_path)
    for key, name in (("request", "request.json"), ("source", "source.qasm"),
                      ("replacement", "replacement.json")):
        assert digests[key] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    assert request.source.gates == load_qasm(tmp_path / "source.qasm").gates


def test_isolated_mode_records_the_execution(tmp_path, capsys):
    request = _example(tmp_path)
    report = tmp_path / "r.json"
    code, out, _ = _run(["rewrite", str(request), "--isolate", "--report", str(report)], capsys)
    assert code == 0 and out["application"] == "applied"
    assert json.loads(report.read_text())["execution"]["status"] == "completed"


def _coherent(tmp_path: Path, replacement_ops, *, contract=None, weights=None,
              require_saving=False) -> Path:
    ops = [HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)), HOp("ccx", (0, 1, 3))]
    (tmp_path / "source.json").write_text(json.dumps(program_to_dict(HybridProgram(3, 1, ops))))
    (tmp_path / "replacement.json").write_text(json.dumps(
        fragment_to_dict(HybridFragment(4, tuple(replacement_ops)))))
    request = {"schema_version": 1, "kind": "symq_rewrite_request", "theorem": "coherent",
               "source": "source.json", "replacement": "replacement.json", "span": [0, 3],
               "contract": contract or {"wires": [0, 1, 2, 3], "clean": [3]},
               "weights": weights or {"by_kind": [["ccx", 10], ["hmr", 0], ["cz", 2]]},
               "require_saving": require_saving}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    return path


TEMPORARY_AND = [HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)), HOp("hmr", (3,), slot="b0"),
                 HOp("cz", (0, 1), condition="b0")]


def test_coherent_request_measurement_based_uncompute(tmp_path, capsys):
    code, out, _ = _run(["rewrite", str(_coherent(tmp_path, TEMPORARY_AND)),
                         "--report", str(tmp_path / "r.json")], capsys)
    assert code == 0 and out["application"] == "applied"
    assert out["result"]["theorem"] == "local_coherent_channel"
    assert out["result"]["cost"]["weighted_delta"] == -8  # ccx priced 10, hmr 0, cz 2
    assert _run(["replay", str(tmp_path / "r.json")], capsys)[0] == 0


def test_a_missing_phase_correction_is_not_proved(tmp_path, capsys):
    code, out, _ = _run(["rewrite", str(_coherent(tmp_path, TEMPORARY_AND[:-1]))], capsys)
    assert code == 2 and out["result"]["outcome"] == "not_proved"
    assert out["application"] == "not_proved"


def test_an_unprepared_ancilla_is_not_assumed_clean(tmp_path, capsys):
    path = _coherent(tmp_path, TEMPORARY_AND, contract={"wires": [0, 1, 2, 3]})
    code, out, _ = _run(["rewrite", str(path)], capsys)
    assert code == 2 and out["application"] == "not_proved"


def test_the_cost_policy_can_refuse_a_proved_rewrite(tmp_path, capsys):
    path = _coherent(tmp_path, TEMPORARY_AND, weights={"by_kind": []}, require_saving=True)
    code, out, _ = _run(["rewrite", str(path)], capsys)
    assert code == 0 and out["result"]["outcome"] == "equivalent"
    assert out["application"] == "refused_by_cost_policy"


def test_coherent_oracle_bounds_are_capped(tmp_path, capsys):
    path = _coherent(tmp_path, TEMPORARY_AND,
                     contract={"wires": [0, 1, 2, 3], "clean": [3], "max_local_width": 9})
    assert _run(["rewrite", str(path)], capsys)[0] == 3
