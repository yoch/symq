"""Strict binary indexing, exact raw coordinates and composed scalar checks."""
from __future__ import annotations

import copy
import hashlib
import json
import random
import struct
from dataclasses import replace

import pytest
from test_kmb_window import _fixture, _packets

from symq import Circuit
from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.hashing import canonical_sha256
from symq.labs.indexed_substitution import prove_indexed_substitution, replay_indexed_substitution
from symq.labs.kmb_source_index import KmbSourceIndex, build_kmb_index
from symq.labs.kmx_source_index import IndexLimits, QueryLimits


def file(tmp_path, raw):
    path = tmp_path / "source.kmb"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def scalar(ops, state):
    for opcode, wires, _, _ in ops:
        if opcode == 0x11 or opcode == 0x21 and state >> wires[0] & 1 or opcode == 0x31 and all(state >> q & 1 for q in wires[:-1]):
            state ^= 1 << wires[-1]
    return state


def test_official_binary_fixture_and_source_operand_spans(tmp_path):
    path = _fixture(tmp_path)
    raw = path.read_bytes()
    pin = hashlib.sha256(raw).hexdigest()
    with build_kmb_index(path, expected_source_sha256=pin) as index:
        record = index.window(start_op=0, stop_op=3, expected_source_sha256=pin)
        assert record["source"]["source_ops"] == 3
        assert record["source"]["position_basis"].startswith("zero_based_raw_KMB")
        assert "op_lines" not in record
        assert index.verify_window(record, start_op=0, stop_op=3,
                                   expected_source_sha256=pin).to_dict() == record["program"]
        for spans, gate in zip(record["operand_byte_spans"], record["program"]["gates"]):
            assert [struct.unpack("<I", raw[slice(*s)])[0] for s in spans] == gate[1]


def test_temporal_cones_and_full_windows_against_scalar_oracle(tmp_path):
    rng = random.Random(2026110802)
    for _case in range(15):
        width = 5
        ops = []
        for _ in range(25):
            arity = rng.randint(1, 3)
            ops.append(({1: 0x11, 2: 0x21, 3: 0x31}[arity],
                        tuple(rng.sample(range(width), arity)), None, None))
        path, pin = file(tmp_path, _packets(*ops))
        with build_kmb_index(path, expected_source_sha256=pin) as index:
            observed, stop = (0, 4), 20
            cone = index.cone(stop_op=stop, observed_wires=observed, expected_source_sha256=pin)
            assert index.verify_cone(cone, stop_op=stop, observed_wires=observed,
                                     expected_source_sha256=pin).to_dict() == cone["program"]
            selected = [ops[i] for i in cone["gate_indices"]]
            for value in range(1 << width):
                assert all((scalar(ops[:stop], value) >> q & 1)
                           == (scalar(selected, value) >> q & 1) for q in observed)
            window = index.window(start_op=10, stop_op=20, expected_source_sha256=pin)
            assert window["gate_indices"] == list(range(10, 20))


def test_info_tags_preserve_raw_coordinates_without_becoming_gates(tmp_path):
    # Insert one real INFO_TAG packet using the public SOA specification.
    raw = bytearray(_packets((0x21, (0, 2), None, None), (0x21, (2, 3), None, None)))
    # Header nops at 32, ntags at 88, nchars at 96; first packet payload at 120.
    struct.pack_into("<Q", raw, 32, 3)
    struct.pack_into("<Q", raw, 88, 1)
    struct.pack_into("<Q", raw, 96, 1)
    struct.pack_into("<Q", raw, 112, 3)
    raw[121:121] = b"\x06"
    # Replace the last packet (id=11, old payload Q(0)).
    raw[-24:] = struct.pack("<QQQQ", 11, 17, 1, 1) + b"x"
    path, pin = file(tmp_path, raw)
    with build_kmb_index(path, expected_source_sha256=pin) as index:
        assert index.metadata()["source_ops"] == 3
        assert index.metadata()["semantic_ops"] == 2
        window = index.window(start_op=0, stop_op=3, expected_source_sha256=pin)
        assert window["gate_indices"] == [0, 2]
        cone = index.cone(stop_op=3, observed_wires=(3,), expected_source_sha256=pin)
        assert cone["gate_indices"] == [0, 2]
        with pytest.raises(UnsupportedOperation, match="metadata"):
            index.window(start_op=1, stop_op=2, expected_source_sha256=pin)


