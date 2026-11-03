"""Audit regressions for symq.labs.kmx_window (PR #182)."""
from __future__ import annotations

import os

import pytest

from symq.errors import UnsupportedOperation
from symq.kickmix import load_kmx
from symq.labs.kmx_window import extract_kmx_window, verify_kmx_window


def _write(tmp_path, text, name="a.kmx"):
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


@pytest.mark.parametrize("sep", ["\r", "\x0b", "\x0c", "\x1c", "\x85", "\u2028", "\u2029"])
def test_line_provenance_matches_load_kmx_or_refuses(tmp_path, sep):
    path = _write(tmp_path, f"# reviewed comment{sep}CZ q0 q1\nX q2\n")
    try:
        record = extract_kmx_window(path, start_op=0, stop_op=2)
    except UnsupportedOperation:
        return
    assert record["op_lines"] == [op.line for op in load_kmx(path).ops]


def test_crlf_is_still_accepted_with_matching_lines(tmp_path):
    path = _write(tmp_path, "# c\r\nHMR q0 b0\r\n\r\nZ q1 if b0\r\n")
    record = extract_kmx_window(path, start_op=0, stop_op=2)
    assert record["op_lines"] == [op.line for op in load_kmx(path).ops] == [2, 4]


@pytest.mark.parametrize("bad", ["R q1", "CX q1", "FOO q1", "REGISTER r"])
def test_diagnostics_name_the_physical_line(tmp_path, bad):
    path = _write(tmp_path, "X q0\nX q1\nX q2\nX q3\n" + bad + "\n")
    with pytest.raises(ValueError, match=r"^line 5: "):
        extract_kmx_window(path, start_op=0, stop_op=1)


def test_verify_maps_non_canonical_receipts_to_value_error(tmp_path):
    path = _write(tmp_path, "HMR q0 b0\nZ q1 if b0\n")
    import hashlib
    pin = hashlib.sha256(path.read_bytes()).hexdigest()
    record = extract_kmx_window(path, start_op=1, stop_op=2)
    deep: list = []
    cursor = deep
    for _ in range(100_000):
        cursor.append([])
        cursor = cursor[0]
    for value in (deep, {"slot": "b0", 1: 2}):
        forged = dict(record)
        forged["fragment"] = value
        with pytest.raises(ValueError):
            verify_kmx_window(path, forged, expected_source_sha256=pin)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO")
def test_non_regular_source_is_refused_without_blocking(tmp_path):
    fifo = tmp_path / "pipe.kmx"
    os.mkfifo(fifo)
    with pytest.raises(UnsupportedOperation, match="regular file"):
        extract_kmx_window(fifo, start_op=0, stop_op=1)
