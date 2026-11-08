"""Strict classical KMB-v2 index, in the existing raw-opcode coordinates.

Reuses the official-format layout reader and owned dependency/query engine.
All source operations must be unconditional X/CX/CCX (plus INFO_TAG metadata).
Hybrid sources are refused in their entirety, not silently lowered to values.
"""
from __future__ import annotations

import copy
import hashlib
import mmap
import os
import sqlite3
import stat
import struct
import tempfile
from pathlib import Path

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.hashing import canonical_sha256
from symq.labs.kmb_window import _layout
from symq.labs.kmx_source_index import (
    _ISSUED,
    _QUERY_LIMITS,
    _RECORD,
    IndexLimits,
    KmxSourceIndex,
    QueryLimits,
    _cancel,
    _copy,
    _guard,
    _over,
    _pin,
)
from symq.resources import Budget, Guard

__all__ = ["KmbSourceIndex", "build_kmb_index"]

_LIMITS = IndexLimits()
_ARITY = {0x11: 1, 0x21: 2, 0x31: 3}
_PACKETS = {1: (7,), 2: (5, 6), 3: (2, 3, 4)}


class KmbSourceIndex(KmxSourceIndex):
    """Builder-issued KMB snapshot; no external database/manifest reopening."""

    def metadata(self) -> dict:
        self._require()
        return copy.deepcopy(self._metadata)

    def _row_read_bytes(self, row: tuple) -> int:
        return 1 + 4 * row[4]

    def _validate_source_row(self, row: tuple, guard: Guard) -> None:
        ordinal, group_index, offset, length, arity, *rest = row
        self._snapshot.seek(offset)
        raw = self._snapshot.read(1)
        if len(raw) != 1 or _ARITY.get(raw[0]) != arity:
            raise ValueError("KMB index contradicts source opcode")
        if offset != self._metadata["opcode_packet_offset"] + ordinal or length != 1:
            raise ValueError("KMB index contradicts source coordinates")
        wires = []
        for packet in _PACKETS[arity]:
            if not 0 <= group_index < self._metadata["operand_group_counts"][str(arity)]:
                raise ValueError("KMB group coordinate outside source packet")
            at = self._metadata["operand_packet_offsets"][str(packet)] + 4 * group_index
            self._snapshot.seek(at)
            value = self._snapshot.read(4)
            if len(value) != 4:
                raise ValueError("KMB operand packet truncated")
            wires.append(struct.unpack("<I", value)[0])
            guard.check_time()
        if wires != rest[:arity]:
            raise ValueError("KMB index contradicts source operand bytes")

    def _selection(self, query, rows, **kwargs):
        result = super()._selection(query, rows, **kwargs)
        result["kind"] = "symq_indexed_kmb_selection"
        result["operand_group_indices"] = result.pop("op_lines")
        result["operand_byte_spans"] = [
            [[self._metadata["operand_packet_offsets"][str(p)] + 4 * row[1],
              self._metadata["operand_packet_offsets"][str(p)] + 4 * row[1] + 4]
             for p in _PACKETS[row[4]]] for row in rows]
        query.guard.check_time()
        return result

    def window(self, *, start_op: int, stop_op: int, expected_source_sha256: str,
               limits: QueryLimits = _QUERY_LIMITS, budget: Budget | None = None) -> dict:
        """Complete window in raw KMB coordinates; INFO_TAGs emit no gates."""
        query = self._query(start_op, stop_op, expected_source_sha256, limits, budget)
        if start_op == stop_op:
            raise ValueError("window must contain at least one raw source operation")
        rows, previous = [], start_op - 1
        while True:
            row = query.row("SELECT op FROM operations WHERE op>? AND op<? ORDER BY op LIMIT 1",
                            (previous, stop_op))
            if row is None:
                break
            _over("selected operations", limits.max_selected_ops, len(rows) + 1)
            previous = row[0]
            rows.append(query.operation(previous))
        if not rows:
            raise UnsupportedOperation("KMB window contains only metadata")
        return self._selection(query, rows, kind="window", start=start_op, stop=stop_op, observed=())


