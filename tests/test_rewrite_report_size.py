"""Replayable publication must produce bounded, standalone JSON that its reader accepts."""
from __future__ import annotations

import json

import pytest

from symq.__main__ import main
from symq.experimental import serialization
from symq.experimental.serialization import (
    encode_compact_json,
    encode_json,
    load_json,
    save_replayable_json,
)
from symq.labs import rewrite_request
from symq.resources import ResourceLimitExceeded

LIMIT = "replayable document bytes"


def _request(tmp_path, gates=2):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"width": 1, "gates": [["x", [0]]] * gates},
                                 separators=(",", ":")))
    (tmp_path / "replacement.json").write_text('{"width":1,"gates":[]}')
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": 1, "kind": "symq_rewrite_request", "theorem": "classical",
        "source": "source.json", "replacement": "replacement.json", "span": [0, 2],
        "contract": {}, "engine": "linear",
    }))
    return request


def test_valid_input_emits_a_standalone_replayable_report_under_the_shared_limit(
        tmp_path, capsys, monkeypatch):
    # A smaller shared limit keeps this end-to-end case fast: writer and reader read the same
    # module constant at call time, so this exercises exactly the production boundary logic.
    request = _request(tmp_path, 4_000)
    path = tmp_path / "report.json"
    assert main(["rewrite", str(request), "--report", str(path), "--timeout", "30"]) == 0
    capsys.readouterr()
    report = load_json(path)
    compact = len(encode_compact_json(report).encode("utf-8"))
    pretty = len(encode_json(report).encode("utf-8"))
    assert compact < pretty
    # The historical pretty encoding would not fit; the compact one does, at the exact limit.
    monkeypatch.setattr(serialization, "MAX_DOCUMENT_BYTES", compact)
    assert main(["rewrite", str(request), "--report", str(path), "--timeout", "30"]) == 0
    assert json.loads(capsys.readouterr().out)["application"] == "applied"
    assert path.stat().st_size == compact < pretty
    for name in ("source.json", "replacement.json", "request.json"):
        (tmp_path / name).unlink()
    assert main(["replay", str(path), "--timeout", "30"]) == 0
    assert json.loads(capsys.readouterr().out)["replay"]["reverified"] is True
    report["result"]["reason"] = "edited"
    save_replayable_json(report, path)
    assert main(["replay", str(path), "--timeout", "30"]) == 3
    assert json.loads(capsys.readouterr().out)["result"]["outcome"] == "receipt_mismatch"


@pytest.mark.parametrize("character", ["x", "é", "🧪"])
def test_writer_and_reader_share_the_exact_byte_boundary(tmp_path, character):
    path = tmp_path / "boundary.json"
    # JSON escaping expands Unicode, including non-BMP surrogate pairs. The
    # quotes count toward the cap; no literal newline may undergo CRLF translation.
    limit = serialization.MAX_DOCUMENT_BYTES
    encoded_character_bytes = len(json.dumps(character).encode("utf-8")) - 2
    count, remainder = divmod(limit - 2, encoded_character_bytes)
    value = character * count + "x" * remainder
    save_replayable_json(value, path)
    assert path.stat().st_size == limit
    assert b"\n" not in path.read_bytes()
    assert load_json(path) == value
    with pytest.raises(ResourceLimitExceeded, match=LIMIT):
        save_replayable_json(value + "x", path)
    assert load_json(path) == value
    with pytest.raises(ResourceLimitExceeded, match=LIMIT):
        save_replayable_json(value + "x", tmp_path / "absent.json")
    assert not (tmp_path / "absent.json").exists()
    assert list(tmp_path.iterdir()) == [path]


def test_reader_default_follows_the_shared_limit(tmp_path, monkeypatch):
    path = tmp_path / "doc.json"
    save_replayable_json("x" * 10, path)  # 12 bytes with quotes
    monkeypatch.setattr(serialization, "MAX_DOCUMENT_BYTES", 11)
    with pytest.raises(ValueError, match="exceeds max_bytes"):
        load_json(path)
    assert load_json(path, max_bytes=12) == "x" * 10


