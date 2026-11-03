# ruff: noqa: I001 -- the CLI integration test imports additional names locally
"""Regression tests for source-bound extraction from strict text Kickmix.

These tests do not assert coherent channel equivalence for a sliced fragment:
prefix classical inputs and borrowed quantum state still require a proof.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.kmx_window import extract_kmx_window, verify_kmx_window
from symq.labs.rewrite_locator import locate_exact


SOURCE = (
    '# full file comment\n'
    'REGISTER group "demo"\n'
    'X q8\n'                  # operation 0, line 3
    'HMR q3 b0\n'             # operation 1, line 4
    'INFO_TAG some_info\n'
    'CZ q8 q4 if b0\n'       # operation 2, line 6
    'CX q2 q4\n'             # operation 3, line 7
    'HMR q4 b0\n'            # operation 4, line 8
    'Z q2 if b0\n'          # operation 5, line 9
    'SWAP q8 q2\n'           # operation 6, line 10
)


def _write(tmp_path, source=SOURCE):
    file = tmp_path / "large.kmx"
    file.write_text(source, encoding="utf-8")
    return file


def test_extract_complete_span_with_incoming_classical_dependency(tmp_path):
    path = _write(tmp_path)
    pin = hashlib.sha256(SOURCE.encode()).hexdigest()
    record = extract_kmx_window(
        path, start_op=2, stop_op=6, expected_source_sha256=pin
    )
    assert (record["source_file_sha256"], record["source_ops"]) == (pin, 7)
    assert record["source_bytes"] == len(SOURCE.encode())
    assert record["op_span"] == [2, 6]
    assert record["line_span"] == [6, 10]
    assert record["op_lines"] == [6, 7, 8, 9]
    assert record["global_wires"] == [2, 4, 8]
    assert record["classical_predecessors"] == [
        {"slot": "b0", "last_hmr_op": 1, "last_hmr_line": 4}
    ]
    assert record["advisory_only"] and not record["proved"]
    assert record["candidate_authorized"] is False
    fragment = verify_kmx_window(path, record, expected_source_sha256=pin)
    assert fragment.width == 3
    assert fragment.classical_inputs == ("b0",)
    assert fragment.ops == (
        HOp("cz", (2, 1), condition="b0"),
        HOp("cx", (0, 1)),
        HOp("hmr", (1,), slot="b0"),
        HOp("z", (0,), condition="b0"),
    )
    # Integration with the existing exact structural locator, still NOT a proof.
    whole = HybridProgram(9, 0, [
        HOp("x", (8,)),
        HOp("hmr", (3,), slot="b0"),
        HOp("cz", (8, 4), condition="b0"),
        HOp("cx", (2, 4)),
        HOp("hmr", (4,), slot="b0"),
        HOp("z", (2,), condition="b0"),
        HOp("swap", (8, 2)),
    ])
    found = locate_exact(whole, fragment)
    assert found["status"] == "unique"
    assert found["matches"][0]["span"] == [2, 6]
    assert found["matches"][0]["wires"] == [2, 4, 8]


def test_tampered_record_or_file_is_rejected_even_when_operations_stay_identical(tmp_path):
    path = _write(tmp_path)
    pin = hashlib.sha256(SOURCE.encode()).hexdigest()
    original = extract_kmx_window(path, start_op=2, stop_op=6)
    forged = json.loads(json.dumps(original))
    forged["fragment"]["ops"][0]["condition"] = "b1"
    with pytest.raises(ValueError, match="contradicts"):
        verify_kmx_window(path, forged, expected_source_sha256=pin)
    forged = json.loads(json.dumps(original))
    forged["source_file_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="contradicts"):
        verify_kmx_window(path, forged, expected_source_sha256=pin)
    forged = json.loads(json.dumps(original))
    forged["extra"] = True
    with pytest.raises(ValueError, match="closed"):
        verify_kmx_window(path, forged, expected_source_sha256=pin)
    path.write_text("# unrelated edit\n" + SOURCE, encoding="utf-8")
    with pytest.raises(ValueError, match="independently pinned"):
        verify_kmx_window(path, original, expected_source_sha256=pin)
    with pytest.raises(ValueError, match="independently pinned"):
        extract_kmx_window(path, start_op=2, stop_op=6, expected_source_sha256=pin)


def test_invalid_cross_cut_classical_reference_fails_closed(tmp_path):
    path = _write(tmp_path, "Z q1 if b0\nHMR q1 b0\n")
    with pytest.raises(UnsupportedOperation, match="before HMR"):
        extract_kmx_window(path, start_op=1, stop_op=2)
    path = _write(tmp_path, "HMR q1 b0\nZ q1 if b0\nHMR q2 b0\nZ q1 if b0\n")
    first = extract_kmx_window(path, start_op=1, stop_op=2)
    assert first["classical_predecessors"][0]["last_hmr_op"] == 0
    last = extract_kmx_window(path, start_op=3, stop_op=4)
    assert last["classical_predecessors"][0]["last_hmr_op"] == 2
    # The same slot name refers to a different measurement event at the cut.
    assert last["classical_predecessors"] != first["classical_predecessors"]


def test_unsupported_gate_anywhere_in_full_source_fails_closed(tmp_path):
    path = _write(tmp_path, "X q0\nHMR q1 b0\nZ q0 if b0\nR q1\n")
    with pytest.raises(UnsupportedOperation, match="reset"):
        extract_kmx_window(path, start_op=0, stop_op=1)
    with pytest.raises(UnsupportedOperation, match="binary .kmb"):
        extract_kmx_window(tmp_path / "data.kmb", start_op=0, stop_op=1)


@pytest.mark.parametrize("span", [(0, 0), (-1, 2), (2, 1), (True, 2), (1, 3.0)])
def test_invalid_operation_range_is_rejected(tmp_path, span):
    with pytest.raises(ValueError):
        extract_kmx_window(_write(tmp_path), start_op=span[0], stop_op=span[1])


def test_boundaries_and_missing_quantum_wires_fail_closed(tmp_path):
    path = _write(tmp_path)
    with pytest.raises(ResourceLimitExceeded, match="line bytes"):
        extract_kmx_window(path, start_op=2, stop_op=3, max_line_bytes=5)
    with pytest.raises(ResourceLimitExceeded, match="source bytes"):
        extract_kmx_window(path, start_op=2, stop_op=3, max_source_bytes=10)
    with pytest.raises(ResourceLimitExceeded, match="source operations"):
        extract_kmx_window(path, start_op=2, stop_op=3, max_source_ops=3)
    with pytest.raises(ResourceLimitExceeded, match="window operations"):
        extract_kmx_window(path, start_op=2, stop_op=6, max_window_ops=3)
    with pytest.raises(ResourceLimitExceeded, match="window wires"):
        extract_kmx_window(path, start_op=2, stop_op=6, max_window_wires=2)
    with pytest.raises(ValueError, match="exceeds"):
        extract_kmx_window(path, start_op=6, stop_op=8)
    with pytest.raises(ValueError, match="lowercase"):
        extract_kmx_window(path, start_op=2, stop_op=3,
                           expected_source_sha256="A" * 64)


def test_streaming_large_prefix_and_cli_json(tmp_path, capsys):
    from symq.__main__ import main

    source = "X q0\n" * 500 + "HMR q9 b5\nZ q2 if b5\n"
    path = _write(tmp_path, source)
    pin = hashlib.sha256(source.encode()).hexdigest()
    expected = extract_kmx_window(
        path, start_op=501, stop_op=502, expected_source_sha256=pin
    )
    assert expected["source_ops"] == 502
    assert expected["global_wires"] == [2]
    assert expected["classical_predecessors"] == [
        {"slot": "b5", "last_hmr_op": 500, "last_hmr_line": 501}
    ]
    result = main([
        "kmx-window", str(path), "--start-op", "501", "--stop-op", "502",
        "--expected-source-sha256", pin
    ])
    assert result == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert main(["kmx-window", str(tmp_path / "binary.kmb"),
                 "--start-op", "0", "--stop-op", "1"]) == 2
    invalid = json.loads(capsys.readouterr().out)
    assert invalid["status"] == "unsupported" and invalid["proved"] is False
    assert main(["kmx-window", str(path), "--start-op", "0",
                 "--stop-op", "503"]) == 3
    bad = json.loads(capsys.readouterr().out)
    assert bad["status"] == "invalid" and bad["candidate_authorized"] is False
