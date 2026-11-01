"""Opt-in, file-based P0 workflow for *classical contextual* substitutions.

This composes, rather than replaces, the exact SAT contextual theorem:
import closed-format circuits, parse an explicit cut/restoration contract,
check the real source interval, replay on immutable snapshots, account for
declared integer gate costs, and write a self-contained report with SHA-256.

The accepted physical semantics are reversible basis-state X/CX/CCX/MCX
under the proven classical initial-input contract. This does NOT prove
an unrestricted coherent channel, relative phase or HMR correction.

The report's saved success flag is NEVER proof authority: replay rebuilds
the exact circuits and contract and re-runs the verifier. A failure or
timeout never exports an applied candidate. This is a research CLI/API,
not a stable public facade or an independently checkable UNSAT certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from symq._io import atomic_write_text
from symq.circuit import Circuit, Gate
from symq.hashing import canonical_sha256
from symq.kickmix import parse_kmx
from symq.labs.classical_transcript import Program
from symq.labs.contextual_substitution import (
    GateWeights,
    SubstitutionContract,
    apply_verified_substitution,
    check_substitution,
)
from symq.qasm import parse_qasm
from symq.resources import Budget, Guard, ResourceLimitExceeded
from symq.sat.assumptions import And, Const, Eq, Not, Var, Xor

MAX_BYTES = 2_000_000
MAX_GATES = 15_000
MAX_WIDTH = 128
MAX_EXPR_NODES = 512
KIND = "symq_contextual_substitution_workflow"
REQUEST_KIND = "symq_contextual_substitution_request"


def _read_bytes(path: Path) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input exceeds the 2 MB research workflow limit")
    return raw


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON field: {name}")
        result[name] = value
    return result


def _json_bytes(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid UTF-8 or excessive JSON nesting") from exc


def _object(value: Any, *, fields: set[str], required: set[str]) -> dict[str, Any]:
    if type(value) is not dict or (set(value) - fields) or (required - set(value)):
        raise ValueError(f"expected JSON object with fields {sorted(fields)}")
    return value


def _program_dict(program: Program) -> dict[str, Any]:
    return {
        "kind": "classical_reversible",
        "width": program.width,
        "gates": [[gate.name, list(gate.qubits)] for gate in program.gates],
    }


def _circuit_dict(value: Any) -> Circuit:
    data = _object(value, fields={"kind", "width", "gates"}, required={"width", "gates"})
    if data.get("kind", "classical_reversible") != "classical_reversible":
        raise ValueError("only classical_reversible circuit JSON is supported")
    if type(data["gates"]) is not list or len(data["gates"]) > MAX_GATES:
        raise ValueError("gate list is invalid or exceeds the 15000-gate limit")
    gates: list[Gate] = []
    for item in data["gates"]:
        if (type(item) is not list or len(item) != 2 or type(item[0]) is not str
                or type(item[1]) is not list):
            raise ValueError("gates must be [name, [control...,target]] arrays")
        gates.append(Gate(item[0], tuple(item[1])))
    circuit = Circuit(data["width"], gates)
    if circuit.width > MAX_WIDTH:
        raise ValueError("circuit width exceeds the 128-wire limit")
    return circuit


def load_circuit_file(path: str | Path) -> tuple[Circuit, str]:
    """Read and hash the *same bytes* whose strict grammar is interpreted."""
    filename = Path(path)
    raw = _read_bytes(filename)
    suffix = filename.suffix.lower()
    if suffix == ".json":
        circuit = _circuit_dict(_json_bytes(raw))
    elif suffix in (".qasm", ".qasm2", ".qasm3"):
        circuit = parse_qasm(raw.decode("utf-8"))
    elif suffix == ".kmx":
        circuit = parse_kmx(raw.decode("utf-8")).to_circuit()
    else:
        raise ValueError("supported circuit inputs: .json, .qasm, .qasm2, .qasm3, .kmx")
    if circuit.width > MAX_WIDTH or len(circuit.gates) > MAX_GATES:
        raise ValueError("circuit exceeds the 128-wire/15000-gate limits")
    return circuit, hashlib.sha256(raw).hexdigest()


def _expression(value: Any) -> Any:
    nodes = 0

    def parse(node: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_EXPR_NODES or depth > 32:
            raise ValueError("cut expression exceeds the bounded AST limits")
        if type(node) is not list or not node or type(node[0]) is not str:
            raise ValueError("cut assumption must be a closed tagged-array expression")
        name = node[0]
        if name == "const" and len(node) == 2 and type(node[1]) is bool:
            return Const(node[1])
        if name == "var" and len(node) == 2 and type(node[1]) is str:
            return Var(node[1])
        if name == "not" and len(node) == 2:
            return Not(parse(node[1], depth + 1))
        if name in ("and", "xor", "eq") and len(node) == 3:
            cls = {"and": And, "xor": Xor, "eq": Eq}[name]
            return cls(parse(node[1], depth + 1), parse(node[2], depth + 1))
        raise ValueError(f"invalid or unsupported cut-expression node: {name}")

    return None if value is None else parse(value, 0)


def _integers(value: Any, what: str) -> tuple[int, ...]:
    if type(value) is not list or any(type(w) is not int for w in value):
        raise ValueError(f"{what} must be an array of integer wire indices")
    return tuple(value)


def load_contract_json(value: Any, width: int) -> SubstitutionContract:
    data = _object(
        value,
        fields={"initial_constants", "clean_at_cut", "restored_at_cut",
                "cut_assumption", "theorem"},
        required={"initial_constants", "clean_at_cut", "restored_at_cut"},
    )
    if data.get("theorem", "classical_contextual_full") != "classical_contextual_full":
        raise ValueError("only the classical_contextual_full theorem is admitted")
    initial = data["initial_constants"]
    if (type(initial) is not list or any(type(pair) is not list or len(pair) != 2
            or any(type(x) is not int for x in pair) for pair in initial)):
        raise ValueError("initial_constants must be [[wire, 0/1], ...]")
    contract = SubstitutionContract(
        initial_constants=tuple(tuple(pair) for pair in initial),
        clean_at_cut=_integers(data["clean_at_cut"], "clean_at_cut"),
        restored_at_cut=_integers(data["restored_at_cut"], "restored_at_cut"),
        cut_assumption=_expression(data.get("cut_assumption")),
    )
    contract.validate(width)
    return contract


def _weights(value: Any) -> GateWeights:
    data = _object(value, fields={"x", "cx", "ccx", "mcx"},
                   required={"x", "cx", "ccx", "mcx"})
    return GateWeights(**data)


def _span(value: Any) -> tuple[int, int]:
    if type(value) is not list or len(value) != 2 or any(type(x) is not int for x in value):
        raise ValueError("span must be an integer [start,stop] array")
    return value[0], value[1]


def _timeout(value: Any) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
        raise ValueError("timeout_seconds must be a positive finite number")
    return float(value)


def _mark(report: dict[str, Any]) -> dict[str, Any]:
    report["semantic_sha256"] = canonical_sha256(report)
    return report


def _execute(
    source: Circuit, replacement: Circuit, span: tuple[int, int],
    contract: SubstitutionContract, weights: GateWeights, guard: Guard,
    *, identities: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One proof, then a second fresh proof before immutable application."""
    frozen_source = Program.freeze(source)
    frozen_replacement = Program.freeze(replacement)
    guard.check_time()
    record: dict[str, Any] = {
        "schema_version": 1,
        "kind": KIND,
        "inputs": {
            "source": _program_dict(frozen_source),
            "replacement": _program_dict(frozen_replacement),
            "span": list(span),
            "contract": contract.document(),
            "weights": asdict(weights),
        },
        "file_provenance": identities or {},
    }
    try:
        receipt = check_substitution(
            frozen_source.circuit(), span, frozen_replacement.circuit(),
            contract=contract, weights=weights, budget=guard.inherited_budget(),
        )
        guard.check_time()
        if receipt.equivalent:
            applied = apply_verified_substitution(
                receipt, frozen_source.circuit(), span, frozen_replacement.circuit(),
                contract=contract, budget=guard.inherited_budget(),
            )
            if not applied.proof.equivalent:
                raise ValueError("replayed contextual proof was not equivalent")
            guard.check_time()
            record["result"] = applied.proof.to_dict()
            record["candidate"] = _program_dict(applied.candidate)
        else:
            record["result"] = receipt.to_dict()
            record["candidate"] = None
    except ResourceLimitExceeded as exc:
        record["result"] = {"outcome": "inconclusive", "reason": str(exc)}
        record["candidate"] = None
    return _mark(record)