def build_kmb_index(path: str | Path, *, expected_source_sha256: str,
                    limits: IndexLimits = _LIMITS, budget: Budget | None = None) -> KmbSourceIndex:
    """Copy/hash the full file, validate canonical v2 layout, index strict operations.

    Whole-file semantic validation refuses resets, phases, SWAP/CSWAP, HMR,
    classical writes/conditions/stacks, debug opcodes and unknown opcodes.
    INFO_TAG alone is inert metadata and retains its raw coordinate.
    """
    guard = _guard(budget, 180)
    _pin(expected_source_sha256)
    if type(limits) is not IndexLimits:
        raise TypeError("limits must be IndexLimits")
    limits.__post_init__()
    source = Path(path)
    if source.suffix.lower() != ".kmb":
        raise UnsupportedOperation("strict binary .kmb v2 source required")
    directory = tempfile.TemporaryDirectory(prefix="symq-kmb-index-")
    snapshot = db = None
    issued = False
    database = Path(directory.name) / "operations.sqlite"
    try:
        snapshot = tempfile.TemporaryFile(mode="w+b", dir=directory.name)  # noqa: SIM115
        fd = os.open(source, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise UnsupportedOperation("indexed source must be a regular file")
            size = _copy(stream, snapshot, expected_source_sha256, guard, limits)
        with mmap.mmap(snapshot.fileno(), 0, access=mmap.ACCESS_READ) as view:
            info, packets = _layout(view, max_registers=100_000,
                                    max_register_entries=5_000_000,
                                    max_ops=limits.max_source_ops,
                                    max_seconds_deadline=guard.deadline or float("inf"))
            guard.check_time()
            _over("global wire index", limits.max_wire_index, info["num_qubits"] - 1)
            db = sqlite3.connect(database)
            db.execute("PRAGMA page_size=4096")
            db.execute(f"PRAGMA max_page_count={limits.max_index_bytes // 4096}")
            db.execute(f"PRAGMA cache_size=-{limits.sqlite_cache_kib}")
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.set_progress_handler(_cancel(guard), 1000)
            db.execute("CREATE TABLE operations (op INTEGER PRIMARY KEY, group_index INTEGER, "
                       "offset INTEGER, length INTEGER, arity INTEGER, q0 INTEGER, q1 INTEGER, "
                       "q2 INTEGER, p0 INTEGER, p1 INTEGER, p2 INTEGER)")
            db.execute("CREATE TABLE writers (wire INTEGER, op INTEGER, PRIMARY KEY(wire, op)) "
                       "WITHOUT ROWID")
            counts = {1: 0, 2: 0, 3: 0}
            tags = 0
            last = {}
            max_q = info["max_q_reg"]
            records = hashlib.sha256()
            for ordinal in range(info["num_ops"]):
                guard.check_time()
                opcode = view[packets[1] + ordinal]
                if opcode == 6:
                    tags += 1
                    continue
                if opcode not in _ARITY:
                    raise UnsupportedOperation(
                        f"KMB raw op {ordinal}: opcode {opcode:#x}; index accepts only "
                        "unconditional X/CX/CCX and INFO_TAG metadata")
                arity = _ARITY[opcode]
                pos = counts[arity]
                if pos >= info["counts"][3 - arity]:
                    raise ValueError("KMB opcode consumes more operands than declared")
                wires = tuple(struct.unpack_from("<I", view, packets[p] + 4 * pos)[0]
                              for p in _PACKETS[arity])
                if len(set(wires)) != arity or any(q >= info["num_qubits"] for q in wires):
                    raise ValueError("KMB repeated or out-of-range wire")
                for q in wires:
                    _over("global wire index", limits.max_wire_index, q)
                    if q not in last:
                        _over("distinct indexed wires", limits.max_wires, len(last) + 1)
                        last[q] = -1
                max_q = max(max_q, *wires)
                row = (ordinal, pos, packets[1] + ordinal, 1, arity,
                       *wires, *((-1,) * (3 - arity)),
                       *(last[q] for q in wires), *((-1,) * (3 - arity)))
                db.execute("INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
                db.execute("INSERT INTO writers VALUES (?, ?)", (wires[-1], ordinal))
                records.update(_RECORD.pack(*row))
                last[wires[-1]] = ordinal
                counts[arity] += 1
            actual_counts = (counts[3], counts[2], counts[1], 0, 0, 0, tags)
            if actual_counts != info["counts"]:
                raise ValueError("KMB opcodes contradict header counts")
            if max_q + 1 != info["num_qubits"] or info["max_b_reg"] + 1 != info["num_bits"]:
                raise ValueError("KMB maximum wire/bit ids contradict header")
            if not last:
                raise UnsupportedOperation("KMB contains no classical operation")
        guard.check_time()
        db.commit()
        db.close()
        db = None
        guard.check_time()
        _over("index bytes", limits.max_index_bytes, database.stat().st_size)
        os.chmod(database, 0o400)
        db = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
        db.execute(f"PRAGMA cache_size=-{limits.sqlite_cache_kib}")
        metadata = {"schema_version": 1, "format": "strict_kmb_v2_classical_dependency_index_v1",
                    "source_file_sha256": expected_source_sha256, "source_bytes": size,
                    "source_ops": info["num_ops"], "global_width": info["num_qubits"],
                    "indexed_wires": len(last), "semantic_ops": sum(counts.values()),
                    "position_basis": "zero_based_raw_KMB_operation_including_INFO_TAG",
                    "byte_basis": "zero_based_raw_bytes_struct_of_arrays",
                    "opcode_packet_offset": packets[1],
                    "operand_packet_offsets": {str(p): packets[p] for p in range(2, 8)},
                    "operand_group_counts": {str(k): v for k, v in counts.items()},
                    "records_sha256": records.hexdigest()}
        metadata["index_sha256"] = canonical_sha256(metadata)
        guard.check_time()
        result = KmbSourceIndex(_token=_ISSUED, _directory=directory,
                                _snapshot=snapshot, _db=db, _metadata=metadata)
        issued = True
        return result
    except sqlite3.DatabaseError as error:
        guard.check_time()
        if (getattr(error, "sqlite_errorcode", None) == 13
                or str(error) == "database or disk is full"):
            raise ResourceLimitExceeded("index storage failures", 0, 1, str(error)) from error
        raise
    finally:
        if not issued:
            try:
                if db is not None:
                    db.close()
            finally:
                try:
                    if snapshot is not None:
                        snapshot.close()
                finally:
                    directory.cleanup()
