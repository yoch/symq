"""Independent finite-state and adversarial tests of the owned KMX disk index."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import sqlite3
import sys

import pytest

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.labs import kmx_source_index as indexes
from symq.resources import Budget


def _source(tmp_path, raw=b"CCX q0 q1 q2\n", name="source.kmx"):
    path = tmp_path / name
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _scalar(width, operations, value):
    """Independent bit-vector interpreter, without the importer or Circuit.run."""
    bits = [(value >> wire) & 1 for wire in range(width)]
    for name, wires in operations:
        if name == "x":
            bits[wires[0]] ^= 1
        elif name == "cx":
            bits[wires[1]] ^= bits[wires[0]]
        elif name == "ccx":
            bits[wires[2]] ^= bits[wires[0]] * bits[wires[1]]
        else:
            raise AssertionError("unknown oracle operation")
    return bits


def test_exact_physical_positions_and_versioned_dependencies(tmp_path):
    raw = (b'# context\r\nREGISTER r "a label"\r\nCX q0 q2\r\n'
           b'X q0\nCX q4 q5\nCCX q2 q3 q1\nX q2')
    path, sha = _source(tmp_path, raw)
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        cone = index.cone(stop_op=4, observed_wires=(1,), expected_source_sha256=sha)
        assert cone["gate_indices"] == [0, 3]
        assert cone["op_lines"] == [3, 6]
        assert cone["global_wires"] == [0, 1, 2, 3]
        assert cone["dependencies"] == [[0, [-1, -1]], [3, [0, -1, -1]]]
        assert cone["boundary_predecessors"] == [
            {"wire": q, "previous_writer": -1} for q in range(4)
        ]
        for byte_span, name in zip(cone["byte_spans"], (b"CX q0 q2\r\n", b"CCX q2 q3 q1\n")):
            assert raw[slice(*byte_span)] == name
        assert index.metadata()["source_ops"] == 5
        assert index.metadata()["source_lines"] == 7
        assert cone["source"]["position_basis"] == "zero_based_semantic_operation"
        assert cone["source"]["line_basis"] == "one_based_physical_LF_or_CRLF"
        assert cone["proved"] is False and cone["candidate_authorized"] is False


def test_windows_and_cones_match_independent_scalar_semantics(tmp_path):
    rng = random.Random(71891)
    for case in range(25):
        width = 3 + case % 4
        operations = []
        raw = b'# synthetic development fixture\n'
        for step in range(35):
            arity = rng.randint(1, 3)
            name = {1: "x", 2: "cx", 3: "ccx"}[arity]
            wires = tuple(rng.sample(range(width), arity))
            operations.append((name, wires))
            raw += (name.upper() + " " + " ".join(f"q{q}" for q in wires) + "\n").encode()
            if step % 4 == 0:
                raw += b'INFO_TAG ignored metadata\n'
        path, sha = _source(tmp_path, raw)
        with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
            start, stop = rng.randrange(15), rng.randrange(15, 36)
            observed = tuple(rng.sample(range(width), rng.randint(1, width)))
            for kind in ("window", "cone"):
                record = (index.window(start_op=start, stop_op=stop, expected_source_sha256=sha)
                          if kind == "window" else index.cone(
                              start_op=start, stop_op=stop, observed_wires=observed,
                              expected_source_sha256=sha))
                wires = record["global_wires"]
                for value in range(1 << width):
                    local = sum(((value >> q) & 1) << i for i, q in enumerate(wires))
                    expected = _scalar(width, operations[start:stop], value)
                    actual = _scalar(len(wires), record["program"]["gates"], local)
                    compared = wires if kind == "window" else observed
                    assert all(expected[q] == actual[wires.index(q)] for q in compared)


def test_cut_is_arbitrary_and_predecessors_are_context_not_zero_assumptions(tmp_path):
    path, sha = _source(tmp_path, b"X q2\nCCX q0 q1 q2\nCX q2 q3\n")
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        cone = index.cone(start_op=1, stop_op=3, observed_wires=(3,), expected_source_sha256=sha)
        assert cone["gate_indices"] == [1, 2]
        assert cone["boundary_inputs"] == "arbitrary"
        assert {r["wire"]: r["previous_writer"] for r in cone["boundary_predecessors"]}[2] == 0
        assert cone["dependencies"] == [[1, [-1, -1, 0]], [2, [1, -1]]]


def test_identity_output_and_empty_cone_are_explicit(tmp_path):
    path, sha = _source(tmp_path, b"X q5\n")
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        record = index.cone(stop_op=1, observed_wires=(2,), expected_source_sha256=sha)
        assert record["global_wires"] == [2]
        assert record["gate_indices"] == []
        assert record["program"] == {"kind": "classical_reversible", "width": 1, "gates": []}
        origin = index.cone(stop_op=0, observed_wires=(5,), expected_source_sha256=sha)
        assert origin["gate_indices"] == []


def test_reuse_does_not_reopen_or_rescan_original_source(tmp_path):
    # Above the prepare-rewrite 2 MB input cap, with a small exact dependency cone.
    noise = b"X q5 # unrelated operation with an intentionally longer comment\n" * 40_000
    raw = noise + b"CCX q0 q1 q2\n" + noise
    assert len(raw) > 2_000_000
    path, sha = _source(tmp_path, raw)
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        path.unlink()
        for _ in range(3):
            cone = index.cone(stop_op=80_001, observed_wires=(0, 1, 2),
                              expected_source_sha256=sha)
            assert cone["gate_indices"] == [40_000]
            assert cone["work"]["sql_queries"] == 7
            assert cone["work"]["read_bytes"] == len(b"CCX q0 q1 q2\n")
            assert cone["work"]["dependency_visits"] == 6
        window = index.window(start_op=39_999, stop_op=40_002, expected_source_sha256=sha)
        assert window["gate_indices"] == [39_999, 40_000, 40_001]


def test_source_mutation_after_build_cannot_change_owned_snapshot(tmp_path):
    path, sha = _source(tmp_path)
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        before = index.window(start_op=0, stop_op=1, expected_source_sha256=sha)
        path.write_bytes(b"X q2\n")
        assert index.window(start_op=0, stop_op=1, expected_source_sha256=sha) == before
        with pytest.raises(ValueError, match="SHA-256"):
            indexes.build_kmx_index(path, expected_source_sha256=sha)
        with pytest.raises(ValueError, match="pin"):
            index.window(start_op=0, stop_op=1, expected_source_sha256="0" * 64)


def test_rebuild_matches_logical_index_identity_and_replays_receipt(tmp_path):
    path, sha = _source(tmp_path, b"CX q0 q2\nX q0\nCCX q2 q3 q1\n")
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as first:
        record = first.cone(stop_op=3, observed_wires=(1,), expected_source_sha256=sha)
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as second:
        verified = second.verify_cone(json.loads(json.dumps(record)), stop_op=3,
                                      observed_wires=(1,), expected_source_sha256=sha)
        assert verified.to_dict() == record["program"]
        window = second.window(start_op=1, stop_op=3, expected_source_sha256=sha)
        assert second.verify_window(window, start_op=1, stop_op=3,
                                    expected_source_sha256=sha).to_dict() == window["program"]


def test_receipt_mutants_cannot_bypass_dependency_closure(tmp_path):
    path, sha = _source(tmp_path, b"CX q0 q2\nCCX q2 q3 q1\nX q4\n")
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        record = index.cone(stop_op=2, observed_wires=(1,), expected_source_sha256=sha)
        for field, value in (
            ("dependencies", [[0, [-1, -1]], [1, [-1, -1, -1]]]),
            ("gate_indices", [1]), ("global_wires", [0, 2, 1, 3]),
            ("op_lines", [2, 3]), ("byte_spans", [[0, 1], [1, 2]]),
            ("op_span", [1, 2]), ("boundary_inputs", "clean"),
            ("candidate_authorized", True), ("schema_version", True),
        ):
            mutant = copy.deepcopy(record)
            mutant[field] = value
            with pytest.raises(ValueError, match="receipt"):
                index.verify_cone(mutant, stop_op=2, observed_wires=(1,), expected_source_sha256=sha)
        mutant = copy.deepcopy(record)
        mutant["source"]["index_sha256"] = "0" * 64
        with pytest.raises(ValueError, match="receipt"):
            index.verify_cone(mutant, stop_op=2, observed_wires=(1,), expected_source_sha256=sha)
        with pytest.raises(TypeError, match="manifest"):
            indexes.KmxSourceIndex(_metadata=record["source"])
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            index._db.execute("DELETE FROM operations")


@pytest.mark.parametrize("tail", [
    b"HMR q0 b0\n", b"Z q0\n", b"R q0\n", b"SWAP q0 q1\n", b"CSWAP q0 q1 q2\n",
    b"CX q0 q1 if b0\n", b"UNKNOWN q0\n", b"INFO_TAG_NOT_METADATA hidden\n",
    b"X q0\r", b"# hidden\vX q0\n", b"# hidden\xe2\x80\xa8X q0\n",
])
def test_unsupported_anywhere_refuses_entire_build(tmp_path, tail):
    path, sha = _source(tmp_path, b"X q0\n" * 30 + tail)
    with pytest.raises(UnsupportedOperation):
        indexes.build_kmx_index(path, expected_source_sha256=sha)


@pytest.mark.parametrize("limits", [
    indexes.IndexLimits(max_source_bytes=1), indexes.IndexLimits(max_index_bytes=4096),
    indexes.IndexLimits(max_source_ops=1), indexes.IndexLimits(max_line_bytes=3),
    indexes.IndexLimits(max_wires=1), indexes.IndexLimits(max_wire_index=1),
])
def test_construction_caps_raise_and_remove_partial_owned_files(tmp_path, monkeypatch, limits):
    path, sha = _source(tmp_path, b"CCX q0 q1 q2\nX q2\n")
    directory = indexes.tempfile.TemporaryDirectory
    created = []

    def tracked(*args, **kwargs):
        result = directory(*args, **kwargs)
        created.append(result.name)
        return result

    monkeypatch.setattr(indexes.tempfile, "TemporaryDirectory", tracked)
    with pytest.raises(ResourceLimitExceeded):
        indexes.build_kmx_index(path, expected_source_sha256=sha, limits=limits)
    assert created and all(not os.path.exists(name) for name in created)


@pytest.mark.parametrize("limits", [
    indexes.QueryLimits(max_selected_ops=1), indexes.QueryLimits(max_selected_wires=1),
    indexes.QueryLimits(max_dependency_visits=1), indexes.QueryLimits(max_sql_queries=1),
    indexes.QueryLimits(max_result_rows=1), indexes.QueryLimits(max_read_bytes=1),
])
def test_query_caps_raise_without_returning_a_partial_selection(tmp_path, limits):
    path, sha = _source(tmp_path, b"CX q0 q2\nCCX q2 q3 q1\n")
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        with pytest.raises(ResourceLimitExceeded):
            index.cone(stop_op=2, observed_wires=(1,), expected_source_sha256=sha, limits=limits)
        # A failed query neither corrupts the index nor extends the next query's budget.
        assert index.cone(stop_op=2, observed_wires=(1,), expected_source_sha256=sha)["status"] == "extracted"


def test_expired_deadlines_and_closed_handles_fail_closed(tmp_path):
    path, sha = _source(tmp_path)
    expired = Budget(absolute_deadline=0)
    with pytest.raises(ResourceLimitExceeded):
        indexes.build_kmx_index(path, expected_source_sha256=sha, budget=expired)
    index = indexes.build_kmx_index(path, expected_source_sha256=sha)
    directory = index._directory.name
    with index:
        record = index.cone(stop_op=1, observed_wires=(2,), expected_source_sha256=sha)
        with pytest.raises(ResourceLimitExceeded):
            index.cone(stop_op=1, observed_wires=(2,), expected_source_sha256=sha, budget=expired)
        with pytest.raises(ResourceLimitExceeded):
            index.verify_cone(record, stop_op=1, observed_wires=(2,),
                              expected_source_sha256=sha, budget=expired)
    assert not os.path.exists(directory)
    index.close()
    with pytest.raises(ValueError, match="closed"):
        index.window(start_op=0, stop_op=1, expected_source_sha256=sha)
    with pytest.raises(ValueError, match="closed"):
        index.metadata()


def test_fifo_is_rejected_without_blocking(tmp_path):
    path = tmp_path / "fifo.kmx"
    os.mkfifo(path)
    with pytest.raises(UnsupportedOperation, match="regular file"):
        indexes.build_kmx_index(path, expected_source_sha256="0" * 64)


def test_line_cap_cannot_overflow_the_platform_readline_size():
    with pytest.raises(ValueError, match="readline sentinel"):
        indexes.IndexLimits(max_line_bytes=sys.maxsize)


@pytest.mark.parametrize("kwargs", [
    {"stop_op": True}, {"start_op": True}, {"stop_op": 2}, {"observed_wires": (True,)},
    {"observed_wires": (0, 0)}, {"observed_wires": (3,)},
])
def test_position_and_wire_type_refusals(tmp_path, kwargs):
    path, sha = _source(tmp_path)
    with indexes.build_kmx_index(path, expected_source_sha256=sha) as index:
        params = {"stop_op": 1, "observed_wires": (2,), **kwargs}
        with pytest.raises(ValueError):
            index.cone(expected_source_sha256=sha, **params)
