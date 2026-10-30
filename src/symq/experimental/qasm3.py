"""Fail-closed, bounded OpenQASM 3 subset for the exact hybrid IR.

Only scalar indexed operands, sign/permutation gates, Z measurement, true
reset, affine bit assignments and single-level if blocks are accepted. No
loops, custom gates, timing, general H/rotations, casts or implicit broadcasts.
"""
from __future__ import annotations

import re

from symq.circuit import UnsupportedOperation
from symq.experimental.hybrid import HOp, HybridIR, HybridProgram, freeze_hybrid
from symq.resources import Budget, Guard, session_scoped

_IDENT = r"[A-Za-z_][A-Za-z_0-9]*"
_REF = re.compile(rf"({_IDENT})(?:\[([0-9]+)\])?\Z")
_DECL = re.compile(rf"(qubit|bit)(?:\[([1-9][0-9]*)\])?\s+({_IDENT})\Z")
_GATES = {"x": 1, "cx": 2, "ccx": 3, "swap": 2, "cswap": 3,
          "z": 1, "cz": 2, "ccz": 3}


@session_scoped
def parse_qasm3(text: str, *, data: int | None = None, ancillas: int = 0,
                max_instructions: int = 20_000, max_register_bits: int = 4096,
                max_condition_ops: int = 128, budget: Budget | None = None) -> HybridIR:
    """Parse the documented subset, preserving measurements and dirty resets.

    Wires flatten in declaration order. ``data``/``ancillas`` explicitly mark
    coherent inputs versus initially-zero wires; without data, all declared
    quantum wires are data. Declared classical bits start at zero (QASM 3).
    """
    if type(text) is not str:
        raise TypeError("QASM source must be text")
    resource_guard = Guard(budget)
    resource_guard.check_time()
    for name, limit in (("max_instructions", max_instructions),
                        ("max_register_bits", max_register_bits),
                        ("max_condition_ops", max_condition_ops)):
        if type(limit) is not int or limit < 1:
            raise ValueError(f"{name} must be positive")
    if len(text) > max_instructions * 1024:
        raise UnsupportedOperation("QASM source size budget exceeded")
    text = re.sub(r"//[^\n]*", "", text)
    # A complete tokenization ensures no unparsed suffix or ignored metadata.
    tokens = re.findall(r"[^;{}]+[;{}]|[;{}]", text)
    if "".join(tokens).strip() != text.strip():
        raise UnsupportedOperation("unterminated QASM statement")
    tokens = [token.strip() for token in tokens]
    if not tokens or tokens.pop(0) not in {"OPENQASM 3;", "OPENQASM 3.0;"}:
        raise UnsupportedOperation("explicit OPENQASM 3 header required")
    registers: dict[str, tuple[str, int, int, bool]] = {}
    widths = {"qubit": 0, "bit": 0}
    ops: list[HOp] = []
    started = False
    condition = None
    block_size = 0
    temporary = 0

    def add(op):
        ops.append(op)
        if len(ops) > max_instructions:
            raise UnsupportedOperation("QASM instruction budget exceeded")

    def ref(value, expected):
        match = _REF.fullmatch(value.strip())
        if match is None or match[1] not in registers:
            raise UnsupportedOperation(f"undeclared or malformed operand {value!r}")
        kind, offset, length, scalar = registers[match[1]]
        index = int(match[2]) if match[2] is not None else 0
        if kind != expected or (match[2] is None and not scalar) or index >= length:
            raise UnsupportedOperation(f"operand shape/type mismatch {value!r}")
        return offset + index if expected == "qubit" else f"b{offset + index}"

    def guard(value):
        match = re.fullmatch(r"\s*(!)?\s*(.+?)(?:\s*==\s*([01]))?\s*", value)
        if match is None:
            raise UnsupportedOperation("unsupported classical condition")
        bit = ref(match[2], "bit")
        inverted = bool(match[1]) ^ (match[3] == "0")
        return ("!" if inverted else "") + bit

    def statement(value, cond):
        nonlocal temporary
        gate = re.fullmatch(rf"({_IDENT})\s+(.+)", value)
        if gate and gate[1] in _GATES:
            wires = tuple(ref(v, "qubit") for v in gate[2].split(","))
            if len(wires) != _GATES[gate[1]]:
                raise UnsupportedOperation("incorrect QASM gate arity")
            add(HOp(gate[1], wires, condition=cond))
            return
        if cond is not None:
            raise UnsupportedOperation("conditions may guard only value/sign gates")
        measure = re.fullmatch(r"(.+?)\s*=\s*measure\s+(.+)", value)
        if measure:
            add(HOp("measure_z", (ref(measure[2], "qubit"),),
                    slot=ref(measure[1], "bit")))
            return
        if value.startswith("reset "):
            add(HOp("reset", (ref(value[6:], "qubit"),)))
            return
        xor = re.fullmatch(r"(.+?)\s*\^=\s*(.+)", value)
        if xor:
            add(HOp("oxor", slot=ref(xor[1], "bit"), source=ref(xor[2], "bit")))
            return
        assignment = re.fullmatch(r"(.+?)\s*=\s*(.+)", value)
        if assignment:
            dest = ref(assignment[1], "bit")
            terms = assignment[2].split("^")
            if len(terms) > max_condition_ops:
                raise UnsupportedOperation("affine expression budget exceeded")
            # Compute through an internal slot so reads of dest precede its write.
            temp = f"b{widths['bit'] + temporary}"
            temporary += 1
            add(HOp("store", slot=temp, value=0))
            for term in terms:
                term = term.strip()
                if term in {"0", "1"}:
                    if term == "1":
                        add(HOp("invert", slot=temp))
                else:
                    negate = term.startswith("!")
                    source = ref(term[1:] if negate else term, "bit")
                    add(HOp("oxor", slot=temp, source=source))
                    if negate:
                        add(HOp("invert", slot=temp))
            add(HOp("store", slot=dest, value=0))
            add(HOp("oxor", slot=dest, source=temp))
            return
        raise UnsupportedOperation(f"unsupported QASM statement {value!r}")

    for token in tokens:
        resource_guard.check_time()
        if token == "}":
            if condition is None or block_size == 0:
                raise UnsupportedOperation("unmatched or empty conditional block")
            condition = None
            continue
        if not token.endswith((";", "{")):
            raise UnsupportedOperation("invalid QASM delimiter")
        value, delimiter = token[:-1].strip(), token[-1]
        if value == 'include "stdgates.inc"' and delimiter == ";" and not started:
            continue
        decl = _DECL.fullmatch(value)
        if decl and delimiter == ";" and not started:
            kind, length, name = decl[1], int(decl[2] or 1), decl[3]
            if name in registers or widths[kind] + length > max_register_bits:
                raise UnsupportedOperation("duplicate or oversized register declaration")
            registers[name] = (kind, widths[kind], length, decl[2] is None)
            widths[kind] += length
            continue
        if not started:
            for bit in range(widths["bit"]):
                add(HOp("store", slot=f"b{bit}", value=0))
            started = True
        if value.startswith("if"):
            if condition is not None:
                raise UnsupportedOperation("nested conditions are unsupported")
            match = re.fullmatch(r"if\s*\(([^()]*)\)\s*(.*)", value)
            if match is None:
                raise UnsupportedOperation("malformed condition")
            current = guard(match[1])
            if delimiter == "{" and not match[2]:
                condition, block_size = current, 0
            elif delimiter == ";" and match[2]:
                statement(match[2], current)
            else:
                raise UnsupportedOperation("invalid conditional body")
        elif delimiter == ";":
            statement(value, condition)
            if condition is not None:
                block_size += 1
                if block_size > max_condition_ops:
                    raise UnsupportedOperation("conditional block budget exceeded")
        else:
            raise UnsupportedOperation("unsupported scope")
    if condition is not None:
        raise UnsupportedOperation("unclosed conditional block")
    if not started:
        for bit in range(widths["bit"]):
            add(HOp("store", slot=f"b{bit}", value=0))
    if data is None:
        data = widths["qubit"] - ancillas
    if type(data) is not int or type(ancillas) is not int or data + ancillas != widths["qubit"]:
        raise UnsupportedOperation("declared quantum width must equal data + ancillas")
    result = freeze_hybrid(HybridProgram(data, ancillas, ops))
    resource_guard.check_time()
    return result