def test_oversized_cli_report_is_inconclusive_names_the_unpublished_result(
        tmp_path, capsys, monkeypatch):
    request = _request(tmp_path)
    path = tmp_path / "report.json"
    path.write_bytes(b"previous report\n")
    real_job = rewrite_request.rewrite_job

    def oversized(*args, **kwargs):
        report = real_job(*args, **kwargs)
        report["provenance"]["oversized"] = "x" * serialization.MAX_DOCUMENT_BYTES
        return report

    monkeypatch.setattr(rewrite_request, "rewrite_job", oversized)
    assert main(["rewrite", str(request), "--report", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["application"] == "not_applied"
    assert result["result"]["outcome"] == "inconclusive"
    assert LIMIT in result["result"]["reason"]
    # The computed decision is reported, but explicitly without authority.
    assert result["unpublished_result"] == {"authoritative": False, "application": "applied",
                                            "outcome": "equivalent"}
    assert path.read_bytes() == b"previous report\n"


def _verify_documents(tmp_path):
    from symq.experimental import VerificationContract
    from symq.experimental.serialization import save_contract, save_program
    from symq.phase import PhaseProgram

    candidate = PhaseProgram(2, 1).ccx(0, 1, 2)
    candidate.cz_if(candidate.hmr(2), 0, 1)
    save_program(PhaseProgram(2, 1), tmp_path / "reference.json")
    save_program(candidate, tmp_path / "candidate.json")
    save_contract(VerificationContract(theorem="full_channel", backend="zdd"),
                  tmp_path / "contract.json")
    return [str(tmp_path / name) for name in ("reference.json", "candidate.json")] + [
        "--contract", str(tmp_path / "contract.json")]


def test_verify_report_is_replayable_and_compact(tmp_path, capsys):
    arguments = _verify_documents(tmp_path)
    path = tmp_path / "artifact.json"
    assert main(["verify", *arguments, "--report", str(path)]) == 0
    capsys.readouterr()
    assert b"\n" not in path.read_bytes()
    artifact = load_json(path)
    assert artifact["kind"] == "symq_verification"
    assert main(["replay", str(path)]) == 0


def test_oversized_verify_report_is_refused_without_overwriting(tmp_path, capsys, monkeypatch):
    arguments = _verify_documents(tmp_path)
    path = tmp_path / "artifact.json"
    path.write_bytes(b"previous artifact\n")
    # Inputs share the limit: keep it just above them, far below the verification artifact.
    inputs = [tmp_path / name for name in ("reference.json", "candidate.json", "contract.json")]
    monkeypatch.setattr(serialization, "MAX_DOCUMENT_BYTES",
                        max(item.stat().st_size for item in inputs))
    assert main(["verify", *arguments, "--report", str(path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["outcome"] == "inconclusive" and LIMIT in output["reason"]
    assert path.read_bytes() == b"previous artifact\n"


def test_prepared_input_encoding_stays_pretty_and_deterministic():
    assert encode_json({"b": 2, "a": 1}) == '{\n  "a": 1,\n  "b": 2\n}\n'
    assert encode_compact_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_withdrawal_never_republishes_a_refused_verify_report(tmp_path, capsys, monkeypatch):
    # The withdrawn artifact differs in size from the refused one; whatever the sizes, a size
    # refusal must not be followed by a second publication attempt of the same report.
    arguments = _verify_documents(tmp_path)
    path = tmp_path / "artifact.json"
    path.write_bytes(b"previous artifact\n")
    real = serialization.save_replayable_json
    calls = []

    def refuse_first(value, target):
        calls.append(value["result"]["outcome"])
        if len(calls) == 1:
            raise ResourceLimitExceeded(serialization.REPLAYABLE_BYTES, 1, 2)
        real(value, target)

    monkeypatch.setattr(serialization, "save_replayable_json", refuse_first)
    assert main(["verify", *arguments, "--report", str(path)]) == 2
    assert LIMIT in json.loads(capsys.readouterr().out)["reason"]
    assert calls == ["equivalent"]
    assert path.read_bytes() == b"previous artifact\n"
