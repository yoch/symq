"""Adversarial end-to-end tests of the *experimental* file-based P0 workflow.

This tests import, declared cut/restore contract, SAT proof, immutable
application, exact gate-weight accounting, self-contained report replay and
fail-closed mutations. It is not an HMR or quantum phase-channel theorem.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from symq.circuit import Circuit, Gate
from symq.hashing import canonical_sha256
from symq.labs.substitution_workflow import (
    _read_report,
    load_circuit_file,
    load_contract_json,
    main,
    replay_report,
    verify_request,
)

pytestmark = pytest.mark.sat

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "contextual_workflow"


def _copy(tmp_path: Path) -> Path:
    for name in ("source.qasm", "replacement.json", "request.json"):
        (tmp_path / name).write_bytes((FIXTURES / name).read_bytes())
    return tmp_path / "request.json"


def _change(request: Path, update) -> None:
    data = json.loads(request.read_text(encoding="utf-8"))
    update(data)
    request.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_import_contract_prove_and_replay_full_permitted_domain(tmp_path):
    request = _copy(tmp_path)
    source, _ = load_circuit_file(tmp_path / "source.qasm")
    assert source.width == 5 and len(source.gates) == 4
    report = verify_request(request)
    proof = report["result"]
    assert proof["outcome"] == "equivalent"
    assert proof["cost"]["weighted_delta"] == -4
    assert proof["reference_sha256"] != proof["candidate_sha256"]
    assert [r["name"] for r in proof["obligations"]] == [
        "domain", "prefix", "interface", "suffix",
        "restore_original", "restore_candidate",
    ]
    assert all(r["status"] == "passed" for r in proof["obligations"])
    assert report["file_provenance"]["request_sha256"]
    assert report["file_provenance"]["source_file_sha256"]
    assert report["file_provenance"]["replacement_file_sha256"]

    applied = report["candidate"]
    assert applied["width"] == 5
    circuit = Circuit(
        applied["width"],
        [
            Gate(n, tuple(q))
            for n, q in applied["gates"]
        ],
    )
    for state in range(1 << 5):
        if not (state >> 4) & 1:
            assert source.run(state) == circuit.run(state)
    # This is a classical domain-specific theorem; the dirty scratch
    # assignment is not silently treated as prepared or coherent.
    assert source.run(1 << 4 | 7) != circuit.run(1 << 4 | 7)
    again = replay_report(report)
    assert again["result"]["outcome"] == "equivalent"
    assert again["candidate"] == report["candidate"]
    assert again["semantic_sha256"] == report["semantic_sha256"]


def test_file_cli_atomic_report_sidecar_and_offline_replay(tmp_path, capsys):
    request = _copy(tmp_path)
    path = tmp_path / "result.json"
    assert main(["verify", str(request), "--report", str(path)]) == 0
    report = _read_report(path)
    assert report["candidate"] is not None
    assert (tmp_path / "result.json.sha256").is_file()
    # A self-contained receipt does not rely on access to its old source files,
    # but a fresh import of those files will acquire new source fingerprints.
    (tmp_path / "source.qasm").unlink()
    (tmp_path / "replacement.json").unlink()
    (tmp_path / "request.json").unlink()
    assert main(["replay", str(path)]) == 0
    assert "equivalent" in capsys.readouterr().out


def test_missing_precondition_is_reported_but_never_applied(tmp_path):
    request = _copy(tmp_path)
    _change(request, lambda data: data["contract"].update(initial_constants=[]))
    report = verify_request(request)
    assert report["result"]["outcome"] == "precondition_failed"
    assert report["candidate"] is None
    output = tmp_path / "reject.json"
    assert main(["verify", str(request), "--report", str(output)]) == 1
    assert _read_report(output)["candidate"] is None
    # A forged "equivalent" flag and re-signed JSON are never proof authority.
    forged = _read_report(output)
    forged["result"]["outcome"] = "equivalent"
    forged.pop("semantic_sha256")
    forged["semantic_sha256"] = canonical_sha256(forged)
    with pytest.raises(ValueError, match="fresh proof disagrees"):
        replay_report(forged)


def test_missing_uncompute_is_refused(tmp_path):
    request = _copy(tmp_path)
    source = json.loads((tmp_path / "replacement.json").read_text())
    del source["gates"][-1]
    (tmp_path / "replacement.json").write_text(json.dumps(source))
    record = verify_request(request)
    assert record["result"]["outcome"] == "not_proved"
    assert record["candidate"] is None


def test_cut_ast_is_closed_and_proved_not_assumed(tmp_path):
    request = _copy(tmp_path)
    _change(
        request,
        lambda data: data["contract"].update(
            cut_assumption=["not", ["var", "u.4"]]
        ),
    )
    assert verify_request(request)["result"]["outcome"] == "equivalent"
    _change(
        request,
        lambda data: data["contract"].update(cut_assumption=["var", "u.4"]),
    )
    assert verify_request(request)["result"]["outcome"] == "precondition_failed"
    _change(
        request,
        lambda data: data["contract"].update(cut_assumption=["var", "v.4"]),
    )
    with pytest.raises(ValueError, match="undeclared"):
        verify_request(request)


def test_borrowed_bit_restoration_is_a_separate_proof(tmp_path):
    request = _copy(tmp_path)
    original = {"kind": "classical_reversible", "width": 3,
                "gates": [["cx", [0, 2]], ["cx", [0, 2]]]}
    candidate = {"kind": "classical_reversible", "width": 3, "gates": []}
    (tmp_path / "source.json").write_text(json.dumps(original))
    (tmp_path / "replacement.json").write_text(json.dumps(candidate))
    data = json.loads(request.read_text())
    data.update(source="source.json", span=[0, 2])
    data["contract"] = {"initial_constants": [], "clean_at_cut": [],
                        "restored_at_cut": [2], "cut_assumption": None}
    request.write_text(json.dumps(data))
    report = verify_request(request)
    assert report["result"]["outcome"] == "equivalent"
    assert report["candidate"]["gates"] == []
    # Two individually equal but non-restoring blocks are *not* valid
    # when a borrowed wire has an explicit restoration obligation.
    data["span"] = [0, 1]
    request.write_text(json.dumps(data))
    report = verify_request(request)
    assert report["result"]["outcome"] == "not_proved"
    assert report["candidate"] is None


@pytest.mark.parametrize("bad", [
    ["not"], ["or", ["var", "u.0"], ["var", "u.1"]],
    ["var", "other.0"], ["const", 1], ["xor", "literal", ["var", "u.1"]],
])
def test_unknown_boolean_contracts_fail_closed(bad):
    data = {"initial_constants": [], "clean_at_cut": [],
            "restored_at_cut": [], "cut_assumption": bad}
    with pytest.raises(ValueError):
        load_contract_json(data, 3)


def test_duplicate_json_unsupported_file_and_provenance_tamper(tmp_path):
    request = _copy(tmp_path)
    report_path = tmp_path / "proof.json"
    assert main(["verify", str(request), "--report", str(report_path)]) == 0

    (tmp_path / "source.qasm").write_text("OPENQASM 3; qubit[5] q; h q[0];")
    with pytest.raises(ValueError):
        verify_request(request)
    (tmp_path / "source.qasm").write_text(
        (FIXTURES / "source.qasm").read_text(encoding="utf-8")
    )
    # Refuse any binary .kmb path rather than guessing a conversion.
    (tmp_path / "untrusted.kmb").write_bytes(b"invalid")
    _change(request, lambda d: d.update(source="untrusted.kmb"))
    with pytest.raises(ValueError, match="supported circuit inputs"):
        verify_request(request)

    request.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        verify_request(request)

    path = report_path
    artifact = json.loads(path.read_text())
    artifact["result"]["outcome"] = "different"
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="SHA-256 sidecar mismatch"):
        _read_report(path)


def test_report_cannot_overwrite_inputs_or_export_candidate_on_failure(tmp_path):
    request = _copy(tmp_path)
    src = tmp_path / "source.qasm"
    old_bytes = src.read_bytes()
    assert main(["verify", str(request), "--report", str(src)]) == 3
    assert src.read_bytes() == old_bytes
    assert main(["verify", str(request), "--report", str(request)]) == 3


def test_extra_unknown_contract_keys_are_refused():
    data = {"initial_constants": [], "clean_at_cut": [],
            "restored_at_cut": [], "future_unknown_assumption": True}
    with pytest.raises(ValueError, match="fields"):
        load_contract_json(data, 3)
