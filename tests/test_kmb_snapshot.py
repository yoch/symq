"""Adversarial tests for source-bound *private* KMB snapshots.

The oracle is the immutable official Qualtran-v2 hex fixture, not a
second invocation of the parser's own internal decoder. The filesystem
races are scheduled deterministically at the parser's layout boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from symq.errors import ResourceLimitExceeded
from symq.labs import kmb_window


_FIXTURE = Path(__file__).parent / "fixtures" / "kmb_v2_three_qubit_incrementer.hex"


def _source(tmp_path):
    source = bytes.fromhex("".join(
        line.strip() for line in _FIXTURE.read_text("utf-8").splitlines()
        if line and not line.startswith("#")
    ))
    assert len(source) == 351
    file = tmp_path / "source.kmb"
    file.write_bytes(source)
    return file, source


def test_private_copy_binds_exact_decoded_bytes_against_aba_writer(tmp_path, monkeypatch):
    path, original = _source(tmp_path)
    pin = hashlib.sha256(original).hexdigest()
    expected = kmb_window.extract_kmb_window(
        path, start_op=0, stop_op=3, expected_source_sha256=pin,
    )
    assert [op["kind"] for op in expected["fragment"]["ops"]] == ["ccx", "cx", "x"]
    type_offset = expected["type_byte_offsets"][0]
    assert original[type_offset] == 0x31
    original_layout = kmb_window._layout
    original_sha = kmb_window._sha
    mutated = False
    calls = 0

    def mutate_original_after_snapshot(view, **kwargs):
        nonlocal mutated
        result = original_layout(view, **kwargs)
        with path.open("r+b") as stream:
            stream.seek(type_offset)
            stream.write(b"\x30")  # CCX -> CCZ, same SOA arity and counts
            stream.flush()
        mutated = True
        return result

    def restore_before_second_hash(view, deadline):
        nonlocal calls
        calls += 1
        if calls == 2:
            assert mutated
            with path.open("r+b") as stream:
                stream.seek(type_offset)
                stream.write(b"\x31")
                stream.flush()
        return original_sha(view, deadline)

    monkeypatch.setattr(kmb_window, "_layout", mutate_original_after_snapshot)
    monkeypatch.setattr(kmb_window, "_sha", restore_before_second_hash)
    actual = kmb_window.extract_kmb_window(
        path, start_op=0, stop_op=3, expected_source_sha256=pin,
    )
    assert calls == 2 and mutated
    assert path.read_bytes() == original
    assert actual == expected
    assert actual["fragment"]["ops"][0]["kind"] == "ccx"
    assert actual["source_file_sha256"] == pin


def test_concurrent_source_truncation_does_not_sigbus_private_decoder(tmp_path, monkeypatch):
    path, original = _source(tmp_path)
    pin = hashlib.sha256(original).hexdigest()
    original_layout = kmb_window._layout

    def truncate_original_after_private_copy(view, **kwargs):
        parsed = original_layout(view, **kwargs)
        path.write_bytes(b"")
        return parsed

    monkeypatch.setattr(kmb_window, "_layout", truncate_original_after_private_copy)
    result = kmb_window.extract_kmb_window(
        path, start_op=0, stop_op=3, expected_source_sha256=pin,
    )
    assert result["source_file_sha256"] == pin
    assert result["fragment"]["ops"][0]["kind"] == "ccx"
    assert os.stat(path).st_size == 0

    monkeypatch.setattr(kmb_window, "_layout", original_layout)
    with pytest.raises(ValueError, match="truncated"):
        kmb_window.verify_kmb_window(path, result, expected_source_sha256=pin)


def test_private_copy_has_a_separate_disk_size_limit(tmp_path, monkeypatch):
    path, source = _source(tmp_path)
    assert len(source) == 351
    assert kmb_window.extract_kmb_window(
        path, start_op=0, stop_op=3, max_snapshot_bytes=351
    )["status"] == "extracted"
    def fail_if_snapshot_called(*args, **kwargs):
        raise AssertionError("size guard must run before allocating temporary storage")
    monkeypatch.setattr(kmb_window.tempfile, "TemporaryFile", fail_if_snapshot_called)
    with pytest.raises(ResourceLimitExceeded, match="private snapshot bytes"):
        kmb_window.extract_kmb_window(
            path, start_op=0, stop_op=3, max_snapshot_bytes=350,
        )


def test_independent_source_pin_and_receipt_fail_closed(tmp_path):
    path, raw = _source(tmp_path)
    source_pin = hashlib.sha256(raw).hexdigest()
    receipt = kmb_window.extract_kmb_window(
        path, start_op=0, stop_op=2, expected_source_sha256=source_pin
    )
    assert kmb_window.verify_kmb_window(
        path, receipt, expected_source_sha256=source_pin
    ).ops[0].kind == "ccx"
    forged = json.loads(json.dumps(receipt))
    forged["fragment"]["ops"][0]["kind"] = "ccz"
    with pytest.raises(ValueError):
        kmb_window.verify_kmb_window(
            path, forged, expected_source_sha256=source_pin
        )
    with pytest.raises(ValueError, match="pinned"):
        kmb_window.extract_kmb_window(
            path, start_op=0, stop_op=2, expected_source_sha256="0" * 64
        )


def test_cli_exposes_private_copy_limit(tmp_path, capsys):
    from symq.__main__ import main

    path, _ = _source(tmp_path)
    assert main(["kmb-window", str(path), "--start-op", "0", "--stop-op", "3",
                 "--max-snapshot-mib", "0"]) == 3
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "invalid" and not response["proved"]
    assert main(["kmb-window", str(path), "--start-op", "0", "--stop-op", "3",
                 "--max-snapshot-mib", "1"]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "extracted" and not response["candidate_authorized"]