def verify_request(
    request_path: str | Path, *, timeout_seconds: float | None = None,
    report_path: str | Path | None = None,
) -> dict:
    """Import a closed JSON request and return an embedded, replayable report."""
    guard = Guard(Budget(max_seconds=30 if timeout_seconds is None
                         else _timeout(timeout_seconds)))
    path = Path(request_path)
    request_raw = _read_bytes(path)
    request = _object(
        _json_bytes(request_raw),
        fields={"schema_version", "kind", "source", "replacement", "span",
                "contract", "weights"},
        required={"schema_version", "kind", "source", "replacement", "span",
                  "contract", "weights"},
    )
    if type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValueError("request requires schema_version 1")
    if request["kind"] != REQUEST_KIND:
        raise ValueError("unrecognized workflow request kind")
    paths = []
    for key in ("source", "replacement"):
        name = request[key]
        if type(name) is not str or not name or Path(name).is_absolute():
            raise ValueError(f"{key} must be a nonempty relative filename")
        resolved = (path.parent / name).resolve()
        if not resolved.is_relative_to(path.parent.resolve()):
            raise ValueError("request files must remain inside the request directory")
        paths.append(resolved)
    if report_path is not None:
        output = Path(report_path).resolve()
        sidecar = output.with_name(output.name + ".sha256")
        if output in (path.resolve(), *paths) or sidecar in (path.resolve(), *paths):
            raise ValueError("report and sidecar must not overwrite input files")
    source, source_sha = load_circuit_file(paths[0])
    replacement, replacement_sha = load_circuit_file(paths[1])
    contract = load_contract_json(request["contract"], source.width)
    weights = _weights(request["weights"])
    span = _span(request["span"])
    return _execute(
        source, replacement, span, contract, weights, guard,
        identities={
            "request_sha256": hashlib.sha256(request_raw).hexdigest(),
            "source_file_sha256": source_sha, "replacement_file_sha256": replacement_sha,
        },
    )


