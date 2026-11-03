"""Strict bounded Kickmix binary v2 (.kmb) source-window reader.

Format source: quantumlib/Qualtran docs/kickmix/kickmix_binary_format.md,
pinned at 9a0c11a4ee7697c082fbf8f2e1e8bf4a71fcb453,
blob debcf51c10d4840fc268f5452686976e96699c40 (Apache-2.0).

This is a source *extractor*, not a channel theorem, a binary-to-text
equivalence proof, or authorization to rewrite a global circuit. It uses
read-only mmap of the struct-of-arrays file and walks operation types in
order with bounded per-window memory. Unknown opcodes, broken packets,
unsafe classical references and active condition stacks fail closed.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from contextlib import contextmanager
import math
import mmap
import os
import re
import stat as _stat
import struct
import time
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.hybrid import HOp
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import HybridFragment
from symq.labs.rewrite_request import fragment_from_dict, fragment_to_dict

__all__ = ["extract_kmb_window", "verify_kmb_window"]

_MAGIC = bytes.fromhex("d750c7d5c329d326e3cc9f6834f2b8bf")
_HEADER = struct.Struct("<16sIIII9Q")
_PACK = struct.Struct("<QQ")
_PIN = re.compile(r"[0-9a-f]{64}\Z")
_KIND = "symq_kmb_window"
_FORMAT = "kickmix_binary_v2"
_KEYS = frozenset({
    "schema_version", "kind", "status", "source_format",
    "source_file_sha256", "source_bytes", "source_ops", "op_span",
    "type_byte_offsets", "global_wires", "classical_predecessors",
    "fragment", "fragment_sha256", "num_qubits", "num_bits",
    "unsupported_outside_window", "advisory_only",
    "proved", "candidate_authorized",
})

# The exact v2 byte enumeration, not an inference from a file's extension.
_OPS = {
    0x00: "NEG", 0x80: "NEG_IF",
    0x01: "POP_CONDITION", 0x81: "PUSH_CONDITION",
    0x10: "Z", 0x90: "Z_IF",
    0x11: "X", 0x91: "X_IF",
    0x12: "R", 0x92: "R_IF",
    0x13: "Z_POW", 0x93: "Z_POW_IF",
    0x50: "HMR", 0xD0: "HMR_IF",
    0x20: "CZ", 0xA0: "CZ_IF",
    0x21: "CX", 0xA1: "CX_IF",
    0x22: "SWAP", 0xA2: "SWAP_IF",
    0x30: "CCZ", 0xB0: "CCZ_IF",
    0x31: "CCX", 0xB1: "CCX_IF",
    0x32: "CSWAP", 0xB2: "CSWAP_IF",
    0x40: "BIT_STORE0", 0xC0: "BIT_STORE0_IF",
    0x41: "BIT_STORE1", 0xC1: "BIT_STORE1_IF",
    0x42: "BIT_INVERT", 0xC2: "BIT_INVERT_IF",
    0x06: "INFO_TAG",
    0x07: "DEBUG_PRINT_EMPTY", 0x87: "DEBUG_PRINT_EMPTY_IF",
    0x47: "DEBUG_PRINT_C", 0xC7: "DEBUG_PRINT_C_IF",
    0x17: "DEBUG_PRINT_Q", 0x97: "DEBUG_PRINT_Q_IF",
}
_QOP = {"X": "x", "CX": "cx", "CCX": "ccx", "SWAP": "swap",
        "CSWAP": "cswap", "Z": "z", "CZ": "cz", "CCZ": "ccz",
        "NEG": "neg", "R": "reset", "HMR": "hmr"}
_BIT_WRITE = {"HMR", "HMR_IF", "BIT_STORE0", "BIT_STORE1", "BIT_INVERT",
              "BIT_STORE0_IF", "BIT_STORE1_IF", "BIT_INVERT_IF"}
_DEBUG = {"INFO_TAG", "DEBUG_PRINT_EMPTY", "DEBUG_PRINT_C", "DEBUG_PRINT_Q",
          "DEBUG_PRINT_EMPTY_IF", "DEBUG_PRINT_C_IF", "DEBUG_PRINT_Q_IF"}
_SUPPORTED_WINDOW = frozenset(_QOP) | {
    "X_IF", "CX_IF", "CCX_IF", "SWAP_IF", "CSWAP_IF",
    "Z_IF", "CZ_IF", "CCZ_IF", "NEG_IF",
    "BIT_STORE0", "BIT_STORE1", "BIT_INVERT", "BIT_INVERT_IF",
}


def _int(value: Any, lower: int, upper: int, name: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be a plain integer in {lower}..{upper}")
    return value


def _pin(value: str) -> None:
    if type(value) is not str or _PIN.fullmatch(value) is None:
        raise ValueError("independent lowercase source SHA-256 required")


def _sha(view: mmap.mmap, clock: float) -> str:
    digest = hashlib.sha256()
    for start in range(0, len(view), 1 << 20):
        if time.perf_counter() >= clock:
            raise ResourceLimitExceeded("KMB wall seconds", 0, 1)
        digest.update(view[start:start + (1 << 20)])
    return digest.hexdigest()


@contextmanager
def _private_snapshot(
    source: BinaryIO, size: int, *, deadline: float, max_seconds: float
) -> Iterator[tuple[mmap.mmap, str]]:
    """Decode a private, file-backed immutable byte image, never a mutable source mmap.

    Bytes are copied and hashed in the same bounded pass, then all parsing
    uses only the unshared private file. Concurrent writes/truncations of
    the original descriptor therefore cannot alter a mapped page or SIGBUS
    the parser. An independently pinned SHA identifies the *copied bytes*;
    copying does not promise one atomic instant in the original file.
    """
    digest = hashlib.sha256()
    remaining = size
    with tempfile.TemporaryFile(mode="w+b") as private:
        while remaining:
            if time.perf_counter() >= deadline:
                raise ResourceLimitExceeded("KMB wall seconds", max_seconds,
                                            max_seconds + 1)
            chunk = source.read(min(1 << 20, remaining))
            if not chunk:
                raise ValueError("KMB source was truncated during the private copy")
            private.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        if (os.fstat(source.fileno()).st_size != size or source.read(1)):
            raise ValueError("KMB source size changed during the private copy")
        if time.perf_counter() >= deadline:
            raise ResourceLimitExceeded("KMB wall seconds", max_seconds,
                                        max_seconds + 1)
        private.flush()
        with mmap.mmap(private.fileno(), 0, access=mmap.ACCESS_READ) as snapshot:
            yield snapshot, digest.hexdigest()


def _packet(view: mmap.mmap, at: int, expected: int) -> tuple[int, int, int]:
    if len(view) - at < _PACK.size:
        raise ValueError("truncated KMB packet header")
    kind, length = _PACK.unpack_from(view, at)
    start = at + _PACK.size
    if kind != expected:
        raise ValueError(f"KMB packets are out of order: wanted {expected}, got {kind}")
    if length > len(view) - start:
        raise ValueError("KMB packet payload exceeds file")
    return start, length, start + length


def _layout(view: mmap.mmap, *, max_registers: int, max_register_entries: int,
            max_ops: int, max_seconds_deadline: float) -> tuple[dict, dict]:
    if len(view) < _HEADER.size:
        raise ValueError("truncated KMB header")
    values = _HEADER.unpack_from(view, 0)
    magic, version, nq, nb, nreg, *counts = values
    (nops, n3, n2, n1, nbit, ncond, nangle, ntags, nchars) = counts
    if magic != _MAGIC or version != 2:
        raise ValueError("expected Kickmix binary format v2 and its exact magic")
    if nq > 500_000_000 or nb > 500_000_000:
        raise ValueError("out-of-range KMB declared qubit/bit count")
    if nops > max_ops:
        raise ResourceLimitExceeded("KMB operations", max_ops, nops)
    if nreg > max_registers:
        raise ResourceLimitExceeded("KMB registers", max_registers, nreg)
    info = {"num_qubits": nq, "num_bits": nb, "num_registers": nreg,
            "num_ops": nops, "counts": (n3, n2, n1, nbit, ncond, nangle, ntags)}
    at = _HEADER.size
    max_q = max_b = -1
    total_entries = 0
    for _ in range(nreg):
        if time.perf_counter() >= max_seconds_deadline:
            raise ResourceLimitExceeded("KMB wall seconds", 0, 1)
        start, length, at = _packet(view, at, 0)
        if length < 8:
            raise ValueError("truncated register metadata")
        name_len, nentries = struct.unpack_from("<II", view, start)
        if length != 8 + name_len + 4 * nentries:
            raise ValueError("noncanonical KMB register packet length")
        if name_len > 1_000_000:
            raise ResourceLimitExceeded("KMB register name bytes", 1_000_000, name_len)
        total_entries += nentries
        if total_entries > max_register_entries:
            raise ResourceLimitExceeded("register entries", max_register_entries,
                                        total_entries)
        # The v2 spec types names as raw chars; no text encoding is mandated.
        cursor = start + 8 + name_len
        for index in range(nentries):
            if index % 1024 == 0 and time.perf_counter() >= max_seconds_deadline:
                raise ResourceLimitExceeded("KMB wall seconds", 0, 1)
            raw = struct.unpack_from("<I", view, cursor + 4 * index)[0]
            if raw >> 31:
                max_q = max(max_q, raw & 0x7fffffff)
            else:
                max_b = max(max_b, raw)
    payloads = {}
    lengths = {1: nops, 2: 4 * n3, 3: 4 * n3, 4: 4 * n3,
               5: 4 * n2, 6: 4 * n2, 7: 4 * n1,
               8: 4 * nbit, 9: 4 * ncond, 10: 16 * nangle,
               11: 8 + 8 * ntags + nchars}
    for kind in range(1, 12):
        start, length, at = _packet(view, at, kind)
        if length != lengths[kind]:
            raise ValueError(f"KMB packet {kind} length disagrees with header")
        payloads[kind] = start
    if at != len(view):
        raise ValueError("trailing bytes after the final KMB packet")
    meta = payloads[11]
    declared_tags = struct.unpack_from("<Q", view, meta)[0]
    if declared_tags != ntags:
        raise ValueError("KMB tag count mismatch")
    prev = 0
    for index in range(ntags):
        if index % 1024 == 0 and time.perf_counter() >= max_seconds_deadline:
            raise ResourceLimitExceeded("KMB wall seconds", 0, 1)
        end = struct.unpack_from("<Q", view, meta + 8 + 8 * index)[0]
        if not prev <= end <= nchars:
            raise ValueError("non-monotone KMB INFO_TAG offsets")
        prev = end
    if prev != nchars:
        raise ValueError("KMB INFO_TAG length mismatch")
    info["max_q_reg"] = max_q
    info["max_b_reg"] = max_b
    return info, payloads


def _hop(kind: str, wires: tuple[int, ...], target_bit: int | None,
         condition: int | None, wire_map: dict[int, int]) -> HOp:
    if kind.endswith("_IF"):
        plain = kind[:-3]
        if plain in {"HMR", "R"} or plain in _DEBUG:
            raise UnsupportedOperation(f"conditional {plain} unsupported in hybrid window")
    else:
        plain = kind
    mapped = tuple(wire_map[q] for q in wires)
    cond = None if condition is None else f"b{condition}"
    if plain in _QOP:
        if plain == "HMR":
            if target_bit is None:
                raise ValueError("HMR missing classical destination")
            return HOp("hmr", mapped, slot=f"b{target_bit}")
        return HOp(_QOP[plain], mapped, condition=cond)
    if plain in {"BIT_STORE0", "BIT_STORE1", "BIT_INVERT"}:
        if target_bit is None:
            raise ValueError("missing classical destination")
        if plain == "BIT_INVERT":
            return HOp("invert", slot=f"b{target_bit}", condition=cond)
        if cond is not None:
            raise UnsupportedOperation("conditional BIT_STORE is unsupported")
        return HOp("store", slot=f"b{target_bit}", value=int(plain[-1]))
    raise UnsupportedOperation(f"{kind} is outside the admitted hybrid window grammar")


def extract_kmb_window(
    path: str | Path, *, start_op: int, stop_op: int,
    expected_source_sha256: str | None = None,
    max_source_bytes: int = 8_000_000_000,
    max_snapshot_bytes: int = 512 * 1024 * 1024,
    max_source_ops: int = 500_000_000,
    max_window_ops: int = 20_000,
    max_window_wires: int = 256,
    max_classical_slots: int = 100_000,
    max_registers: int = 100_000,
    max_register_entries: int = 5_000_000,
    max_seconds: float = 180.0,
) -> dict[str, Any]:
    """Validate a complete canonical-layout v2 KMB and extract an exact op span.

    Input coordinates are raw KMB operation indices (metadata still counts).
    A resulting HybridFragment is only a structural object; the global
    context and all incoming classical/quantum preconditions need proof.
    """
    source = Path(path)
    if source.suffix.lower() != ".kmb":
        raise UnsupportedOperation("strict binary .kmb v2 input required")
    for value, label, upper in (
        (max_source_bytes, "max_source_bytes", 100_000_000_000),
        (max_snapshot_bytes, "max_snapshot_bytes", 100_000_000_000),
        (max_source_ops, "max_source_ops", 1_000_000_000),
        (max_window_ops, "max_window_ops", 10_000_000),
        (max_window_wires, "max_window_wires", 1_000_000),
        (max_classical_slots, "max_classical_slots", 10_000_000),
        (max_registers, "max_registers", 1_000_000),
        (max_register_entries, "max_register_entries", 100_000_000),
    ):
        _int(value, 1, upper, label)
    _int(start_op, 0, 1_000_000_000, "start_op")
    _int(stop_op, start_op + 1, 1_000_000_000, "stop_op")
    if stop_op > max_source_ops:
        raise ResourceLimitExceeded("KMB source operations", max_source_ops, stop_op)
    if stop_op - start_op > max_window_ops:
        raise ResourceLimitExceeded("KMB window operations", max_window_ops,
                                    stop_op - start_op)
    if (type(max_seconds) not in (float, int) or not math.isfinite(max_seconds)
            or max_seconds <= 0):
        raise ValueError("positive finite max_seconds required")
    if expected_source_sha256 is not None:
        _pin(expected_source_sha256)
    deadline = time.perf_counter() + max_seconds
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb", buffering=0) as handle:
        stat = os.fstat(handle.fileno())
        if not _stat.S_ISREG(stat.st_mode):
            raise UnsupportedOperation("KMB source must be a regular file")
        if stat.st_size < _HEADER.size:
            raise ValueError("truncated KMB source file")
        if stat.st_size > max_source_bytes:
            raise ResourceLimitExceeded("KMB file bytes", max_source_bytes,
                                        stat.st_size)
        if stat.st_size > max_snapshot_bytes:
            raise ResourceLimitExceeded("KMB private snapshot bytes", max_snapshot_bytes,
                                        stat.st_size)
        with _private_snapshot(handle, stat.st_size, deadline=deadline,
                               max_seconds=max_seconds) as (view, copied_digest):
            # The snapshot is now private. Recheck its digest before parsing,
            # so source_file_sha256 binds precisely the bytes being decoded.
            first_digest = _sha(view, deadline)
            if first_digest != copied_digest:
                raise ValueError("KMB private snapshot bytes changed unexpectedly")
            if expected_source_sha256 is not None and first_digest != expected_source_sha256:
                raise ValueError("KMB file differs from independently pinned SHA-256")
            info, packets = _layout(
                view, max_registers=max_registers,
                max_register_entries=max_register_entries,
                max_ops=max_source_ops, max_seconds_deadline=deadline,
            )
            if stop_op > info["num_ops"]:
                raise ValueError("requested KMB operation range extends past EOF")

            counters = [0] * 7  # 3q,2q,1q,1bit,condition,angle,info_tag
            selected: list[tuple[int, str, tuple[int, ...], int | None, int | None]] = []
            offsets: list[int] = []
            outside_unsupported = 0
            last_write: dict[int, tuple[int, str, bool]] = {}
            written_inside: set[int] = set()
            external: dict[int, tuple[int, str, bool]] = {}
            stack_depth = 0
            refusal: UnsupportedOperation | None = None
            max_q, max_b = info["max_q_reg"], info["max_b_reg"]

            def fetch_u32(packet_kind: int, index: int, limit: int) -> int:
                if index >= limit:
                    raise ValueError("KMB operation consumes more operands than declared")
                return struct.unpack_from("<I", view, packets[packet_kind] + index * 4)[0]

            for index in range(info["num_ops"]):
                if index % 1024 == 0 and time.perf_counter() >= deadline:
                    raise ResourceLimitExceeded("KMB wall seconds", max_seconds,
                                                max_seconds + 1)
                opcode = view[packets[1] + index]
                kind = _OPS.get(opcode)
                if kind is None:
                    raise ValueError(f"unrecognized KMB opcode {opcode:#x} at op {index}")
                group = opcode & 0x30
                wires: tuple[int, ...] = ()
                if group:
                    n = 3 if group == 0x30 else 2 if group == 0x20 else 1
                    group_index = (3 - n)
                    pos = counters[group_index]
                    packet_id = {3: (2, 3, 4), 2: (5, 6), 1: (7,)}[n]
                    wires = tuple(fetch_u32(channel, pos, info["counts"][group_index])
                                  for channel in packet_id)
                    counters[group_index] += 1
                    if len(set(wires)) != n:
                        raise ValueError(f"repeated KMB qubit targets at op {index}")
                    if any(q >= info["num_qubits"] for q in wires):
                        raise ValueError("KMB qubit id exceeds header")
                    max_q = max(max_q, *wires)
                target_bit = None
                if opcode & 0x40:
                    target_bit = fetch_u32(8, counters[3], info["counts"][3])
                    counters[3] += 1
                    if target_bit >= info["num_bits"]:
                        raise ValueError("KMB bit id exceeds header")
                    max_b = max(max_b, target_bit)
                condition = None
                if opcode & 0x80:
                    condition = fetch_u32(9, counters[4], info["counts"][4])
                    counters[4] += 1
                    if condition >= info["num_bits"]:
                        raise ValueError("KMB condition id exceeds header")
                    max_b = max(max_b, condition)
                if kind in {"Z_POW", "Z_POW_IF"}:
                    counters[5] += 1
                if kind == "INFO_TAG":
                    counters[6] += 1

                chosen = start_op <= index < stop_op
                # A KMB source may have caller-initialized classical bits.
                # Unknown incoming values are exposed as arbitrary cut inputs,
                # NEVER silently assumed zero; a conditional possible writer
                # remains ambiguous and is refused at the selected cut.
                # A source input influenced by a condition stack cannot be
                # imported as a plain HOp even if its own opcode looks simple.
                if chosen and stack_depth and refusal is None:
                    refusal = UnsupportedOperation(
                        "selected window is under a PUSH_CONDITION stack"
                    )
                if kind == "POP_CONDITION":
                    # Spec: POP_CONDITION on an empty stack has no effect. It is
                    # well-formed, so refuse (unsupported) rather than call it invalid.
                    if not stack_depth:
                        if refusal is None:
                            refusal = UnsupportedOperation(
                                f"KMB op {index}: POP_CONDITION on an empty stack")
                    else:
                        stack_depth -= 1
                elif kind == "PUSH_CONDITION":
                    stack_depth += 1

                if chosen and refusal is None:
                    if kind not in _SUPPORTED_WINDOW:
                        refusal = UnsupportedOperation(f"KMB op {index}: {kind} unsupported")
                    if refusal is None and condition is not None and condition not in written_inside:
                        previous = last_write.get(
                            condition, (-1, "SOURCE_INITIAL_UNKNOWN", True)
                        )
                        if not previous[2]:
                            refusal = UnsupportedOperation(
                                "classical input has a conditional possible prefix writer"
                            )
                        else:
                            external.setdefault(condition, previous)
                    if refusal is None and kind in {"BIT_INVERT", "BIT_INVERT_IF"}:
                        assert target_bit is not None
                        if target_bit not in written_inside:
                            previous = last_write.get(
                                target_bit, (-1, "SOURCE_INITIAL_UNKNOWN", True)
                            )
                            if not previous[2]:
                                refusal = UnsupportedOperation(
                                    "BIT_INVERT input has a possible prefix writer"
                                )
                            else:
                                external.setdefault(target_bit, previous)
                    selected.append((index, kind, wires, target_bit, condition))
                    offsets.append(packets[1] + index)
                    if target_bit is not None and kind in _BIT_WRITE:
                        written_inside.add(target_bit)
                elif kind not in _SUPPORTED_WINDOW and kind not in _DEBUG:
                    outside_unsupported += 1

                if target_bit is not None and kind in _BIT_WRITE:
                    if target_bit not in last_write and len(last_write) >= max_classical_slots:
                        raise ResourceLimitExceeded("KMB classical slots", max_classical_slots,
                                                    len(last_write) + 1)
                    certain = (condition is None and stack_depth == 0)
                    # A conditional write may or may not overwrite the old value.
                    last_write[target_bit] = (index, kind, certain)

            if stack_depth and refusal is None:
                # Not forbidden by the v2 spec: a refusal, not a malformed file.
                refusal = UnsupportedOperation("unbalanced KMB condition stack")
            if tuple(counters) != info["counts"]:
                raise ValueError("KMB opcode counts contradict the header")
            if max_q + 1 != info["num_qubits"] or max_b + 1 != info["num_bits"]:
                raise ValueError("KMB maximum qubit/bit ids contradict the header")
            last_digest = _sha(view, deadline)
            if last_digest != first_digest:
                raise ValueError("KMB private snapshot bytes changed during validation")
            if refusal is not None:
                raise refusal
            if not selected:
                raise UnsupportedOperation("empty semantic KMB window")
            wire_ids = tuple(sorted({q for _, _, wires, _, _ in selected for q in wires}))
            if not wire_ids:
                raise UnsupportedOperation("KMB window contains no quantum wire")
            if len(wire_ids) > max_window_wires:
                raise ResourceLimitExceeded("KMB window wires", max_window_wires,
                                            len(wire_ids))
            wire_map = {wire: i for i, wire in enumerate(wire_ids)}
            fragment = HybridFragment(
                len(wire_ids),
                tuple(_hop(kind, wires, bit, cond, wire_map)
                      for _, kind, wires, bit, cond in selected),
                tuple(f"b{slot}" for slot in external),
            )
            document = fragment_to_dict(fragment)
            return {
                "schema_version": 1, "kind": _KIND, "status": "extracted",
                "source_format": _FORMAT, "source_file_sha256": first_digest,
                "source_bytes": stat.st_size, "source_ops": info["num_ops"],
                "op_span": [start_op, stop_op], "type_byte_offsets": offsets,
                "global_wires": list(wire_ids),
                "classical_predecessors": [
                    {"slot": f"b{slot}",
                     "last_write_op": None if v[0] < 0 else v[0],
                     "last_write_kind": v[1]} for slot, v in external.items()
                ],
                "fragment": document, "fragment_sha256": canonical_sha256(document),
                "num_qubits": info["num_qubits"], "num_bits": info["num_bits"],
                "unsupported_outside_window": outside_unsupported,
                "advisory_only": True, "proved": False,
                "candidate_authorized": False,
            }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify_kmb_window(path: str | Path, record: dict[str, Any], *,
                      expected_source_sha256: str, **limits: Any) -> HybridFragment:
    """Reparse a private copy and compare the whole record to an external pin.

    Each verification call owns an immutable byte image and never mmaps the
    caller's mutable file. The read/copy of the original is not an atomic
    filesystem snapshot; the SHA-256 binds the exact copied bytes.
    """
    _pin(expected_source_sha256)
    if type(record) is not dict or set(record) != _KEYS:
        raise ValueError("closed symq_kmb_window record required")
    if (record["kind"] != _KIND or type(record["schema_version"]) is not int
            or record["schema_version"] != 1):
        raise ValueError("unsupported KMB window schema")
    span = record["op_span"]
    if (type(span) is not list or len(span) != 2
            or any(type(i) is not int for i in span)):
        raise ValueError("invalid KMB operation span")
    # Dict equality equates True with 1 and False with 0: this is a
    # closed, typed JSON receipt, not a permissive Python mapping. Compact
    # canonical JSON is used, encoded before the costly re-parse: the indented
    # encode_json allocates quadratic indentation on deep input under
    # Python 3.14 (OOM) instead of raising RecursionError.
    try:
        claimed = _canonical(record)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("KMB window record is not canonical JSON") from error
    fresh = extract_kmb_window(
        path, start_op=span[0], stop_op=span[1],
        expected_source_sha256=expected_source_sha256, **limits,
    )
    if claimed != _canonical(fresh):
        raise ValueError("KMB window record contradicts the externally pinned source")
    return fragment_from_dict(fresh["fragment"])
