"""Versioned, closed JSON documents for the opt-in experimental API."""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from symq.phase import Op, PhaseProgram

SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024


def _keys(value: Any, expected: set[str], description: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{description} requires exactly {sorted(expected)}")
    return value


def program_to_dict(program: Any) -> dict:
    if type(program) is PhaseProgram:
        # Reconstruct dimensions as validate() primarily checks instructions.
        PhaseProgram(program.data, program.ancillas)
        program.validate()
        return {"schema_version": SCHEMA_VERSION, "kind": "sign_hmr",
                "data": program.data, "ancillas": program.ancillas,
                "ops": [{"kind": op.kind, "qubits": list(op.qubits),
                         "outcome": op.outcome} for op in program.ops]}
    from .hybrid import HybridIR, HybridProgram
    if type(program) is not HybridProgram:
        if type(program) is HybridIR:
            program = program.to_program()
        else:
            raise TypeError("a PhaseProgram or HybridProgram is required")
    program.validate()
    return {"schema_version": SCHEMA_VERSION, "kind": "hybrid",
            "data": program.data, "ancillas": program.ancillas,
            "ops": [{"kind": op.kind, "wires": list(op.wires), "slot": op.slot,
                     "condition": op.condition, "source": op.source, "value": op.value}
                    for op in program.ops]}


def program_from_dict(value: Any) -> Any:
    _keys(value, {"schema_version", "kind", "data", "ancillas", "ops"}, "program")
    if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported program schema_version")
    if type(value["ops"]) is not list:
        raise ValueError("program ops must be an array")
    if value["kind"] == "sign_hmr":
        ops = []
        for op in value["ops"]:
            _keys(op, {"kind", "qubits", "outcome"}, "sign/HMR operation")
            if type(op["qubits"]) is not list:
                raise ValueError("operation qubits must be an array")
            ops.append(Op(op["kind"], tuple(op["qubits"]), op["outcome"]))
        program = PhaseProgram(value["data"], value["ancillas"], ops)
        program.validate()
        return program
    if value["kind"] == "hybrid":
        from .hybrid import HOp, HybridProgram
        ops = []
        for op in value["ops"]:
            _keys(op, {"kind", "wires", "slot", "condition", "source", "value"},
                  "hybrid operation")
            if type(op["wires"]) is not list:
                raise ValueError("operation wires must be an array")
            ops.append(HOp(op["kind"], tuple(op["wires"]), op["slot"],
                           op["condition"], op["source"], op["value"]))
        return HybridProgram(value["data"], value["ancillas"], ops)
    raise ValueError(f"unsupported program kind {value['kind']!r}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value}")


def load_json(path: str | Path, *, max_bytes: int = MAX_DOCUMENT_BYTES) -> Any:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    with Path(path).open("rb") as source:
        data = source.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("JSON document exceeds max_bytes")
    return json.loads(data, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def save_json(value: Any, path: str | Path) -> None:
    # Encode before opening the destination, so malformed data cannot truncate it.
    encoded = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    Path(path).write_text(encoded, encoding="utf-8")


def load_program(path: str | Path) -> Any:
    return program_from_dict(load_json(path))


def save_program(program: Any, path: str | Path) -> None:
    save_json(program_to_dict(program), path)


def load_contract(path: str | Path) -> Any:
    from .contracts import VerificationContract
    return VerificationContract.from_dict(load_json(path))


def save_contract(contract: Any, path: str | Path) -> None:
    from .contracts import VerificationContract
    if type(contract) is not VerificationContract:
        raise TypeError("a VerificationContract is required")
    save_json(contract.to_dict(), path)


def result_to_dict(result: Any) -> dict:
    if hasattr(result, "to_dict"):
        value = result.to_dict()
    elif is_dataclass(result) and not isinstance(result, type):
        value = asdict(result)
        value.setdefault("schema_version", SCHEMA_VERSION)
    else:
        raise TypeError("an experimental result dataclass is required")
    if type(value) is not dict:
        raise TypeError("result document must be an object")
    return value


def save_result(result: Any, path: str | Path) -> None:
    """Save a result record; loading a JSON record never authenticates a proof."""
    save_json(result_to_dict(result), path)