def _check_digest(report: dict[str, Any]) -> None:
    if (type(report) is not dict or type(report.get("semantic_sha256")) is not str
            or len(report["semantic_sha256"]) != 64):
        raise ValueError("missing semantic report SHA-256")
    actual = canonical_sha256({k: v for k, v in report.items() if k != "semantic_sha256"})
    if actual != report["semantic_sha256"]:
        raise ValueError("semantic report SHA-256 mismatch")


def replay_report(report: dict[str, Any], *, timeout_seconds: float = 30) -> dict[str, Any]:
    """Recompute, not deserialize as proof, the same complete verdict and candidate."""
    _check_digest(report)
    if report.get("kind") != KIND or report.get("schema_version") != 1:
        raise ValueError("unknown contextual workflow artifact version")
    input_data = _object(
        report.get("inputs"),
        fields={"source", "replacement", "span", "contract", "weights"},
        required={"source", "replacement", "span", "contract", "weights"},
    )
    source = _circuit_dict(input_data["source"])
    replacement = _circuit_dict(input_data["replacement"])
    contract = load_contract_json(input_data["contract"], source.width)
    weights = _weights(input_data["weights"])
    fresh = _execute(
        source, replacement, _span(input_data["span"]), contract, weights,
        Guard(Budget(max_seconds=_timeout(timeout_seconds))),
        identities=report.get("file_provenance"),
    )
    previous = report.get("result")
    current = fresh["result"]
    if type(previous) is not dict:
        raise ValueError("report has no typed verifier result")
    if previous.get("outcome") in ("unsupported", "inconclusive"):
        raise ValueError("no decisive proof result to replay")
    fields = ("outcome", "reference_sha256", "candidate_sha256",
              "contract_sha256", "span", "cost", "theorem", "engine")
    if any(canonical_sha256(previous.get(k)) != canonical_sha256(current.get(k))
           for k in fields):
        raise ValueError("fresh proof disagrees with saved outcome or source/contract/cost pins")
    if report.get("candidate") != fresh.get("candidate"):
        raise ValueError("saved candidate does not match the freshly verified application")
    return fresh


def _save_report(path: Path, artifact: dict[str, Any]) -> None:
    payload = (json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n")
    atomic_write_text(path, payload)
    atomic_write_text(path.with_name(path.name + ".sha256"),
                      hashlib.sha256(payload.encode("utf-8")).hexdigest() + "\n")


def _read_report(path: Path) -> dict[str, Any]:
    raw = _read_bytes(path)
    sidecar = path.with_name(path.name + ".sha256")
    expected = _read_bytes(sidecar).decode("ascii").strip()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("report file SHA-256 sidecar mismatch")
    report = _json_bytes(raw)
    _check_digest(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify", help="import, check, replay, and write a pinned report")
    check.add_argument("request", type=Path)
    check.add_argument("--report", type=Path, required=True)
    check.add_argument("--timeout", type=float, default=30)
    replay = commands.add_parser("replay", help="recompute a self-contained report")
    replay.add_argument("report", type=Path)
    replay.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            if args.report.resolve() == args.request.resolve():
                raise ValueError("report must not overwrite the input request")
            data = verify_request(
                args.request, timeout_seconds=args.timeout, report_path=args.report
            )
            _save_report(args.report, data)
        else:
            data = replay_report(_read_report(args.report), timeout_seconds=args.timeout)
        result = data["result"]
        print(json.dumps({
            "outcome": result["outcome"], "reason": result["reason"],
            "semantic_sha256": data["semantic_sha256"],
            "weighted_delta": result.get("cost", {}).get("weighted_delta"),
            "candidate_embedded": data["candidate"] is not None,
        }, indent=2, sort_keys=True))
        return {"equivalent": 0, "not_proved": 1, "precondition_failed": 1}.get(
            result["outcome"], 2
        )
    except ResourceLimitExceeded as exc:
        print(f"symq workflow inconclusive: {exc}", file=sys.stderr)
        return 2
    except (ValueError, TypeError, OSError, KeyError) as exc:
        print(f"symq workflow invalid: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
