"""Strict OpenQASM 2/3 reader for the X/CX/CCX/MCX subset.

Accepted statements: the version header, ``include``, exactly one quantum register
(``qreg q[n];`` or ``qubit[n] q;``) and applications of ``x``, ``cx``, ``ccx`` or ``mcx``,
optionally prefixed by positive-control modifiers ``ctrl @`` / ``ctrl(k) @``. Anything else
(other gates, ``negctrl``, ``inv``, measurements, classical bits, barriers, gate
definitions) raises :class:`~symq.UnsupportedOperation`. RevLib-style ``// i`` and ``// o``
annotations are accepted only when they are the identity permutation, because a
non-trivial input/output permutation would change the meaning of the circuit.
"""
from __future__ import annotations

import re
from pathlib import Path

from .circuit import Circuit, UnsupportedOperation


class QasmSyntaxError(ValueError):
    """Malformed input inside the accepted subset."""


_HEADER = re.compile(r"OPENQASM\s+(2\.0|3\.0|3)")
_INCLUDE = re.compile(r'include\s+"[^"]+"')
_QREG = re.compile(r"qreg\s+([A-Za-z_]\w*)\s*\[\s*(\d+)\s*\]")
_QUBIT = re.compile(r"qubit\s*\[\s*(\d+)\s*\]\s*([A-Za-z_]\w*)")
_MODIFIER = re.compile(r"ctrl(?:\s*\(\s*(\d+)\s*\))?\s*@\s*")
_APPLY = re.compile(r"([A-Za-z_]\w*)(\s*\(.*?\))?\s+(.+)")
_OPERAND = re.compile(r"([A-Za-z_]\w*)\s*\[\s*(\d+)\s*\]")
_BASE_CONTROLS = {"x": 0, "cx": 1, "ccx": 2}


def _annotations(text: str) -> None:
    for line in text.splitlines():
        match = re.match(r"\s*//\s*([io])\s+([\d\s]+)$", line)
        if match:
            indices = [int(v) for v in match.group(2).split()]
            if indices != list(range(len(indices))):
                raise UnsupportedOperation(
                    f"non-identity {'input' if match.group(1) == 'i' else 'output'} permutation"
                )


def parse_qasm(text: str) -> Circuit:
    _annotations(text)
    code = re.sub(r"//[^\n]*", "", text)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    circuit: Circuit | None = None
    register = ""
    statements = [s.strip() for s in code.split(";")]
    if statements and statements[-1]:
        raise QasmSyntaxError(f"missing ';' after {statements[-1]!r}")
    for number, statement in enumerate(statements[:-1], start=1):
        statement = " ".join(statement.split())
        if not statement:
            continue
        if number == 1 and _HEADER.fullmatch(statement):
            continue
        if _INCLUDE.fullmatch(statement):
            continue
        declaration = _QREG.fullmatch(statement) or _QUBIT.fullmatch(statement)
        if declaration:
            if circuit is not None:
                raise UnsupportedOperation("only one quantum register is supported")
            if statement.startswith("qreg"):
                register, width = declaration.group(1), int(declaration.group(2))
            else:
                width, register = int(declaration.group(1)), declaration.group(2)
            circuit = Circuit(width)
            continue
        if circuit is None:
            raise UnsupportedOperation(f"statement before register declaration: {statement!r}")
        _apply(circuit, register, statement)
    if circuit is None:
        raise QasmSyntaxError("no quantum register declared")
    return circuit


def _apply(circuit: Circuit, register: str, statement: str) -> None:
    rest = statement
    controls = 0
    while True:
        modifier = _MODIFIER.match(rest)
        if modifier is None:
            break
        controls += int(modifier.group(1) or 1)
        rest = rest[modifier.end():]
    application = _APPLY.fullmatch(rest)
    if application is None:
        raise UnsupportedOperation(f"unsupported statement: {statement!r}")
    gate, parameters, operands = application.groups()
    if gate not in (*_BASE_CONTROLS, "mcx") or parameters or "@" in operands:
        raise UnsupportedOperation(f"unsupported statement: {statement!r}")
    qubits = []
    for operand in operands.split(","):
        match = _OPERAND.fullmatch(operand.strip())
        if match is None and re.fullmatch(r"[A-Za-z_]\w*", operand.strip()):
            raise UnsupportedOperation(f"register broadcast in {statement!r}")
        if match is None:
            raise QasmSyntaxError(f"bad operand {operand.strip()!r} in {statement!r}")
        if match.group(1) != register:
            raise QasmSyntaxError(f"unknown register {match.group(1)!r} in {statement!r}")
        qubits.append(int(match.group(2)))
    if gate == "mcx":
        controls += len(qubits) - 1
    else:
        controls += _BASE_CONTROLS[gate]
    if len(qubits) != controls + 1:
        raise QasmSyntaxError(f"operand count does not match controls in {statement!r}")
    name = {0: "x", 1: "cx", 2: "ccx"}.get(controls, "mcx")
    circuit.append(name, *qubits)


def load_qasm(path: str | Path) -> Circuit:
    return parse_qasm(Path(path).read_text(encoding="utf-8"))
