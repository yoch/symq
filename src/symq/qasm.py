"""Strict OpenQASM 2/3 reader for the X/CX/CCX/MCX subset.

Accepted statements: the version header, ``include``, exactly one quantum register
(``qreg q[n];`` or ``qubit[n] q;``) and applications of ``x``, ``cx``, ``ccx`` or ``mcx``,
optionally prefixed by positive-control modifiers ``ctrl @`` / ``ctrl(k) @``. Anything else
(other gates, ``negctrl``, ``inv``, measurements, classical bits, barriers, gate
definitions) raises :class:`~symq.UnsupportedOperation`. RevLib-style ``// i`` and ``// o``
annotations are accepted only when they are the identity permutation, because a
non-trivial input/output permutation would change the meaning of the circuit.

Every refusal is a :class:`~symq.QasmSyntaxError` or an :class:`~symq.UnsupportedOperation`
(both are ``SymqError`` and ``ValueError``), prefixed with the line of the statement once the
statements are being read. Numbers are ASCII decimal literals of at most
:data:`MAX_INDEX`; a register has at least one qubit.
"""
from __future__ import annotations

import re
from pathlib import Path

from .circuit import Circuit
from .errors import QasmSyntaxError, UnsupportedOperation

MAX_INDEX = 2**31 - 1
"""Largest register width or qubit index accepted in a file (no backend comes near it)."""

_HEADER = re.compile(r"OPENQASM\s+(2\.0|3\.0|3)")
_INCLUDE = re.compile(r'include\s+"([^"]+)"')
_INCLUDES = {"3.0": frozenset({"stdgates.inc"}), "3": frozenset({"stdgates.inc"}),
             "2.0": frozenset({"qelib1.inc"})}
# ``[0-9]`` and not ``\d``: ``\d`` also matches the decimal digits of other scripts, which
# ``int`` would then silently convert.
_QREG = re.compile(r"qreg\s+([A-Za-z_]\w*)\s*\[\s*([0-9]+)\s*\]")
_QUBIT = re.compile(r"qubit\s*\[\s*([0-9]+)\s*\]\s*([A-Za-z_]\w*)")
_MODIFIER = re.compile(r"ctrl(?:\s*\(\s*([0-9]+)\s*\))?\s*@\s*")
_APPLY = re.compile(r"([A-Za-z_]\w*)(\s*\(.*?\))?\s+(.+)")
_OPERAND = re.compile(r"([A-Za-z_]\w*)\s*\[\s*([0-9]+)\s*\]")
_BASE_CONTROLS = {"x": 0, "cx": 1, "ccx": 2}


def bounded_index(digits: str) -> int | None:
    """The value of ASCII decimal ``digits``, or ``None`` when it exceeds :data:`MAX_INDEX`.

    The length is tested first, so a literal of thousands of digits is never converted (Python
    refuses such conversions with a bare ``ValueError``). Shared with the kickmix reader.
    """
    significant = digits.lstrip("0")
    if len(significant) > 10:
        return None
    value = int(significant or "0")
    return value if value <= MAX_INDEX else None


def _number(digits: str, what: str) -> int:
    value = bounded_index(digits)
    if value is None:
        raise QasmSyntaxError(f"{what} exceeds the supported maximum {MAX_INDEX}")
    return value


def _strip_comments(text: str) -> str:
    """``text`` without its ``//`` and ``/* */`` comments, line breaks kept.

    One left-to-right pass: whichever comment opens first owns everything up to its own end, so a
    ``//`` inside a block comment and a ``/*`` inside a line comment are plain comment text.
    Stripping the two kinds in two passes got this wrong: a ``//`` inside a block comment removed
    the closing ``*/``, and the statements up to the next ``*/`` vanished with it. A block comment
    keeps its line breaks so later statements keep their line numbers. Linear in the text.
    """
    pieces, position = [], 0
    line, block = text.find("//"), text.find("/*")
    while line != -1 or block != -1:
        if block == -1 or (line != -1 and line < block):
            end = text.find("\n", line)
            end = len(text) if end == -1 else end
            pieces.append(text[position:line])
            position = end  # the line break itself stays
        else:
            end = text.find("*/", block + 2)
            if end == -1:
                raise QasmSyntaxError(
                    f"line {text.count(chr(10), 0, block) + 1}: unterminated block comment")
            pieces.append(text[position:block])
            pieces.append("\n" * text.count("\n", block, end))
            position = end + 2
        if line != -1 and line < position:
            line = text.find("//", position)
        if block != -1 and block < position:
            block = text.find("/*", position)
    pieces.append(text[position:])
    return "".join(pieces)


