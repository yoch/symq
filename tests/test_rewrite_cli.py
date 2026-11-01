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
from symq.labs.rewrite import ReceiptMismatch
from symq.labs.rewrite_request import fragment_to_dict, replay_report, replayed_candidate

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
    provenance = report["provenance"]
    assert set(provenance["input_file_sha256"]) == {"request", "source", "replacement"}
    assert "not reverified" in provenance["status"]
    source, candidate = Circuit(5).cx(0, 4).cx(0, 4).mcx(0, 1, 2, 3).cx(3, 0), \
        replayed_candidate(report)
    assert all(candidate.run(x) == source.run(x) for x in range(32) if not x >> 4 & 1)
    assert report["result"]["cost"]["weighted_delta"] == -4  # mcx 10 -> 3 x ccx 2
    for name in ("source.qasm", "replacement.json", "request.json"):
        (tmp_path / name).unlink()  # replay needs only the self-contained report
    code, out, _ = _run(["replay", str(tmp_path / "r.json")], capsys)
    assert code == 0 and out["mode"] == "rewrite_recomputed"
    assert out["replay"] == {"reverified": True, "stored_outcome": "equivalent"}
    assert out["provenance"]["reverified"] is False


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
        assert "contradicts the recomputed proof" in err
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


def _proved_report(tmp_path, capsys) -> dict:
    request = _example(tmp_path)
    path = tmp_path / "r.json"
    assert _run(["rewrite", str(request), "--report", str(path)], capsys)[0] == 0
    return json.loads(path.read_text())


REPORT_EDITS = {
    "positive turned negative, candidate removed": lambda r: (
        r["result"].update(outcome="not_proved"),
        r.update(application="not_proved", candidate=None)),
    "outcome": lambda r: r["result"].update(outcome="precondition_failed"),
    "reason": lambda r: r["result"].update(reason="edited"),
    "obligation status": lambda r: r["result"]["obligations"][0].update(status="failed"),
    "obligation witness": lambda r: r["result"]["obligations"][0].update(witness=[1]),
    "application": lambda r: r.update(application="refused_by_cost_policy"),
    "candidate removed": lambda r: r.update(candidate=None),
    "candidate edited": lambda r: r["candidate"]["gates"].append(["x", [0]]),
    "extra null key in result": lambda r: r["result"].update(authorized=None),
    "theorem": lambda r: r["result"].update(theorem="classical_total"),
    "engine": lambda r: r["result"].update(engine="packed"),
    "request contract": lambda r: r["request"]["contract"].update(clean_at_cut=[]),
    "request span": lambda r: r["request"].update(span=[1, 3]),
}


@pytest.mark.parametrize("edit", REPORT_EDITS, ids=list(REPORT_EDITS))
def test_every_reverified_field_of_a_report_is_checked(tmp_path, capsys, edit):
    edited = _proved_report(tmp_path, capsys)
    REPORT_EDITS[edit](edited)
    with pytest.raises(ReceiptMismatch):
        replay_report(edited)
    with pytest.raises(ReceiptMismatch):
        replayed_candidate(edited)
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(edited))
    assert _run(["replay", str(path)], capsys)[0] == 3


def test_provenance_is_kept_apart_and_never_presented_as_verified(tmp_path, capsys):
    report = _proved_report(tmp_path, capsys)
    report["provenance"]["input_file_sha256"]["source"] = "0" * 64
    fresh = replay_report(report)
    assert fresh["replay"]["reverified"] is True
    assert fresh["provenance"] == {"reverified": False, "stored": report["provenance"]}
    for bad in ({**report, "extra": 1}, {k: v for k, v in report.items() if k != "candidate"}):
        with pytest.raises(ValueError, match="unknown fields|missing"):
            replay_report(bad)


def test_an_inconclusive_replay_reverifies_nothing_and_authorizes_nothing(tmp_path, capsys):
    from symq import Budget

    report = _proved_report(tmp_path, capsys)
    fresh = replay_report(report, Budget(max_seconds=1e-9))
    assert fresh["result"]["outcome"] == "inconclusive"
    assert fresh["replay"] == {"reverified": False, "stored_outcome": "equivalent"}
    assert fresh["candidate"] is None
    assert replayed_candidate(report, Budget(max_seconds=1e-9)) is None


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
    assert json.loads(report.read_text())["provenance"]["execution"]["status"] == "completed"


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


@pytest.mark.parametrize("field,value", [("checked_pairs", 1),
                                         ("theorem", "local_coherent_instrument"),
                                         ("instrument_slots", ["b0"])])
def test_coherent_report_fields_are_reverified(tmp_path, capsys, field, value):
    path = tmp_path / "r.json"
    assert _run(["rewrite", str(_coherent(tmp_path, TEMPORARY_AND)), "--report", str(path)],
                capsys)[0] == 0
    report = json.loads(path.read_text())
    report["result"][field] = value
    with pytest.raises(ReceiptMismatch, match=f"result.{field}"):
        replay_report(report)


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
