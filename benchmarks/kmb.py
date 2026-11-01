"""Strict reader and writer for the KMB v2 multiplier files of the public bilinear corpus.

Only the subset that corpus uses is accepted: three qubit registers ``a``, ``b``, ``t`` laid out
as consecutive blocks of ``n`` qubits, no classical bits, angles or single-qubit streams, and the
operations CX (33), SWAP (34), CCX (49) and the no-op 6. Anything else raises ``ValueError``
with the reason. Decoded files become :class:`symq.Circuit` objects, so they are evaluated by the
library's own engines rather than by a private simulator.

The byte layout below was read from the corpus files themselves; it is not a specification of
the format in general.
"""
from __future__ import annotations

import struct

from symq import Circuit

__all__ = ["MAGIC", "decode", "encode"]

MAGIC = bytes.fromhex("d750c7d5c329d326e3cc9f6834f2b8bf")
_HEADER = 104
_CX, _SWAP, _CCX, _NOP = 33, 34, 49, 6


class _Reader:
    def __init__(self, raw: bytes) -> None:
        self.raw, self.pos = raw, _HEADER

    def packet(self, kind: int) -> bytes:
        if self.pos + 16 > len(self.raw):
            raise ValueError(f"truncated packet header (expected packet {kind})")
        found, size = struct.unpack_from("<QQ", self.raw, self.pos)
        if found != kind or self.pos + 16 + size > len(self.raw):
            raise ValueError(f"expected packet {kind}, found {found} of {size} bytes")
        data = self.raw[self.pos + 16:self.pos + 16 + size]
        self.pos += 16 + size
        return data


def _words(data: bytes, count: int, what: str) -> tuple[int, ...]:
    if len(data) != 4 * count:
        raise ValueError(f"{what}: expected {count} words, got {len(data)} bytes")
    return struct.unpack(f"<{count}I", data)


def decode(raw: bytes) -> Circuit:
    """The circuit of a KMB v2 file, wire ``i`` being qubit ``i`` (``a``, then ``b``, then ``t``)."""
    if len(raw) < _HEADER or raw[:16] != MAGIC:
        raise ValueError("not a KMB v2 file (bad magic)")
    version, qubits, bits, registers = struct.unpack_from("<4I", raw, 16)
    if version != 2 or bits != 0 or registers != 3 or qubits % 3:
        raise ValueError("unsupported KMB layout: need version 2, 3 registers, no classical bits")
    counts = struct.unpack_from("<9Q", raw, 32)
    reader = _Reader(raw)
    n = qubits // 3
    for index, expected in enumerate("abt"):
        data = reader.packet(0)
        if len(data) < 8:
            raise ValueError("invalid register packet")
        name_size, size = struct.unpack_from("<II", data)
        if len(data) != 8 + name_size + 4 * size:
            raise ValueError("invalid register packet length")
        name = data[8:8 + name_size].decode("utf-8")
        ids = struct.unpack_from(f"<{size}I", data, 8 + name_size)
        if name != expected or ids != tuple(0x80000000 | (index * n + i) for i in range(n)):
            raise ValueError(f"register {name!r} is not the expected qubit block {expected!r}")
    opcodes = reader.packet(1)
    if len(opcodes) != counts[0]:
        raise ValueError("operation count mismatch")
    three = [_words(reader.packet(kind), counts[1], f"stream {kind}") for kind in (2, 3, 4)]
    two = [_words(reader.packet(kind), counts[2], f"stream {kind}") for kind in (5, 6)]
    for kind, count, what in ((7, counts[3], "single-qubit"), (8, counts[4], "bit"),
                              (9, counts[5], "bit-condition"), (10, 2 * counts[6], "angle")):
        if count or reader.packet(kind):
            raise ValueError(f"{what} operations are not supported")
    if len(reader.packet(11)) < 8:
        raise ValueError("invalid tag packet")
    if reader.pos != len(raw):
        raise ValueError("trailing bytes after the tag packet")
    circuit, i3, i2 = Circuit(qubits), 0, 0
    for opcode in opcodes:
        if opcode == _NOP:
            continue
        if opcode == _CCX:
            if i3 >= counts[1]:
                raise ValueError("more CCX operations than CCX operands")
            circuit.ccx(three[0][i3], three[1][i3], three[2][i3])
            i3 += 1
        elif opcode in (_CX, _SWAP):
            if i2 >= counts[2]:
                raise ValueError("more two-qubit operations than operands")
            a, b = two[0][i2], two[1][i2]
            i2 += 1
            if opcode == _CX:
                circuit.cx(a, b)
            else:
                circuit.cx(a, b).cx(b, a).cx(a, b)
        else:
            raise ValueError(f"unsupported operation code {opcode}")
    if i3 != counts[1] or i2 != counts[2]:
        raise ValueError("unused operands")
    return circuit.validate()


def encode(circuit: Circuit) -> bytes:
    """A KMB v2 file for a CX/CCX circuit on ``3n`` wires (registers ``a``, ``b``, ``t``)."""
    circuit.validate()
    if circuit.width % 3 or any(gate.name not in {"cx", "ccx"} for gate in circuit.gates):
        raise ValueError("encode needs a CX/CCX circuit on 3n wires")
    n = circuit.width // 3
    three = [gate.qubits for gate in circuit.gates if gate.name == "ccx"]
    two = [gate.qubits for gate in circuit.gates if gate.name == "cx"]
    out = bytearray(MAGIC)
    out += struct.pack("<4I", 2, circuit.width, 0, 3)
    out += struct.pack("<9Q", len(circuit.gates), len(three), len(two), 0, 0, 0, 0, 0, 0)

    def packet(kind: int, data: bytes) -> None:
        out.extend(struct.pack("<2Q", kind, len(data)) + data)

    for index, name in enumerate(b"abt"):
        ids = [0x80000000 | (index * n + i) for i in range(n)]
        packet(0, struct.pack("<2I", 1, n) + bytes([name]) + struct.pack(f"<{n}I", *ids))
    packet(1, bytes(_CCX if gate.name == "ccx" else _CX for gate in circuit.gates))
    for field in range(3):
        packet(2 + field, struct.pack(f"<{len(three)}I", *(q[field] for q in three)))
    for field in range(2):
        packet(5 + field, struct.pack(f"<{len(two)}I", *(q[field] for q in two)))
    for kind in (7, 8, 9, 10):
        packet(kind, b"")
    packet(11, struct.pack("<Q", 0))
    return bytes(out)
