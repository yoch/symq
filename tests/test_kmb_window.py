"""Official Qualtran KMB-v2 fixture and independent packet-builder regressions."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.hybrid import HOp
from symq.labs.kmb_window import extract_kmb_window, verify_kmb_window
from symq.labs.kmx_window import extract_kmx_window

_MAGIC = bytes.fromhex("d750c7d5c329d326e3cc9f6834f2b8bf")
_FIX = Path(__file__).parent / "fixtures" / "kmb_v2_three_qubit_incrementer.hex"


def _fixture(tmp_path):
    source = "".join(
        row.strip() for row in _FIX.read_text(encoding="utf-8").splitlines()
        if not row.lstrip().startswith("#")
    )
    binary = bytes.fromhex(source)
    assert len(binary) == 351
    file = tmp_path / "official.kmb"
    file.write_bytes(binary)
    return file


def _packets(*operations, registers=()):
    """Independent KMB writer for tiny synthetic format-v2 audit cases.

    Each operation is (opcode, wires, target_bit, condition_bit).
    The writer follows the published SOA packet specification; it is
    deliberately separate from the production extractor.
    """
    types = []
    arrays = {i: bytearray() for i in range(2, 12)}
    max_q = max_b = -1
    counts = [0] * 7
    for opcode, wires, target_bit, condition in operations:
        types.append(opcode)
        group = opcode & 0x30
        if group:
            n = {0x10: 1, 0x20: 2, 0x30: 3}[group]
            assert len(wires) == n
            for p, wire in zip({1: (7,), 2: (5, 6), 3: (2, 3, 4)}[n], wires):
                arrays[p].extend(struct.pack("<I", wire))
                max_q = max(max_q, wire)
            counts[3 - n] += 1
        else:
            assert not wires
        if opcode & 0x40:
            assert target_bit is not None
            arrays[8].extend(struct.pack("<I", target_bit))
            max_b = max(max_b, target_bit)
            counts[3] += 1
        else:
            assert target_bit is None
        if opcode & 0x80:
            assert condition is not None
            arrays[9].extend(struct.pack("<I", condition))
            max_b = max(max_b, condition)
            counts[4] += 1
        else:
            assert condition is None
        if opcode in (0x13, 0x93):
            arrays[10].extend(b"\x00" * 16)
            counts[5] += 1
        if opcode == 0x06:
            counts[6] += 1

    reg_packets = []
    for name, ids in registers:
        encoded = name.encode("utf-8")
        payload = struct.pack("<II", len(encoded), len(ids)) + encoded
        for is_qubit, index in ids:
            payload += struct.pack("<I", index | (0x80000000 if is_qubit else 0))
            if is_qubit:
                max_q = max(max_q, index)
            else:
                max_b = max(max_b, index)
        reg_packets.append(struct.pack("<QQ", 0, len(payload)) + payload)
    arrays[11].extend(struct.pack("<Q", 0))
    # INFO_TAG test cases have their own explicit corruptions.
    assert counts[6] == 0
    info = [len(operations), *counts[:6], counts[6], 0]
    header = struct.pack("<16sIIII9Q", _MAGIC, 2, max_q + 1, max_b + 1,
                         len(reg_packets), *info)
    out = bytearray(header)
    for record in reg_packets:
        out.extend(record)
    out.extend(struct.pack("<QQ", 1, len(types)) + bytes(types))
    for kind in range(2, 12):
        data = arrays[kind]
        out.extend(struct.pack("<QQ", kind, len(data)))
        out.extend(data)
    return bytes(out)


def _write(tmp_path, *ops, registers=()):
    file = tmp_path / "generated.kmb"
    file.write_bytes(_packets(*ops, registers=registers))
    return file


def test_public_qualtran_three_qubit_incrementer_binary_fixture(tmp_path):
    file = _fixture(tmp_path)
    raw = file.read_bytes()
    pin = hashlib.sha256(raw).hexdigest()
    report = extract_kmb_window(
        file, start_op=0, stop_op=3, expected_source_sha256=pin
    )
    assert (report["num_qubits"], report["num_bits"], report["source_ops"]) == (3, 0, 3)
    assert report["source_file_sha256"] == pin
    assert report["global_wires"] == [0, 1, 2]
    assert report["fragment"]["ops"] == [
        {"kind": "ccx", "wires": [0, 1, 2], "slot": None,
         "condition": None, "source": None, "value": None},
        {"kind": "cx", "wires": [0, 1], "slot": None,
         "condition": None, "source": None, "value": None},
        {"kind": "x", "wires": [0], "slot": None,
         "condition": None, "source": None, "value": None},
    ]
    assert not report["proved"] and not report["candidate_authorized"]
    fragment = verify_kmb_window(file, report, expected_source_sha256=pin)
    assert fragment.ops == (HOp("ccx", (0, 1, 2)), HOp("cx", (0, 1)),
                            HOp("x", (0,)))
    assert report["type_byte_offsets"] == sorted(report["type_byte_offsets"])


def test_binary_and_text_window_produce_same_hybrid_fragment(tmp_path):
    operations = (
        (0x11, (8,), None, None),
        (0x50, (3,), 0, None),
        (0xA0, (8, 4), None, 0),
        (0x21, (2, 4), None, None),
        (0x50, (4,), 0, None),
        (0x90, (2,), None, 0),
        (0x22, (8, 2), None, None),
    )
    binary = _write(tmp_path, *operations)
    text = tmp_path / "source.kmx"
    text.write_text(
        "X q8\nHMR q3 b0\nCZ q8 q4 if b0\nCX q2 q4\n"
        "HMR q4 b0\nZ q2 if b0\nSWAP q8 q2\n",
        encoding="utf-8",
    )
    actual = extract_kmb_window(binary, start_op=2, stop_op=6)
    expected = extract_kmx_window(text, start_op=2, stop_op=6)
    assert actual["fragment"] == expected["fragment"]
    assert actual["global_wires"] == expected["global_wires"] == [2, 4, 8]
    assert actual["classical_predecessors"] == [
        {"slot": "b0", "last_write_op": 1, "last_write_kind": "HMR"}
    ]
    assert not actual["advisory_only"] is False
    assert not actual["proved"] and not actual["candidate_authorized"]


def test_real_reset_and_bit_operations_remain_explicit_not_elided(tmp_path):
    f = _write(tmp_path,
               (0x40, (), 0, None),    # BIT_STORE0 b0
               (0x42, (), 0, None),    # BIT_INVERT b0
               (0x91, (7,), None, 0),  # X q7 if b0
               (0x12, (8,), None, None))
    report = extract_kmb_window(f, start_op=1, stop_op=4)
    assert report["classical_predecessors"] == [
        {"slot": "b0", "last_write_op": 0, "last_write_kind": "BIT_STORE0"}
    ]
    assert report["fragment"]["classical_inputs"] == ["b0"]
    assert [x["kind"] for x in report["fragment"]["ops"]] == [
        "invert", "x", "reset"
    ]
    assert report["global_wires"] == [7, 8]


def test_pinned_file_and_claim_mutations_refused(tmp_path):
    f = _fixture(tmp_path)
    pin = hashlib.sha256(f.read_bytes()).hexdigest()
    report = extract_kmb_window(f, start_op=1, stop_op=3)
    fake = json.loads(json.dumps(report))
    fake["fragment"]["ops"][0]["kind"] = "x"
    with pytest.raises(ValueError, match="contradicts"):
        verify_kmb_window(f, fake, expected_source_sha256=pin)
    fake = json.loads(json.dumps(report))
    fake["source_file_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="contradicts"):
        verify_kmb_window(f, fake, expected_source_sha256=pin)
    f.write_bytes(f.read_bytes() + b"\x00")
    with pytest.raises(ValueError, match="pinned"):
        verify_kmb_window(f, report, expected_source_sha256=pin)


@pytest.mark.parametrize(("field", "replacement"), [
    ("schema_version", True),
    ("proved", 0),
    ("candidate_authorized", 0),
    ("advisory_only", 1),
    ("source_ops", 3.0),
    ("num_qubits", 3.0),
])
def test_replay_refuses_bool_integer_receipt_type_confusion(tmp_path, field, replacement):
    file = _fixture(tmp_path)
    pin = hashlib.sha256(file.read_bytes()).hexdigest()
    record = extract_kmb_window(file, start_op=0, stop_op=3)
    forged = json.loads(json.dumps(record))
    forged[field] = replacement
    with pytest.raises(ValueError):
        verify_kmb_window(file, forged, expected_source_sha256=pin)


@pytest.mark.parametrize("edit", [
    lambda b: b.__setitem__(0, 0),                  # magic
    lambda b: b.__setitem__(16, 1),                 # version
    lambda b: b.__setitem__(20, 4),                 # maximum qubit id
    lambda b: b.__setitem__(32, 4),                 # op count
    lambda b: b.__setitem__(104, 9),                # register packet order
    lambda b: b.__setitem__(124, 0xff),             # register payload
    lambda b: b.__setitem__(b.index(bytes((0x31, 0x21, 0x11))), 0xff),
    lambda b: b.extend(b"\x00"),
])
def test_public_binary_fixture_corruptions_fail_closed(tmp_path, edit):
    file = _fixture(tmp_path)
    raw = bytearray(file.read_bytes())
    edit(raw)
    file.write_bytes(raw)
    with pytest.raises((ValueError, UnsupportedOperation)):
        extract_kmb_window(file, start_op=0, stop_op=3)


def test_duplicate_qubit_rejected_and_unwritten_bit_is_explicit_input(tmp_path):
    f = _write(tmp_path, (0x21, (1, 1), None, None))
    with pytest.raises(ValueError, match="repeated"):
        extract_kmb_window(f, start_op=0, stop_op=1)
    f = _write(tmp_path, (0x90, (0,), None, 0))
    record = extract_kmb_window(f, start_op=0, stop_op=1)
    assert record["fragment"]["classical_inputs"] == ["b0"]
    assert record["classical_predecessors"] == [
        {"slot": "b0", "last_write_op": None,
         "last_write_kind": "SOURCE_INITIAL_UNKNOWN"}
    ]
    assert record["advisory_only"] and not record["proved"]


def test_possible_conditional_writer_and_active_condition_stack_refused(tmp_path):
    f = _write(tmp_path,
               (0x41, (), 1, None),
               (0xD0, (2,), 0, 1),
               (0x90, (0,), None, 0))
    with pytest.raises(UnsupportedOperation, match="possible prefix writer"):
        extract_kmb_window(f, start_op=2, stop_op=3)
    f = _write(tmp_path,
               (0x41, (), 0, None),
               (0x81, (), None, 0),
               (0x11, (2,), None, None),
               (0x01, (), None, None))
    with pytest.raises(UnsupportedOperation, match="PUSH_CONDITION"):
        extract_kmb_window(f, start_op=2, stop_op=3)


def test_unknown_angle_inside_window_refused_but_allowed_elsewhere(tmp_path):
    f = _write(tmp_path, (0x13, (0,), None, None),
               (0x11, (1,), None, None))
    report = extract_kmb_window(f, start_op=1, stop_op=2)
    assert report["unsupported_outside_window"] == 1
    with pytest.raises(UnsupportedOperation, match="Z_POW"):
        extract_kmb_window(f, start_op=0, stop_op=1)


def test_bounded_no_implicit_large_allocations(tmp_path):
    f = _fixture(tmp_path)
    with pytest.raises(ResourceLimitExceeded, match="file bytes"):
        extract_kmb_window(f, start_op=0, stop_op=3, max_source_bytes=128)
    with pytest.raises(ResourceLimitExceeded, match="operations"):
        extract_kmb_window(f, start_op=0, stop_op=3, max_source_ops=2)
    with pytest.raises(ResourceLimitExceeded, match="window operations"):
        extract_kmb_window(f, start_op=0, stop_op=3, max_window_ops=2)
    with pytest.raises(ResourceLimitExceeded, match="window wires"):
        extract_kmb_window(f, start_op=0, stop_op=3, max_window_wires=2)
    with pytest.raises(ValueError, match="range"):
        extract_kmb_window(f, start_op=2, stop_op=4)


def test_binary_window_cli_advisory_and_mismatch(tmp_path, capsys):
    from symq.__main__ import main

    file = _fixture(tmp_path)
    pin = hashlib.sha256(file.read_bytes()).hexdigest()
    assert main(["kmb-window", str(file), "--start-op", "0", "--stop-op", "3",
                 "--expected-source-sha256", pin]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "extracted" and not report["proved"]
    assert main(["kmb-window", str(file), "--start-op", "0", "--stop-op", "3",
                 "--expected-source-sha256", "0" * 64]) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "invalid" and not report["candidate_authorized"]
    text_file = tmp_path / "text.kmx"
    text_file.write_text("X q0\n", encoding="utf-8")
    assert main(["kmb-window", str(text_file),
                 "--start-op", "0", "--stop-op", "1"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "unsupported" and not report["proved"]


def test_supported_conditional_gate_outside_cut_is_not_reported_unsupported(tmp_path):
    # The program is structurally valid and the conditional operation is
    # among the fragment's accepted HOp grammar, even outside the cut.
    file = _write(tmp_path, (0x41, (), 0, None),
                  (0xA1, (0, 1), None, 0),
                  (0x11, (2,), None, None))
    record = extract_kmb_window(file, start_op=2, stop_op=3)
    assert record["unsupported_outside_window"] == 0
    assert record["fragment"]["ops"][0]["kind"] == "x"


def test_official_qualtran_8_qubit_adder_with_external_initial_bits(tmp_path):
    """A published large v2 KMB may read initial classical bits before any writer.

    This is a *structural* extraction. Those bits are explicitly unconstrained
    classical cut inputs, not a proof that they are prepared in any value.
    """
    file = tmp_path / "official-adder.kmb"
    raw = bytes.fromhex("".join(
        line.strip() for line in (
            Path(__file__).parent / "fixtures" / "kmb_v2_8_qubit_adder.hex"
        ).read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ))
    assert len(raw) == 1687
    file.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    first = extract_kmb_window(
        file, start_op=0, stop_op=1, expected_source_sha256=pin
    )
    assert (first["source_ops"], first["num_qubits"], first["num_bits"]) == (
        147, 16, 16
    )
    assert first["fragment"]["ops"][0]["kind"] == "x"
    assert first["fragment"]["classical_inputs"]
    assert first["classical_predecessors"] == [
        {"slot": first["fragment"]["classical_inputs"][0],
         "last_write_op": None, "last_write_kind": "SOURCE_INITIAL_UNKNOWN"}
    ]
    assert first["advisory_only"] and not first["proved"]
    assert not first["candidate_authorized"]
    assert verify_kmb_window(file, first, expected_source_sha256=pin).ops[0].kind == "x"

    # The same public binary actually contains HMR and non-unitary reset gates.
    hmr = extract_kmb_window(
        file, start_op=23, stop_op=24, expected_source_sha256=pin
    )
    assert hmr["fragment"]["ops"][0]["kind"] == "hmr"
    assert verify_kmb_window(file, hmr, expected_source_sha256=pin).ops[0].kind == "hmr"
    reset = extract_kmb_window(
        file, start_op=14, stop_op=15, expected_source_sha256=pin
    )
    assert reset["fragment"]["ops"][0]["kind"] == "reset"
    assert reset["advisory_only"] and not reset["proved"]


def test_audit_non_utf8_register_name_is_spec_valid(tmp_path):
    # The v2 spec types register names as raw chars; no encoding is mandated.
    data = bytearray(_packets((0x11, (0,), None, None), registers=[("ab", [(True, 0)])]))
    at = data.index(b"ab")
    data[at] = 0xFF
    file = tmp_path / "name.kmb"
    file.write_bytes(bytes(data))
    assert extract_kmb_window(file, start_op=0, stop_op=1)["status"] == "extracted"


def test_audit_malformed_file_is_invalid_even_if_window_is_unsupported(tmp_path):
    # Unknown opcode AFTER an unsupported selected op: the file is malformed.
    data = bytearray(_packets((0x13, (0,), None, None), (0x11, (0,), None, None)))
    data[data.index(bytes([0x13, 0x11]), 104) + 1] = 0xE7
    file = tmp_path / "bad.kmb"
    file.write_bytes(bytes(data))
    with pytest.raises(ValueError) as caught:
        extract_kmb_window(file, start_op=0, stop_op=1)
    assert not isinstance(caught.value, UnsupportedOperation)


def test_audit_fifo_source_is_refused_without_blocking(tmp_path):
    import os
    fifo = tmp_path / "pipe.kmb"
    os.mkfifo(fifo)
    with pytest.raises(UnsupportedOperation):
        extract_kmb_window(fifo, start_op=0, stop_op=1, max_seconds=1.0)


@pytest.mark.parametrize("ops", [
    ((0x01, (), None, None), (0x11, (0,), None, None)),          # POP on empty stack
    ((0x11, (0,), None, None), (0x81, (), None, 0)),             # PUSH left open at EOF
])
def test_audit_spec_valid_condition_stack_shapes_are_refused_not_invalid(tmp_path, ops):
    # Spec: "If the condition stack is empty, this operation has no effect."
    file = _write(tmp_path, *ops)
    with pytest.raises(UnsupportedOperation):
        extract_kmb_window(file, start_op=0, stop_op=2)