def _annotations(text: str) -> None:
    for line in text.splitlines():
        # ``\d`` on purpose: a RevLib annotation written with the digits of another script must
        # be recognised as an annotation and refused, not skipped as an ordinary comment.
        match = re.match(r"\s*//\s*([io])\s+([\d\s]+)$", line)
        if match:
            tokens = match.group(2).split()
            if any(re.fullmatch("[0-9]+", token) is None for token in tokens):
                raise QasmSyntaxError(
                    f"annotation indices must be ASCII decimal digits: {line.strip()!r}")
            indices = [_number(v, "annotation index") for v in tokens]
            if indices != list(range(len(indices))):
                raise UnsupportedOperation(
                    f"non-identity {'input' if match.group(1) == 'i' else 'output'} permutation"
                )


def parse_qasm(text: str) -> Circuit:
    """The circuit described by strict OpenQASM 2/3 ``text`` (see the module docstring).

    Returns a valid :class:`~symq.Circuit` or raises :class:`~symq.QasmSyntaxError` (malformed
    text) or :class:`~symq.UnsupportedOperation` (well-formed text outside the accepted subset).
    """
    if not isinstance(text, str):
        raise TypeError("OpenQASM source must be a str")
    # One line-break convention, so that line numbers mean the same for every file.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    _annotations(text)
    code = _strip_comments(text)
    raw = code.split(";")
    if raw[-1].strip():
        raise QasmSyntaxError(f"missing ';' after {raw[-1].strip()!r}")
    state = _State()
    offset = 0
    for number, piece in enumerate(raw[:-1], start=1):
        start = offset + len(piece) - len(piece.lstrip())
        offset += len(piece) + 1
        statement = " ".join(piece.split())
        if not statement:
            continue
        try:
            _statement(state, number, statement)
        except (QasmSyntaxError, UnsupportedOperation) as error:
            line = code.count("\n", 0, start) + 1
            error.args = (f"line {line}: {error}",)
            raise
    if state.version is None:
        raise QasmSyntaxError("missing the OPENQASM version header")
    if state.circuit is None:
        raise QasmSyntaxError("no quantum register declared")
    return state.circuit


class _State:
    """What the statements read so far have established."""

    def __init__(self) -> None:
        self.circuit: Circuit | None = None
        self.register = ""
        self.version: str | None = None


def _statement(state: _State, number: int, statement: str) -> None:
    circuit, register, version = state.circuit, state.register, state.version
    header = _HEADER.fullmatch(statement)
    if header is not None:
        if version is not None or number != 1:
            raise QasmSyntaxError("exactly one version header is required, as the first statement")
        state.version = header.group(1)
        return
    include = _INCLUDE.fullmatch(statement)
    if include is not None:
        if version is None:
            raise UnsupportedOperation(f"include before the version header: {statement!r}")
        if include.group(1) not in _INCLUDES[version]:
            raise UnsupportedOperation(
                f"unsupported include {include.group(1)!r} for OpenQASM {version}; "
                f"accepted: {sorted(_INCLUDES[version])}"
            )
        return
    if version is None:
        raise QasmSyntaxError(f"statement before the version header: {statement!r}")
    declaration = _QREG.fullmatch(statement) or _QUBIT.fullmatch(statement)
    if declaration:
        if circuit is not None:
            raise UnsupportedOperation("only one quantum register is supported")
        if statement.startswith("qreg"):
            register, digits = declaration.group(1), declaration.group(2)
        else:
            digits, register = declaration.group(1), declaration.group(2)
        width = _number(digits, "register width")
        if width < 1:
            raise QasmSyntaxError(f"a register needs at least one qubit: {statement!r}")
        state.register, state.circuit = register, Circuit(width)
        return
    if circuit is None:
        raise UnsupportedOperation(f"statement before register declaration: {statement!r}")
    _apply(circuit, register, statement)


def _apply(circuit: Circuit, register: str, statement: str) -> None:
    rest = statement
    controls = 0
    while True:
        modifier = _MODIFIER.match(rest)
        if modifier is None:
            break
        count = 1 if modifier.group(1) is None else _number(modifier.group(1), "control count")
        if count < 1:
            raise QasmSyntaxError(f"ctrl(0) is not a control modifier in {statement!r}")
        controls += count
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
        qubits.append(_number(match.group(2), "qubit index"))
    if gate == "mcx":
        controls += len(qubits) - 1
    else:
        controls += _BASE_CONTROLS[gate]
    if len(qubits) != controls + 1:
        raise QasmSyntaxError(f"operand count does not match controls in {statement!r}")
    name = {0: "x", 1: "cx", 2: "ccx"}.get(controls, "mcx")
    if len(set(qubits)) != len(qubits):
        raise QasmSyntaxError(f"repeated qubit in {statement!r}")
    if max(qubits) >= circuit.width:
        raise QasmSyntaxError(
            f"qubit index out of range for a register of {circuit.width} in {statement!r}")
    circuit.append(name, *qubits)


def load_qasm(path: str | Path) -> Circuit:
    """Read and parse an OpenQASM file; a file that is not UTF-8 text is a syntax error."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise QasmSyntaxError(f"{path}: not UTF-8 text") from None
    return parse_qasm(text)
