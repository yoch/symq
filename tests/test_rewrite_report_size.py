"""Rewrite publication must produce bounded, standalone replayable JSON."""
from __future__ import annotations

import json

import pytest

from symq.__main__ import _save_rewrite_report, main
from symq.experimental.serialization import MAX_DOCUMENT_BYTES, encode_json, load_json
from symq.labs import rewrite_request
from symq.resources import ResourceLimitExceeded


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


def test_large_valid_input_emits_a_standalone_replayable_report(tmp_path, capsys):
    request = _request(tmp_path, 130_000)
    assert (tmp_path / "source.json").stat().st_size < rewrite_request.MAX_INPUT_BYTES
    path = tmp_path / "report.json"
    assert main(["rewrite", str(request), "--report", str(path), "--timeout", "30"]) == 0
    assert json.loads(capsys.readouterr().out)["application"] == "applied"
    report = load_json(path)
    assert len(report["candidate"]["gates"]) == 129_998
    assert path.stat().st_size <= MAX_DOCUMENT_BYTES
    # The same receipt in the historical encoding exceeded the replay cap.
    assert len(encode_json(report).encode("utf-8")) > MAX_DOCUMENT_BYTES
    for name in ("source.json", "replacement.json", "request.json"):
        (tmp_path / name).unlink()
    assert main(["replay", str(path), "--timeout", "30"]) == 0
    assert json.loads(capsys.readouterr().out)["replay"]["reverified"] is True
    report["result"]["reason"] = "edited"
    _save_rewrite_report(report, path)
    assert main(["replay", str(path), "--timeout", "30"]) == 3
    assert json.loads(capsys.readouterr().out)["result"]["outcome"] == "receipt_mismatch"


@pytest.mark.parametrize("character", ["x", "é", "🧪"])
def test_writer_and_reader_share_the_exact_byte_boundary(tmp_path, character):
    path = tmp_path / "boundary.json"
    # JSON escaping expands Unicode, including non-BMP surrogate pairs. Two
    # quotes and the final newline also count toward the encoded byte cap.
    encoded_character_bytes = len(json.dumps(character).encode("utf-8")) - 2
    count, remainder = divmod(MAX_DOCUMENT_BYTES - 3, encoded_character_bytes)
    value = character * count + "x" * remainder
    _save_rewrite_report(value, path)
    assert path.stat().st_size == MAX_DOCUMENT_BYTES
    assert load_json(path) == value
    with pytest.raises(ResourceLimitExceeded, match="rewrite report bytes"):
        _save_rewrite_report(value + "x", path)
    assert load_json(path) == value
    with pytest.raises(ResourceLimitExceeded, match="rewrite report bytes"):
        _save_rewrite_report(value + "x", tmp_path / "absent.json")
    assert not (tmp_path / "absent.json").exists()
    assert list(tmp_path.iterdir()) == [path]


def test_oversized_cli_report_is_inconclusive_without_overwriting(tmp_path, capsys, monkeypatch):
    request = _request(tmp_path)
    path = tmp_path / "report.json"
    path.write_bytes(b"previous report\n")
    real_job = rewrite_request.rewrite_job

    def oversized(*args, **kwargs):
        report = real_job(*args, **kwargs)
        report["provenance"]["oversized"] = "x" * MAX_DOCUMENT_BYTES
        return report

    monkeypatch.setattr(rewrite_request, "rewrite_job", oversized)
    assert main(["rewrite", str(request), "--report", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["application"] == "not_applied"
    assert result["result"]["outcome"] == "inconclusive"
    assert "rewrite report bytes" in result["result"]["reason"]
    assert path.read_bytes() == b"previous report\n"


def test_prepared_input_encoding_stays_pretty_and_deterministic():
    assert encode_json({"b": 2, "a": 1}) == '{\n  "a": 1,\n  "b": 2\n}\n'
