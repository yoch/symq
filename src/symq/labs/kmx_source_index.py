"""Owned, reusable disk index for strict classical KMX sources (research API).

Build once from independently pinned bytes; query windows or versioned backward
dependencies without rescanning the source. Only unconditional X/CX/CCX are
accepted, throughout the whole file. Saved manifests cannot reopen an index:
only a complete checked build issues an in-process handle. Neither extraction
nor dependency closure proves a prepared state or authorizes substitution.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from symq.circuit import Circuit, Gate, circuit_from_dict
from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.hashing import canonical_sha256
from symq.kickmix import KmxOp, parse_kmx
from symq.resources import Budget, Guard

__all__ = ["IndexLimits", "KmxSourceIndex", "QueryLimits", "build_kmx_index"]

_ISSUED = object()
_PIN = re.compile(r"[0-9a-f]{64}\Z")
_LINE_PREFIX = re.compile(r"^line \d+: ")
_NAMES = {"X": 1, "CX": 2, "CCX": 3}
_KINDS = {value: name for name, value in _NAMES.items()}
_RECORD = struct.Struct("<11q")
_FORMAT = "strict_kmx_classical_dependency_index_v1"


@dataclass(frozen=True)
class IndexLimits:
    """Construction caps, including retained snapshot and main SQLite file bytes."""

    max_source_bytes: int = 2 * 1024**3
    max_index_bytes: int = 4 * 1024**3
    max_source_ops: int = 100_000_000
    max_line_bytes: int = 1_000_000
    max_wires: int = 100_000
    max_wire_index: int = 2**31 - 1
    sqlite_cache_kib: int = 8192

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value < 2**63:
                raise ValueError(f"{name} must be a positive integer below 2**63")
        if self.max_index_bytes < 4096:
            raise ValueError("max_index_bytes must allow at least one SQLite page")
        if self.max_line_bytes >= sys.maxsize:
            raise ValueError("max_line_bytes must leave room for a bounded readline sentinel")


@dataclass(frozen=True)
class QueryLimits:
    """Per-query caps; all SQL results, visited dependencies and reads are counted."""

    max_selected_ops: int = 20_000
    max_selected_wires: int = 256
    max_dependency_visits: int = 100_000
    max_sql_queries: int = 100_000
    max_result_rows: int = 100_000
    max_read_bytes: int = 32 * 1024**2

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


_INDEX_LIMITS = IndexLimits()
_QUERY_LIMITS = QueryLimits()


def _pin(value: str) -> None:
    if type(value) is not str or _PIN.fullmatch(value) is None:
        raise ValueError("expected_source_sha256 must be a lowercase SHA-256 digest")


def _guard(budget: Budget | None, seconds: int) -> Guard:
    guard = Guard(Budget(max_seconds=seconds) if budget is None else budget)
    if any(getattr(guard.budget, field) is not None
           for field in ("max_terms", "max_nodes", "max_bytes")):
        raise ValueError("source indexes use time budgets and explicit index/query limits")
    return guard


def _over(resource: str, limit: int, value: int) -> None:
    if value > limit:
        raise ResourceLimitExceeded(resource, limit, value)


def _line(raw: bytes, number: int) -> KmxOp | None:
    text = raw.decode("utf-8")
    if text.endswith("\r"):
        raise UnsupportedOperation(f"line {number}: bare CR is not an LF or CRLF separator")
    body = text.removesuffix("\n").removesuffix("\r")
    if body.splitlines() not in ([], [body]):
        raise UnsupportedOperation(f"line {number}: only LF or CRLF line separators are supported")
    try:
        parsed = parse_kmx(body)
    except (ValueError, UnsupportedOperation) as error:
        message = _LINE_PREFIX.sub("", str(error), count=1)
        raise type(error)(f"line {number}: {message}") from error
    if not parsed.ops:
        return None
    if len(parsed.ops) != 1:
        raise UnsupportedOperation(f"line {number}: expected at most one semantic operation")
    op = parsed.ops[0]
    if op.name not in _NAMES or op.condition is not None:
        raise UnsupportedOperation(
            f"line {number}: the index accepts only unconditional X/CX/CCX, got {op.name}"
        )
    return op


def _copy(source: BinaryIO, snapshot: BinaryIO, expected: str,
          guard: Guard, limits: IndexLimits) -> int:
    size = os.fstat(source.fileno()).st_size
    _over("source snapshot bytes", limits.max_source_bytes, size)
    digest = hashlib.sha256()
    remaining = size
    while remaining:
        guard.check_time()
        chunk = source.read(min(1 << 20, remaining))
        if not chunk:
            raise ValueError("source was truncated during the private snapshot copy")
        snapshot.write(chunk)
        digest.update(chunk)
        remaining -= len(chunk)
    if os.fstat(source.fileno()).st_size != size or source.read(1):
        raise ValueError("source size changed during the private snapshot copy")
    guard.check_time()
    if digest.hexdigest() != expected:
        raise ValueError("snapshot bytes differ from the independently supplied source SHA-256")
    snapshot.flush()
    snapshot.seek(0)
    guard.check_time()
    return size


def _cancel(guard: Guard):
    def callback() -> int:
        try:
            guard.check_time()
        except ResourceLimitExceeded:
            return 1
        return 0
    return callback


@dataclass
class _Query:
    owner: KmxSourceIndex
    guard: Guard
    limits: QueryLimits
    sql_queries: int = 0
    result_rows: int = 0
    dependency_visits: int = 0
    read_bytes: int = 0

    def row(self, sql: str, parameters: tuple[int, ...]) -> tuple | None:
        self.guard.check_time()
        self.sql_queries += 1
        _over("index SQL queries", self.limits.max_sql_queries, self.sql_queries)
        db = self.owner._db
        db.set_progress_handler(_cancel(self.guard), 100)
        try:
            row = db.execute(sql, parameters).fetchone()
        except sqlite3.DatabaseError:
            self.guard.check_time()
            raise
        finally:
            db.set_progress_handler(None, 0)
        self.guard.check_time()
        if row is not None:
            self.result_rows += 1
            _over("index result rows", self.limits.max_result_rows, self.result_rows)
        return row

    def writer(self, wire: int, before: int) -> int:
        row = self.row("SELECT op FROM writers WHERE wire=? AND op<? ORDER BY op DESC LIMIT 1",
                       (wire, before))
        return -1 if row is None else row[0]

    def operation(self, index: int) -> tuple:
        row = self.row("SELECT * FROM operations WHERE op=?", (index,))
        if row is None or row[0] != index:
            raise ValueError("the owned index contains no requested operation")
        ordinal, line, offset, length, arity, *rest = row
        wires, predecessors = tuple(rest[:arity]), tuple(rest[3:3 + arity])
        if (arity not in _KINDS or offset < 0 or length < 1
                or offset + length > self.owner._metadata["source_bytes"]
                or any(p < -1 or p >= ordinal for p in predecessors)):
            raise ValueError("invalid owned dependency record")
        self.read_bytes += length
        _over("selected source bytes", self.limits.max_read_bytes, self.read_bytes)
        self.owner._snapshot.seek(offset)
        raw = self.owner._snapshot.read(length)
        self.guard.check_time()
        if len(raw) != length:
            raise ValueError("private snapshot has been truncated")
        op = _line(raw, line)
        if op is None or op.name != _KINDS[arity] or op.qubits != wires:
            raise ValueError("owned index operation contradicts private snapshot bytes")
        return row

    def counters(self) -> dict[str, int]:
        return {"sql_queries": self.sql_queries, "result_rows": self.result_rows,
                "dependency_visits": self.dependency_visits, "read_bytes": self.read_bytes}


class KmxSourceIndex:
    """Builder-issued handle; private snapshot/database are closed together.

    Reuse is within this handle's lifetime, on its creating thread. There is no
    loader accepting an external SQLite file, manifest, or serialized handle.
    Private attributes are not a security boundary against hostile Python in
    the same interpreter, as with the other research proof APIs.
    """

    def __init__(self, *, _token: object = None, _directory: Any = None,
                 _snapshot: Any = None, _db: Any = None, _metadata: Any = None):
        if _token is not _ISSUED:
            raise TypeError("use build_kmx_index; a manifest cannot issue an index handle")
        self._directory = _directory
        self._snapshot = _snapshot
        self._db = _db
        self._metadata = _metadata
        self._closed = False
        self._token = _token

    def _require(self) -> None:
        if self._token is not _ISSUED or self._closed:
            raise ValueError("source index is closed or was not issued by the builder")

    def __enter__(self) -> KmxSourceIndex:  # noqa: PYI034 - Python 3.10, no typing_extensions dep
        self._require()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._db.close()
            finally:
                try:
                    self._snapshot.close()
                finally:
                    self._directory.cleanup()

    def metadata(self) -> dict[str, Any]:
        self._require()
        return dict(self._metadata)

    def _query(self, start: int, stop: int, expected: str, limits: QueryLimits,
               budget: Budget | None) -> _Query:
        self._require()
        _pin(expected)
        if expected != self._metadata["source_file_sha256"]:
            raise ValueError("query source pin differs from the owned immutable snapshot")
        if (type(start) is not int or type(stop) is not int
                or not 0 <= start <= stop <= self._metadata["source_ops"]):
            raise ValueError("expected 0 <= start_op <= stop_op <= source operations")
        if type(limits) is not QueryLimits:
            raise TypeError("limits must be QueryLimits")
        limits.__post_init__()
        guard = _guard(budget, 30)
        guard.check_time()
        return _Query(self, guard, limits)

    def _selection(self, query: _Query, rows: list[tuple], *, kind: str,
                   start: int, stop: int, observed: tuple[int, ...]) -> dict[str, Any]:
        rows.sort(key=lambda row: row[0])
        wires = set(observed)
        for row in rows:
            query.guard.check_time()
            wires.update(row[5:5 + row[4]])
            _over("selected wires", query.limits.max_selected_wires, len(wires))
        if not wires:
            raise ValueError("selection has no wire to map")
        mapping = {q: i for i, q in enumerate(sorted(wires))}
        gates = []
        for row in rows:
            query.guard.check_time()
            gates.append(Gate(_KINDS[row[4]].lower(), tuple(mapping[q] for q in row[5:5 + row[4]])))
        program = Circuit(len(mapping), gates).to_dict()
        boundary = []
        for q in mapping:
            boundary.append({"wire": q, "previous_writer": query.writer(q, start)})
        record = {
            "schema_version": 1, "kind": "symq_indexed_kmx_selection", "selection": kind,
            "status": "extracted", "source": self.metadata(),
            "op_span": [start, stop], "observed_wires": list(observed),
            "global_wires": list(mapping), "gate_indices": [row[0] for row in rows],
            "op_lines": [row[1] for row in rows],
            "byte_spans": [[row[2], row[2] + row[3]] for row in rows],
            "dependencies": [[row[0], list(row[8:8 + row[4]])] for row in rows],
            "boundary_predecessors": boundary, "boundary_inputs": "arbitrary",
            "program": program, "program_sha256": canonical_sha256(program),
            "advisory_only": True, "proved": False, "candidate_authorized": False,
            "work": query.counters(),
        }
        query.guard.check_time()
        return record

    def window(self, *, start_op: int, stop_op: int, expected_source_sha256: str,
               limits: QueryLimits = _QUERY_LIMITS, budget: Budget | None = None) -> dict[str, Any]:
        """Read one contiguous semantic-operation window; no source-wide scan."""
        query = self._query(start_op, stop_op, expected_source_sha256, limits, budget)
        if start_op == stop_op:
            raise ValueError("window must contain at least one semantic operation")
        _over("selected operations", limits.max_selected_ops, stop_op - start_op)
        rows = [query.operation(index) for index in range(start_op, stop_op)]
        return self._selection(query, rows, kind="window", start=start_op, stop=stop_op, observed=())

    def cone(self, *, stop_op: int, observed_wires: tuple[int, ...],
             expected_source_sha256: str, start_op: int = 0,
             limits: QueryLimits = _QUERY_LIMITS, budget: Budget | None = None) -> dict[str, Any]:
        """Follow versioned writers for exact selected-output closure at a cut.

        Output wires are global. An unused wire below the inferred global width
        is an identity input. Only the requested outputs, not all mapped local
        outputs, agree with the original interval on every boundary assignment.
        """
        query = self._query(start_op, stop_op, expected_source_sha256, limits, budget)
        if type(observed_wires) is not tuple or not observed_wires:
            raise ValueError("observed_wires must be a nonempty tuple of distinct global wires")
        _over("selected wires", limits.max_selected_wires, len(observed_wires))
        if (any(type(q) is not int or not 0 <= q < self._metadata["global_width"]
                       for q in observed_wires) or len(set(observed_wires)) != len(observed_wires)):
            raise ValueError("observed_wires must be a bounded nonempty tuple of distinct global wires")
        observed = tuple(sorted(observed_wires))
        pending = [query.writer(q, stop_op) for q in observed]
        seen: set[int] = set()
        rows = []
        wires = set(observed)
        while pending:
            query.guard.check_time()
            query.dependency_visits += 1
            _over("dependency visits", limits.max_dependency_visits, query.dependency_visits)
            index = pending.pop()
            if index < start_op or index in seen:
                continue
            _over("selected operations", limits.max_selected_ops, len(rows) + 1)
            row = query.operation(index)
            seen.add(index)
            rows.append(row)
            wires.update(row[5:5 + row[4]])
            _over("selected wires", limits.max_selected_wires, len(wires))
            pending.extend(row[8:8 + row[4]])
        return self._selection(query, rows, kind="cone", start=start_op, stop=stop_op,
                               observed=observed)

    def verify_window(self, record: dict[str, Any], **query: Any) -> Circuit:
        """Re-extract from the owned snapshot and compare every receipt field."""
        guard = _guard(query.get("budget"), 30)
        query["budget"] = guard.inherited_budget()
        return self._verify(record, self.window(**query), guard)

    def verify_cone(self, record: dict[str, Any], **query: Any) -> Circuit:
        """Recompute dependency closure, not just the selected circuit hash."""
        guard = _guard(query.get("budget"), 30)
        query["budget"] = guard.inherited_budget()
        return self._verify(record, self.cone(**query), guard)

    @staticmethod
    def _verify(record: dict[str, Any], fresh: dict[str, Any], guard: Guard) -> Circuit:
        # Expected-shape recursion bounds work and rejects bool/int confusion.
        def same(value: Any, expected: Any) -> bool:
            guard.check_time()
            if type(value) is not type(expected):
                return False
            if type(expected) is dict:
                return value.keys() == expected.keys() and all(
                    same(value[k], v) for k, v in expected.items())
            if type(expected) is list:
                return len(value) == len(expected) and all(same(a, b) for a, b in zip(value, expected))
            return bool(value == expected)

        if not same(record, fresh):
            raise ValueError("selection receipt differs from pinned source, position or dependency closure")
        program = circuit_from_dict(fresh["program"])
        guard.check_time()
        return program


def build_kmx_index(
    path: str | Path, *, expected_source_sha256: str,
    limits: IndexLimits = _INDEX_LIMITS, budget: Budget | None = None,
) -> KmxSourceIndex:
    """Copy/hash once, then parse the private image and build a disk-backed index.

    Copying is not an atomic instant of the original path: the independently
    supplied digest identifies the complete copied bytes. Snapshot and SQLite
    storage are owned by the returned context-manager handle and removed on
    close. Any error closes/removes partial construction; no handle is issued.
    """
    guard = _guard(budget, 180)
    _pin(expected_source_sha256)
    if type(limits) is not IndexLimits:
        raise TypeError("limits must be IndexLimits")
    limits.__post_init__()
    source = Path(path)
    if source.suffix.lower() != ".kmx":
        raise UnsupportedOperation("this index reads strict text .kmx only, not binary .kmb")
    directory = tempfile.TemporaryDirectory(prefix="symq-kmx-index-")
    snapshot = None
    db = None
    issued = False
    database = Path(directory.name) / "operations.sqlite"
    try:
        guard.check_time()
        snapshot = tempfile.TemporaryFile(mode="w+b", dir=directory.name)  # noqa: SIM115 - handle-owned
        fd = os.open(source, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise UnsupportedOperation("the indexed source must be a regular file")
            size = _copy(stream, snapshot, expected_source_sha256, guard, limits)
        db = sqlite3.connect(database)
        db.execute("PRAGMA page_size=4096")
        db.execute(f"PRAGMA max_page_count={limits.max_index_bytes // 4096}")
        db.execute(f"PRAGMA cache_size=-{limits.sqlite_cache_kib}")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA temp_store=FILE")
        db.set_progress_handler(_cancel(guard), 1000)
        db.execute("CREATE TABLE operations (op INTEGER PRIMARY KEY, line INTEGER, offset INTEGER, "
                   "length INTEGER, arity INTEGER, q0 INTEGER, q1 INTEGER, q2 INTEGER, "
                   "p0 INTEGER, p1 INTEGER, p2 INTEGER)")
        db.execute("CREATE TABLE writers (wire INTEGER, op INTEGER, PRIMARY KEY(wire, op)) WITHOUT ROWID")
        last: dict[int, int] = {}
        count = lines = offset = 0
        records = hashlib.sha256()
        while True:
            guard.check_time()
            raw = snapshot.readline(limits.max_line_bytes + 1)
            if not raw:
                break
            lines += 1
            _over("source line bytes", limits.max_line_bytes, len(raw))
            op = _line(raw, lines)
            if op is not None:
                _over("indexed source operations", limits.max_source_ops, count + 1)
                for wire in op.qubits:
                    _over("global wire index", limits.max_wire_index, wire)
                    if wire not in last:
                        _over("distinct indexed wires", limits.max_wires, len(last) + 1)
                        last[wire] = -1
                arity = _NAMES[op.name]
                qubits = op.qubits + (-1,) * (3 - arity)
                previous = tuple(last[q] for q in op.qubits) + (-1,) * (3 - arity)
                row = (count, lines, offset, len(raw), arity, *qubits, *previous)
                db.execute("INSERT INTO operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
                db.execute("INSERT INTO writers VALUES (?, ?)", (op.qubits[-1], count))
                records.update(_RECORD.pack(*row))
                last[op.qubits[-1]] = count
                count += 1
            offset += len(raw)
        if not count:
            raise ValueError("source contains no supported semantic operation")
        guard.check_time()
        db.commit()
        db.close()
        db = None
        guard.check_time()
        _over("index bytes", limits.max_index_bytes, database.stat().st_size)
        # No external path is accepted for reopening: this is the database just
        # constructed above, in a private directory. Queries cannot write it.
        os.chmod(database, 0o400)
        db = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
        db.execute(f"PRAGMA cache_size=-{limits.sqlite_cache_kib}")
        metadata = {
            "schema_version": 1, "format": _FORMAT,
            "source_file_sha256": expected_source_sha256, "source_bytes": size,
            "source_ops": count, "source_lines": lines, "global_width": max(last) + 1,
            "indexed_wires": len(last), "position_basis": "zero_based_semantic_operation",
            "line_basis": "one_based_physical_LF_or_CRLF", "byte_basis": "zero_based_raw_bytes",
            "records_sha256": records.hexdigest(),
        }
        metadata["index_sha256"] = canonical_sha256(metadata)
        guard.check_time()
        index = KmxSourceIndex(_token=_ISSUED, _directory=directory,
                               _snapshot=snapshot, _db=db, _metadata=metadata)
        issued = True
        return index
    except sqlite3.DatabaseError as error:
        guard.check_time()
        # sqlite_errorcode is unavailable on Python 3.10. Do not pretend to
        # measure an overshoot: SQLITE_FULL also covers unavailable disk space.
        if (getattr(error, "sqlite_errorcode", None) == 13
                or str(error) == "database or disk is full"):
            raise ResourceLimitExceeded(
                "index storage failures", 0, 1,
                f"SQLite storage full: page cap is {limits.max_index_bytes} bytes; "
                "filesystem exhaustion is also possible; no index was issued",
            ) from error
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