@pytest.mark.sat
def test_composed_binary_plan_rebuilds_and_replays(tmp_path):
    ops = [(0x21, (0, 2), None, None), (0x11, (5,), None, None),
           (0x21, (2, 3), None, None), (0x31, (1, 3, 5), None, None)]
    path, pin = file(tmp_path, _packets(*ops))
    request = {"kind": "symq_indexed_classical_substitution", "schema_version": 1,
               "source_file_sha256": pin, "prefix_start_op": 0, "op_span": [2, 3],
               "replacement": Circuit(1).to_dict(), "replacement_wires": [3],
               "contract": {"initial_constants": [[0, 0], [2, 0]], "clean_at_cut": [2]}}
    pins = {"expected_source_sha256": pin, "expected_request_sha256": canonical_sha256(request)}
    proof = prove_indexed_substitution(path, request, **pins)
    assert proof["status"] == "equivalent"
    assert replay_indexed_substitution(path, request, json.loads(json.dumps(proof)), **pins) == proof
    assert proof["global_cost"] is proof["complete_candidate"] is None
    for value in range(64):
        if value & 5 == 0:
            assert scalar(ops, value) == scalar(ops[:2] + ops[3:], value)


@pytest.mark.parametrize("bad", [(0x12, (4,), None, None), (0x50, (4,), 0, None),
                                 (0x20, (3, 4), None, None), (0x22, (3, 4), None, None),
                                 (0x91, (4,), None, 0), (0x40, (), 0, None)])
def test_hybrid_and_quantum_instructions_anywhere_refuse_complete_index(tmp_path, bad):
    path, pin = file(tmp_path, _packets((0x21, (0, 1), None, None), bad))
    with pytest.raises(UnsupportedOperation, match="only unconditional"):
        build_kmb_index(path, expected_source_sha256=pin)


def test_receipts_metadata_and_byte_limits_cannot_bypass_reconstruction(tmp_path):
    path, pin = file(tmp_path, _packets((0x31, (0, 1, 2), None, None)))
    with build_kmb_index(path, expected_source_sha256=pin) as index:
        meta = index.metadata()
        meta["operand_packet_offsets"]["2"] = 0
        assert index.metadata()["operand_packet_offsets"]["2"] != 0
        cone = index.cone(stop_op=1, observed_wires=(2,), expected_source_sha256=pin)
        assert cone["work"]["read_bytes"] == 13
        for field, value in [("operand_group_indices", [10]), ("dependencies", []),
                             ("operand_byte_spans", [[[0, 4]]]), ("global_wires", [2, 1, 0])]:
            mutant = copy.deepcopy(cone)
            mutant[field] = value
            with pytest.raises(ValueError, match="receipt"):
                index.verify_cone(mutant, stop_op=1, observed_wires=(2,), expected_source_sha256=pin)
        with pytest.raises(ResourceLimitExceeded, match="source bytes"):
            index.cone(stop_op=1, observed_wires=(2,), expected_source_sha256=pin,
                       limits=replace(QueryLimits(), max_read_bytes=12))
        path.unlink()
        assert index.cone(stop_op=1, observed_wires=(2,), expected_source_sha256=pin) == cone
    with pytest.raises(TypeError, match="manifest"):
        KmbSourceIndex(_metadata=meta)


@pytest.mark.parametrize("change", [lambda b: b.__setitem__(slice(0, 16), b"x" * 16),
                                    lambda b: b.extend(b"trailing"),
                                    lambda b: struct.pack_into("<Q", b, 40, 12),
                                    lambda b: b.__setitem__(120, 255)])
def test_malformed_complete_binary_is_never_accepted(tmp_path, change):
    raw = bytearray(_packets((0x21, (0, 1), None, None)))
    change(raw)
    path, pin = file(tmp_path, raw)
    with pytest.raises((ValueError, UnsupportedOperation)):
        build_kmb_index(path, expected_source_sha256=pin)


def test_index_budgets_and_clean_copy_hash(tmp_path):
    path, pin = file(tmp_path, _packets((0x31, (0, 1, 2), None, None)))
    with pytest.raises(ValueError, match="SHA-256"):
        build_kmb_index(path, expected_source_sha256="0" * 64)
    for limits in [replace(IndexLimits(), max_source_bytes=1),
                   replace(IndexLimits(), max_index_bytes=4096),
                   replace(IndexLimits(), max_wires=2)]:
        with pytest.raises(ResourceLimitExceeded):
            build_kmb_index(path, expected_source_sha256=pin, limits=limits)
