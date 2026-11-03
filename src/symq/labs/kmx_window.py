"""Streaming, source-bound hybrid window extraction from strict Kickmix text.

Binary .kmb is NOT decoded. The result is advisory, never a quantum proof,
a cut-reachability certificate, or authorization to replace any operation.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.hybrid import HOp
from symq.experimental.serialization import encode_json
from symq.hashing import canonical_sha256
from symq.kickmix import KmxOp, parse_kmx
from symq.labs.channel_composition import HybridFragment
from symq.labs.rewrite_request import fragment_from_dict, fragment_to_dict

__all__ = ["extract_kmx_window", "verify_kmx_window"]

_PIN = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = {"X": "x", "CX": "cx", "CCX": "ccx", "SWAP": "swap",
          "CSWAP": "cswap", "Z": "z", "CZ": "cz", "CCZ": "ccz"}
_KIND = "symq_kmx_window"
_LINE_PREFIX = re.compile(r"^line \d+: ")
_KEYS = frozenset({
    "schema_version", "kind", "status", "source_format", "source_file_sha256",
    "source_bytes", "source_ops", "op_span", "line_span", "op_lines",
    "global_wires", "classical_predecessors", "fragment", "fragment_sha256",
    "advisory_only", "proved", "candidate_authorized",
})


def _positive(value: int, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive plain integer")


def _pin(digest: str) -> None:
    if type(digest) is not str or _PIN.fullmatch(digest) is None:
        raise ValueError("expected_source_sha256 must be a lowercase SHA-256 digest")


def _hop(op: KmxOp, mapping: dict[int, int]) -> HOp:
    wires = tuple(mapping[q] for q in op.qubits)
    if op.name == "HMR":
        assert op.bit is not None
        return HOp("hmr", wires, slot=f"b{op.bit}")
    return HOp(_KINDS[op.name], wires,
               condition=None if op.condition is None else f"b{op.condition}")


def extract_kmx_window(
    path: str | Path, *, start_op: int, stop_op: int,
    expected_source_sha256: str | None = None,
    max_source_bytes: int = 512_000_000,
    max_line_bytes: int = 1_000_000,
    max_source_ops: int = 10_000_000,
    max_window_ops: int = 20_000,
    max_window_wires: int = 256,
    max_classical_slots: int = 100_000,
) -> dict[str, Any]:
    """Bind a half-open operation range in .kmx, not a physical line range.

    The complete file is parsed and hashed once. Only the selected operations
    and last HMR writes are retained in memory. Any condition inherited from
    the prefix becomes an arbitrary classical fragment input and carries a
    record of the actual prefix HMR that last wrote its slot.

    No clean-wire hypothesis, source-level proof or quantum-channel proof is
    inferred. A file hash stored in the record is untrusted unless the caller
    separately supplies the expected value.
    """
    if (type(start_op) is not int or type(stop_op) is not int
            or start_op < 0 or stop_op <= start_op):
        raise ValueError("expected an increasing nonempty operation span")
    for value, name in ((max_source_bytes, "max_source_bytes"),
                        (max_line_bytes, "max_line_bytes"),
                        (max_source_ops, "max_source_ops"),
                        (max_window_ops, "max_window_ops"),
                        (max_window_wires, "max_window_wires"),
                        (max_classical_slots, "max_classical_slots")):
        _positive(value, name)
    if stop_op - start_op > max_window_ops:
        raise ResourceLimitExceeded("window operations", max_window_ops,
                                    stop_op - start_op)
    if expected_source_sha256 is not None:
        _pin(expected_source_sha256)
    source = Path(path)
    if source.suffix.lower() != ".kmx":
        raise UnsupportedOperation(
            "only strict text .kmx is supported; binary .kmb requires a verified exporter"
        )

    digest = hashlib.sha256()
    total = count = 0
    selected: list[KmxOp] = []
    last_write: dict[int, tuple[int, int]] = {}
    written_inside: set[int] = set()
    external: dict[int, tuple[int, int]] = {}
    # Open without blocking, then check the descriptor itself: a check on the
    # path before opening could be raced by swapping in a FIFO.
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise UnsupportedOperation("the Kickmix source must be a regular file")
        line_number = 0
        while True:
            raw = stream.readline(max_line_bytes + 1)
            if not raw:
                break
            line_number += 1
            if len(raw) > max_line_bytes:
                raise ResourceLimitExceeded("Kickmix line bytes", max_line_bytes, len(raw))
            total += len(raw)
            if total > max_source_bytes:
                raise ResourceLimitExceeded("Kickmix source bytes", max_source_bytes, total)
            digest.update(raw)
            text = raw.decode("utf-8")
            body = text.removesuffix("\n").removesuffix("\r")
            if body.splitlines() not in ([], [body]):
                # parse_kmx splits on CR, VT, FF, NEL, U+2028...; keep LF/CRLF only so
                # physical line numbers agree with load_kmx and no op hides in a comment.
                raise UnsupportedOperation(
                    f"line {line_number}: only LF or CRLF line separators are supported")
            try:
                parsed = parse_kmx(body)
            except (UnsupportedOperation, ValueError) as error:
                message = _LINE_PREFIX.sub("", str(error), count=1)
                raise type(error)(f"line {line_number}: {message}") from error
            if not parsed.ops:
                continue
            if len(parsed.ops) != 1:
                raise UnsupportedOperation("multiple instructions on a Kickmix line")
            original = parsed.ops[0]
            op = KmxOp(original.name, original.qubits, original.bit,
                       original.condition, line_number)
            if count >= max_source_ops:
                raise ResourceLimitExceeded("Kickmix source operations", max_source_ops,
                                            count + 1)
            if op.condition is not None:
                if op.condition not in last_write:
                    raise UnsupportedOperation(
                        f"line {line_number}: b{op.condition} used before HMR"
                    )
                if start_op <= count < stop_op and op.condition not in written_inside:
                    external.setdefault(op.condition, last_write[op.condition])
            if start_op <= count < stop_op:
                selected.append(op)
                if op.name == "HMR":
                    assert op.bit is not None
                    written_inside.add(op.bit)
            if op.name == "HMR":
                assert op.bit is not None
                if op.bit not in last_write and len(last_write) >= max_classical_slots:
                    raise ResourceLimitExceeded("classical slots", max_classical_slots,
                                                len(last_write) + 1)
                last_write[op.bit] = (count, line_number)
            count += 1

    source_digest = digest.hexdigest()
    if expected_source_sha256 is not None and source_digest != expected_source_sha256:
        raise ValueError("file bytes differ from the independently pinned SHA-256")
    if stop_op > count:
        raise ValueError(f"stop {stop_op} exceeds {count} source operations")
    if len(selected) != stop_op - start_op:
        raise ValueError("incomplete operation window")
    global_wires = tuple(sorted({q for op in selected for q in op.qubits}))
    if not global_wires:
        raise UnsupportedOperation("window has no quantum wire to map")
    if len(global_wires) > max_window_wires:
        raise ResourceLimitExceeded("window wires", max_window_wires, len(global_wires))
    mapping = {q: i for i, q in enumerate(global_wires)}
    inputs = tuple(f"b{bit}" for bit in external)
    fragment = HybridFragment(len(global_wires),
                              tuple(_hop(op, mapping) for op in selected), inputs)
    document = fragment_to_dict(fragment)
    return {
        "schema_version": 1, "kind": _KIND, "status": "extracted",
        "source_format": "strict_text_kmx_v1",
        "source_file_sha256": source_digest,
        "source_bytes": total, "source_ops": count,
        "op_span": [start_op, stop_op],
        "line_span": [selected[0].line, selected[-1].line + 1],
        "op_lines": [op.line for op in selected],
        "global_wires": list(global_wires),
        "classical_predecessors": [
            {"slot": f"b{bit}", "last_hmr_op": before[0], "last_hmr_line": before[1]}
            for bit, before in external.items()
        ],
        "fragment": document, "fragment_sha256": canonical_sha256(document),
        "advisory_only": True, "proved": False, "candidate_authorized": False,
    }


def verify_kmx_window(
    path: str | Path, record: dict[str, Any], *, expected_source_sha256: str,
    **limits: int,
) -> HybridFragment:
    """Reparse the full source against an external SHA pin; no proof is inferred."""
    _pin(expected_source_sha256)
    if type(record) is not dict or set(record) != _KEYS:
        raise ValueError("closed symq_kmx_window record required")
    if (record["kind"] != _KIND or type(record["schema_version"]) is not int
            or record["schema_version"] != 1):
        raise ValueError("unsupported window schema")
    span = record["op_span"]
    if (type(span) is not list or len(span) != 2
            or any(type(x) is not int for x in span)):
        raise ValueError("invalid operation span")
    # Plain Python dict equality equates 0 with False and 1 with True.
    # Compare canonical JSON instead so typed source metadata is immutable.
    # Encode the (bounded) record first so a malformed one fails fast,
    # before the whole source is re-parsed.
    try:
        claimed = encode_json(record)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("window record is not canonical JSON") from error
    expected = extract_kmx_window(
        path, start_op=span[0], stop_op=span[1],
        expected_source_sha256=expected_source_sha256, **limits,
    )
    if claimed != encode_json(expected):
        raise ValueError("window record contradicts pinned source")
    return fragment_from_dict(expected["fragment"])
