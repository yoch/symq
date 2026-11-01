"""Strict importer for the text circuit format (``.kmx``) of Qualtran's kickmix simulator.

Only a narrow, exactly representable subset is accepted; everything else is refused with the
offending line instead of being approximated:

* reversible gates ``X``, ``CX``, ``CCX``, ``SWAP`` and ``CSWAP`` (SWAPs are lowered to CX/CCX);
* sign phases ``Z``, ``CZ``, ``CCZ``;
* ``HMR q bN`` (X-basis measurement and reset of ``q`` into classical bit ``bN``);
* sign phases conditioned on one measured bit: ``Z ... if bN``, ``CZ ... if bN``, ``CCZ ... if bN``;
* the metadata lines ``REGISTER name "label"``, ``APPEND_TO_REGISTER element register``,
  ``INFO_TAG ...`` and ``DEBUG_PRINT ...`` (no semantics), matched by exact name; the first two are
  checked for shape and none may carry an ``if bN`` condition.

The grammar is closed: a name is accepted only if it is listed above. Refused: ``R`` (reset),
``Z_POW`` (arbitrary angles), ``NEG`` (global phase), ``BIT_*``, ``PUSH_CONDITION``/
``POP_CONDITION``, conditional reversible gates (``X ... if b``), conditional ``HMR``, every name
with an ``_IF`` suffix (a condition is written only as a trailing ``if bN``) and every unknown
name, even one that starts like a metadata name. The binary ``.kmb`` format is not read.

:meth:`KmxProgram.to_circuit` gives a classical :class:`~symq.circuit.Circuit` and refuses any phase
or measurement. :meth:`KmxProgram.to_phase_program` gives a :class:`~symq.phase.PhaseProgram`, the
input of the strict sign/HMR checker and of the experimental channel API; the caller names the data
qubits, every other qubit is an ancilla prepared in ``|0>``.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .circuit import Circuit
from .errors import QasmSyntaxError, UnsupportedOperation
from .phase import PhaseProgram

__all__ = ["KmxOp", "KmxProgram", "KmxSyntaxError", "load_kmx", "parse_kmx"]


class KmxSyntaxError(QasmSyntaxError):
    """Malformed line inside the accepted kickmix subset."""


_QUBIT = re.compile(r"q(\d+)$")
_BIT = re.compile(r"b(\d+)$")
_REVERSIBLE = {"X": 1, "CX": 2, "CCX": 3, "SWAP": 2, "CSWAP": 3}
_PHASE = {"Z": 1, "CZ": 2, "CCZ": 3}
_METADATA = frozenset({"REGISTER", "APPEND_TO_REGISTER", "INFO_TAG", "DEBUG_PRINT"})
_REGISTER = re.compile(r'REGISTER\s+\S+\s+"[^"]*"$')
_REFUSED = {
    "R": "reset is not a reversible or sign-phase operation",
    "Z_POW": "arbitrary-angle phases are outside the sign-phase grammar",
    "NEG": "global phase flips are not tracked by the sign-phase grammar",
    "BIT_INVERT": "classical bit arithmetic is not supported",
    "BIT_STORE0": "classical bit arithmetic is not supported",
    "BIT_STORE1": "classical bit arithmetic is not supported",
    "PUSH_CONDITION": "condition stacks are not supported",
    "POP_CONDITION": "condition stacks are not supported",
}
TOFFOLI_LIKE = frozenset({"CCX", "CCZ", "CSWAP"})
"""Operations counted as Toffoli-like, conditioned or not."""


@dataclass(frozen=True)
class KmxOp:
    """One accepted operation: name, qubit indices, measured bit (HMR) and condition bit."""

    name: str
    qubits: tuple[int, ...]
    bit: int | None = None
    condition: int | None = None
    line: int = 0


@dataclass
class KmxProgram:
    """The accepted operations of a ``.kmx`` file, in order."""

    ops: list[KmxOp] = field(default_factory=list)
    registers: dict[str, list[str]] = field(default_factory=dict)

    @property
    def qubits(self) -> tuple[int, ...]:
        """Every qubit index the program touches, sorted."""
        return tuple(sorted({q for op in self.ops for q in op.qubits}))

    def counts(self) -> dict[str, int]:
        """Operation counts, with ``toffoli_like`` (CCX, CCZ, CSWAP, conditioned or not)."""
        counts = Counter(op.name + ("_IF" if op.condition is not None else "") for op in self.ops)
        result = dict(sorted(counts.items()))
        result["toffoli_like"] = sum(op.name in TOFFOLI_LIKE for op in self.ops)
        return result

    def to_circuit(self, qubits: Sequence[int] | None = None) -> Circuit:
        """A classical reversible circuit; wire ``i`` is ``qubits[i]`` (default: all, sorted).

        Refuses phases and measurements: dropping them would change the operation.
        """
        mapping = self._mapping(qubits)
        circuit = Circuit(max(len(mapping), 1))
        for op in self.ops:
            if op.name not in _REVERSIBLE or op.condition is not None:
                raise UnsupportedOperation(
                    f"line {op.line}: {op.name} is not a classical reversible operation; "
                    "use to_phase_program()")
            _append_reversible(circuit, op, mapping)
        return circuit

    def to_phase_program(self, data: Sequence[int]) -> PhaseProgram:
        """A sign/HMR program with ``data`` (kickmix qubit indices) as data wires, in order.

        Every other touched qubit becomes an ancilla, in increasing index order, prepared in
        ``|0>``. Each ``HMR`` produces a fresh outcome; a condition ``if bN`` refers to the latest
        measurement written into ``bN``.
        """
        data = list(data)
        if len(set(data)) != len(data):
            raise ValueError("data qubits must be distinct")
        ancillas = [q for q in self.qubits if q not in set(data)]
        mapping = {q: i for i, q in enumerate([*data, *ancillas])}
        program = PhaseProgram(len(data), len(ancillas))
        latest: dict[int, int] = {}
        for op in self.ops:
            wires = [mapping[q] for q in op.qubits]
            if op.name in _REVERSIBLE:
                if op.condition is not None:
                    raise UnsupportedOperation(
                        f"line {op.line}: classically conditioned {op.name} is not supported")
                for name, gate in _lowered(op.name, wires):
                    program.append(name, *gate)
            elif op.name in _PHASE:
                if op.condition is None:
                    program.mcz(*wires)
                else:
                    if op.condition not in latest:
                        raise UnsupportedOperation(
                            f"line {op.line}: condition b{op.condition} is read before any HMR "
                            "writes it")
                    program.mcz_if(latest[op.condition], *wires)
            elif op.name == "HMR":
                latest[op.bit] = program.hmr(wires[0])  # type: ignore[index]
            else:  # pragma: no cover - the parser admits nothing else
                raise UnsupportedOperation(op.name)
        return program

    def _mapping(self, qubits: Sequence[int] | None) -> dict[int, int]:
        order = list(self.qubits) if qubits is None else list(qubits)
        if len(set(order)) != len(order):
            raise ValueError("qubits must be distinct")
        missing = set(self.qubits) - set(order)
        if missing:
            raise ValueError(f"qubits {sorted(missing)} are used but not mapped")
        return {q: i for i, q in enumerate(order)}


def _lowered(name: str, wires: list[int]) -> list[tuple[str, tuple[int, ...]]]:
    if name == "SWAP":
        a, b = wires
        return [("cx", (a, b)), ("cx", (b, a)), ("cx", (a, b))]
    if name == "CSWAP":
        c, a, b = wires
        return [("cx", (b, a)), ("ccx", (c, a, b)), ("cx", (b, a))]
    return [(name.lower(), tuple(wires))]


def _append_reversible(circuit: Circuit, op: KmxOp, mapping: dict[int, int]) -> None:
    for name, gate in _lowered(op.name, [mapping[q] for q in op.qubits]):
        circuit.append(name, *gate)


def _index(token: str, pattern: re.Pattern[str], what: str, line: int) -> int:
    match = pattern.match(token)
    if match is None:
        raise KmxSyntaxError(f"line {line}: expected a {what}, got {token!r}")
    return int(match.group(1))


def parse_kmx(text: str) -> KmxProgram:
    """Parse ``.kmx`` text into the accepted subset (see the module docstring)."""
    program = KmxProgram()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        name = tokens[0]
        if name in _METADATA:
            if len(tokens) >= 3 and tokens[-2] == "if":
                raise UnsupportedOperation(f"line {number}: {name} cannot be conditioned")
            if name == "APPEND_TO_REGISTER":
                if len(tokens) != 3:
                    raise KmxSyntaxError(
                        f"line {number}: APPEND_TO_REGISTER takes an element and a register")
                program.registers.setdefault(tokens[2], []).append(tokens[1])
            elif name == "REGISTER" and _REGISTER.match(line) is None:
                raise KmxSyntaxError(f'line {number}: REGISTER takes a name and a "label"')
            continue
        if name.endswith("_IF"):
            raise UnsupportedOperation(
                f"line {number}: {name}: conditions are written as a trailing 'if bN'; the _IF "
                "form is not part of the accepted grammar")
        condition = None
        if len(tokens) >= 3 and tokens[-2] == "if":
            condition = _index(tokens[-1], _BIT, "condition bit", number)
            tokens = tokens[:-2]
        if name in _REFUSED:
            raise UnsupportedOperation(f"line {number}: {name}: {_REFUSED[name]}")
        arguments = tokens[1:]
        if name == "HMR":
            if condition is not None:
                raise UnsupportedOperation(f"line {number}: conditional HMR is not supported")
            if len(arguments) != 2:
                raise KmxSyntaxError(f"line {number}: HMR takes a qubit and a bit")
            qubit = _index(arguments[0], _QUBIT, "qubit", number)
            bit = _index(arguments[1], _BIT, "bit", number)
            program.ops.append(KmxOp("HMR", (qubit,), bit=bit, line=number))
            continue
        arity = _REVERSIBLE.get(name) or _PHASE.get(name)
        if arity is None:
            raise UnsupportedOperation(f"line {number}: unknown or unsupported operation {name!r}")
        if len(arguments) != arity:
            raise KmxSyntaxError(f"line {number}: {name} takes {arity} qubits, got {len(arguments)}")
        qubits = tuple(_index(token, _QUBIT, "qubit", number) for token in arguments)
        if len(set(qubits)) != len(qubits):
            raise KmxSyntaxError(f"line {number}: repeated qubit in {name}")
        program.ops.append(KmxOp(name, qubits, condition=condition, line=number))
    return program


def load_kmx(path: str | Path) -> KmxProgram:
    """Read and parse a ``.kmx`` file (the binary ``.kmb`` format is not supported)."""
    path = Path(path)
    if path.suffix == ".kmb":
        raise UnsupportedOperation("the binary .kmb format is not supported; export .kmx text")
    return parse_kmx(path.read_text(encoding="utf-8"))
