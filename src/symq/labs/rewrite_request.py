"""File requests and self-contained reports for ``symq rewrite`` (research API, no promise).

One request format serves both rewrite theorems:

* ``theorem: "classical"`` — :func:`symq.labs.contextual_substitution.check_substitution`, a
  reversible basis-state theorem under an explicit input/cut contract;
* ``theorem: "coherent"`` — :func:`symq.labs.hybrid_substitution.check_hybrid_substitution`, the
  bounded local coherent channel/instrument theorem.

A request names a source and a replacement file next to it, an exact ``[start, stop)`` span, the
theorem-specific ``contract`` and declared ``weights``. Each request is proved **once**; a proved
report embeds the frozen candidate built by the checker in that same call. Replaying a report
reruns the checker from the embedded streams and refuses a report whose pinned hashes or costs do
not match them. Neither the report nor its hashes are a portable proof certificate.

Request::

    {"schema_version": 1, "kind": "symq_rewrite_request", "theorem": "classical",
     "source": "source.qasm", "replacement": "replacement.json", "span": [2, 3],
     "contract": {"initial_constants": [[4, 0]], "clean_at_cut": [4], "restored_at_cut": [],
                  "cut_assumption": null},
     "weights": {"by_kind": [["ccx", 32]], "unit": "declared_units", "default": 1},
     "require_saving": false}
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from symq.circuit import Circuit, circuit_from_dict, parse_circuit
from symq.experimental.domains import expression_from_dict
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import parse_json, program_from_dict, program_to_dict
from symq.labs.channel_composition import FrozenHybridProgram, HybridFragment
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.hybrid_substitution import LIMIT_CAPS, check_hybrid_substitution
from symq.labs.rewrite import ReceiptMismatch, Weights, compare_pins, refused_by_cost
from symq.resources import Budget

__all__ = [
    "REPORT_KIND",
    "REQUEST_KIND",
    "HybridFrame",
    "RewriteRequest",
    "candidate_stream",
    "exit_code",
    "fragment_from_dict",
    "fragment_to_dict",
    "input_paths",
    "load_request",
    "replay_report",
    "request_from_dict",
    "request_to_dict",
    "rewrite_job",
    "run_request",
]

REQUEST_KIND = "symq_rewrite_request"
REPORT_KIND = "symq_rewrite"
THEOREMS = ("classical", "coherent")
MAX_INPUT_BYTES = 2_000_000


def _keys(value: Any, allowed: set[str], required: set[str], what: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{what} must be a JSON object")
    unknown, missing = set(value) - allowed, required - set(value)
    if unknown or missing:
        raise ValueError(f"{what}: unknown fields {sorted(unknown)}, missing {sorted(missing)}")
    return value


def _ints(value: Any, what: str) -> tuple[int, ...]:
    if type(value) is not list or any(type(item) is not int for item in value):
        raise ValueError(f"{what} must be an array of integers")
    return tuple(value)


@dataclass(frozen=True)
class HybridFrame:
    """The coherent contract: local-to-global wires, local frame and oracle bounds."""

    wires: tuple[int, ...]
    clean: tuple[int, ...] = ()
    preserved: tuple[int, ...] = ()
    discarded: tuple[int, ...] = ()
    observed_slots: tuple[str, ...] = ()
    discarded_global: tuple[int, ...] = ()
    max_local_width: int = 6
    max_events: int = 8
    max_branches: int = 256

    def to_dict(self) -> dict[str, Any]:
        return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(self).items()}


@dataclass(frozen=True)
class RewriteRequest:
    theorem: str
    source: Circuit | HybridProgram
    replacement: Circuit | HybridFragment
    span: tuple[int, int]
    contract: SubstitutionContract | HybridFrame
    weights: Weights
    require_saving: bool = False


def fragment_to_dict(fragment: HybridFragment) -> dict[str, Any]:
    if type(fragment) is not HybridFragment:
        raise TypeError("a HybridFragment is required")
    return {"kind": "hybrid_fragment", "width": fragment.width,
            "classical_inputs": list(fragment.classical_inputs),
            "ops": [{"kind": op.kind, "wires": list(op.wires), "slot": op.slot,
                     "condition": op.condition, "source": op.source, "value": op.value}
                    for op in fragment.ops]}


def fragment_from_dict(value: Any) -> HybridFragment:
    doc = _keys(value, {"kind", "width", "classical_inputs", "ops"},
                {"kind", "width", "ops"}, "hybrid fragment")
    if doc["kind"] != "hybrid_fragment":
        raise ValueError("a replacement for the coherent theorem has kind 'hybrid_fragment'")
    inputs = doc.get("classical_inputs", [])
    if type(inputs) is not list or any(type(s) is not str for s in inputs):
        raise ValueError("classical_inputs must be an array of slot names")
    if type(doc["ops"]) is not list:
        raise ValueError("ops must be an array")
    ops = []
    for item in doc["ops"]:
        op = _keys(item, {"kind", "wires", "slot", "condition", "source", "value"},
                   {"kind", "wires"}, "hybrid operation")
        if type(op["kind"]) is not str:
            raise ValueError("operation kind must be a string")
        ops.append(HOp(op["kind"], _ints(op["wires"], "operation wires"), op.get("slot"),
                       op.get("condition"), op.get("source"), op.get("value")))
    return HybridFragment(doc["width"], tuple(ops), tuple(inputs))


def _weights(value: Any) -> Weights:
    doc = _keys(value, {"by_kind", "unit", "default"}, {"by_kind"}, "weights")
    pairs = doc["by_kind"]
    if type(pairs) is not list or any(type(p) is not list or len(p) != 2 for p in pairs):
        raise ValueError("weights.by_kind must be [[operation, nonnegative integer], ...]")
    return Weights(tuple(tuple(p) for p in pairs), doc.get("unit", "declared_units"),
                   doc.get("default", 1))


def _classical_contract(value: Any) -> SubstitutionContract:
    doc = _keys(value, {"initial_constants", "clean_at_cut", "restored_at_cut",
                        "cut_assumption"}, set(), "classical contract")
    constants = doc.get("initial_constants", [])
    if type(constants) is not list or any(type(p) is not list or len(p) != 2 for p in constants):
        raise ValueError("initial_constants must be [[wire, 0 or 1], ...]")
    assumption = doc.get("cut_assumption")
    return SubstitutionContract(
        tuple(tuple(p) for p in constants), _ints(doc.get("clean_at_cut", []), "clean_at_cut"),
        _ints(doc.get("restored_at_cut", []), "restored_at_cut"),
        None if assumption is None else expression_from_dict(assumption))


def _hybrid_frame(value: Any) -> HybridFrame:
    fields = set(HybridFrame.__dataclass_fields__)
    doc = _keys(value, fields, {"wires"}, "coherent contract")
    slots = doc.get("observed_slots", [])
    if type(slots) is not list or any(type(s) is not str for s in slots):
        raise ValueError("observed_slots must be an array of slot names")
    bounds = {name: doc.get(name, HybridFrame.__dataclass_fields__[name].default)
              for name in LIMIT_CAPS}
    return HybridFrame(
        _ints(doc["wires"], "wires"), _ints(doc.get("clean", []), "clean"),
        _ints(doc.get("preserved", []), "preserved"), _ints(doc.get("discarded", []), "discarded"),
        tuple(slots), _ints(doc.get("discarded_global", []), "discarded_global"), **bounds)


def request_to_dict(request: RewriteRequest) -> dict[str, Any]:
    """The request with both streams inlined, as embedded in a report."""
    classical = request.theorem == "classical"
    contract = (request.contract.document() if classical else request.contract.to_dict())
    if classical:
        contract = {k: v for k, v in contract.items() if k != "theorem"}
    return {"theorem": request.theorem,
            "source": (request.source.to_dict() if classical
                       else program_to_dict(request.source)),
            "replacement": (request.replacement.to_dict() if classical
                            else fragment_to_dict(request.replacement)),
            "span": list(request.span), "contract": contract,
            "weights": request.weights.to_dict(), "require_saving": request.require_saving}


def request_from_dict(value: Any, *, source: Any = None, replacement: Any = None) -> RewriteRequest:
    """Parse an inlined request (or a file request whose streams were loaded separately)."""
    doc = _keys(value, {"schema_version", "kind", "theorem", "source", "replacement", "span",
                        "contract", "weights", "require_saving"},
                {"theorem", "source", "replacement", "span", "contract"}, "rewrite request")
    theorem = doc["theorem"]
    if theorem not in THEOREMS:
        raise ValueError(f"theorem must be one of {THEOREMS}")
    span = _ints(doc["span"], "span")
    if len(span) != 2:
        raise ValueError("span must be [start, stop]")
    if type(doc.get("require_saving", False)) is not bool:
        raise ValueError("require_saving must be a Boolean")
    if theorem == "classical":
        source = circuit_from_dict(doc["source"]) if source is None else source
        replacement = circuit_from_dict(doc["replacement"]) if replacement is None else replacement
        contract: SubstitutionContract | HybridFrame = _classical_contract(doc["contract"])
    else:
        source = program_from_dict(doc["source"]) if source is None else source
        if type(source) is not HybridProgram:
            raise ValueError("the coherent theorem needs a hybrid source program")
        replacement = fragment_from_dict(doc["replacement"]) if replacement is None else replacement
        contract = _hybrid_frame(doc["contract"])
    weights = _weights(doc.get("weights", {"by_kind": []}))
    return RewriteRequest(theorem, source, replacement, (span[0], span[1]), contract, weights,
                          doc.get("require_saving", False))


def _beside(request_path: Path, name: Any, key: str) -> Path:
    if type(name) is not str or not name or Path(name).is_absolute():
        raise ValueError(f"{key} must be a relative file name")
    target = (request_path.parent / name).resolve()
    if not target.is_relative_to(request_path.parent.resolve()):
        raise ValueError(f"{key} must stay inside the request directory")
    return target


def _read(path: Path) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError(f"{path.name} exceeds {MAX_INPUT_BYTES} bytes")
    return data


def _document(path: Path) -> tuple[bytes, dict]:
    raw = _read(path)
    doc = parse_json(raw)
    if type(doc) is not dict:
        raise ValueError("a rewrite request is a JSON object")
    return raw, doc


def input_paths(path: str | Path) -> set[Path]:
    """The resolved request file and the source and replacement files it names."""
    request_path = Path(path)
    _, doc = _document(request_path)
    return {request_path.resolve(),
            *(_beside(request_path, doc.get(key), key) for key in ("source", "replacement"))}


def load_request(path: str | Path) -> tuple[RewriteRequest, dict[str, str]]:
    """Read a request file and the two files it names; return it and their SHA-256 digests.

    Each file is read once, and the digests are taken from the very bytes that are parsed.
    """
    request_path = Path(path)
    raw, doc = _document(request_path)
    if doc.get("schema_version") != 1 or doc.get("kind") != REQUEST_KIND:
        raise ValueError(f"expected a schema_version 1 {REQUEST_KIND!r} document")
    if doc.get("theorem") not in THEOREMS:
        raise ValueError(f"theorem must be one of {THEOREMS}")
    files = {key: _beside(request_path, doc.get(key), key) for key in ("source", "replacement")}
    blobs = {key: _read(file) for key, file in files.items()}
    digests = {"request": hashlib.sha256(raw).hexdigest(),
               **{key: hashlib.sha256(blob).hexdigest() for key, blob in blobs.items()}}
    if doc["theorem"] == "classical":
        source = parse_circuit(blobs["source"], files["source"].name)
        replacement = parse_circuit(blobs["replacement"], files["replacement"].name)
    else:
        program = program_from_dict(parse_json(blobs["source"]))
        if type(program) is not HybridProgram:
            raise ValueError("the coherent theorem needs a 'hybrid' source program")
        source = program
        replacement = fragment_from_dict(parse_json(blobs["replacement"]))
    return request_from_dict(doc, source=source, replacement=replacement), digests


def _prove(request: RewriteRequest, budget: Budget | None) -> Any:
    if request.theorem == "classical":
        return check_substitution(request.source, request.span, request.replacement,
                                  contract=request.contract, weights=request.weights,
                                  budget=budget)
    return check_hybrid_substitution(request.source, request.span, request.replacement,
                                     weights=request.weights, budget=budget,
                                     **asdict(request.contract))


def run_request(request: RewriteRequest, budget: Budget | None = None,
                files: dict[str, str] | None = None) -> dict[str, Any]:
    """Prove the request once and return the self-contained report."""
    result = _prove(request, budget)
    candidate = None
    application = "not_proved"
    if result.candidate is not None:
        if refused_by_cost(result, request.require_saving):
            application = "refused_by_cost_policy"
        else:
            application = "applied"
            candidate = (result.candidate.circuit().to_dict() if request.theorem == "classical"
                         else program_to_dict(result.candidate.to_program()))
    report = {"schema_version": 1, "kind": REPORT_KIND, "request": request_to_dict(request),
              "result": result.to_dict(), "application": application, "candidate": candidate}
    if files is not None:
        report["file_sha256"] = dict(files)
    return report


_PINS = ("reference_sha256", "candidate_sha256", "contract_sha256", "span", "cost")


def replay_report(report: Any, budget: Budget | None = None) -> dict[str, Any]:
    """Rerun a report's request from its embedded streams; a stored outcome is no authority.

    Raises :class:`symq.labs.rewrite.ReceiptMismatch` when the report's pinned hashes or costs
    do not belong to its embedded request (an edited report). The fresh outcome may differ from
    the stored one, for example after a timeout; it is the one returned.
    """
    if type(report) is not dict or report.get("schema_version") != 1 \
            or report.get("kind") != REPORT_KIND:
        raise ValueError(f"expected a schema_version 1 {REPORT_KIND!r} report")
    request = request_from_dict(report["request"])
    fresh = run_request(request, budget)
    saved = report.get("result")
    if type(saved) is not dict:
        raise ValueError("the report has no result")

    compare_pins(SimpleNamespace(**{k: saved.get(k) for k in _PINS}),
                 SimpleNamespace(**{k: fresh["result"].get(k) for k in _PINS}), _PINS)
    if saved.get("outcome") == "equivalent" and fresh["result"]["outcome"] == "equivalent" \
            and report.get("candidate") is not None \
            and report["candidate"] != fresh["candidate"]:
        raise ReceiptMismatch("the embedded candidate is not the stream the checker proved")
    fresh["replayed"] = {"stored_outcome": saved.get("outcome")}
    return fresh


def rewrite_job(request: RewriteRequest, budget: Budget | None,
                files: dict[str, str] | None) -> dict[str, Any]:
    """Importable worker for :func:`symq.experimental.execution.run_isolated`."""
    return run_request(request, budget, files)


def exit_code(report: dict[str, Any]) -> int:
    """``symq`` convention: 0 proved, 2 anything else (never a proved difference here)."""
    return 0 if report["result"]["outcome"] == "equivalent" else 2


def candidate_stream(report: dict[str, Any]) -> Circuit | FrozenHybridProgram | None:
    """The applied candidate of a report, rebuilt from its embedded JSON."""
    if report.get("candidate") is None:
        return None
    if report["request"]["theorem"] == "classical":
        return circuit_from_dict(report["candidate"])
    return FrozenHybridProgram.freeze(program_from_dict(report["candidate"]))
