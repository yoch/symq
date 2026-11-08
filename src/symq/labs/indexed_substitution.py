"""Compose strict indexed extraction with a fresh classical site proof.

The output is a pinned substitution *plan*, never a rewritten complete file.
Only the builder-issued index is trusted in process; portable replay rebuilds
it from independently pinned complete source bytes. No phase/measurement or
external preparation theorem is implied. See docs/guide/indexed-substitution.md.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from symq.circuit import Circuit, Gate, circuit_from_dict
from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.serialization import parse_json
from symq.hashing import canonical_sha256
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.kmx_source_index import IndexLimits, KmxSourceIndex, QueryLimits, build_kmx_index
from symq.labs.rewrite import DECISIVE, ReceiptMismatch
from symq.labs.rewrite_request import _classical_contract
from symq.resources import Budget, Guard, VerificationSession
from symq.sat.assumptions import And, Const, Eq, Expr, Not, Var, Xor, variables

__all__ = ["CompositionLimits", "check_indexed_substitution", "prove_indexed_substitution",
           "replay_indexed_substitution"]

_PIN = re.compile(r"[0-9a-f]{64}\Z")
_VARIABLE = re.compile(r"([xu])\.(0|[1-9][0-9]*)\Z")
_KIND = "symq_indexed_classical_substitution"


@dataclass(frozen=True)
class CompositionLimits:
    max_request_bytes: int = 2_000_000
    max_replacement_ops: int = 20_000
    max_support_wires: int = 256
    max_predicate_nodes: int = 4096

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


_LIMITS = CompositionLimits()
_QUERY_LIMITS = QueryLimits()
_INDEX_LIMITS = IndexLimits()


def _over(name: str, value: int, bound: int) -> None:
    if value > bound:
        raise ResourceLimitExceeded(name, bound, value)


def _pin(value: Any, name: str) -> None:
    if type(value) is not str or _PIN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _same(actual: Any, expected: Any, guard: Guard) -> bool:
    guard.check_time()
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(
            _same(actual[k], v, guard) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _same(a, b, guard) for a, b in zip(actual, expected))
    return bool(actual == expected)


def _expression(expr: Expr | None, prefix: str, width: int,
                guard: Guard, limits: CompositionLimits) -> set[int]:
    if expr is None:
        return set()
    # The existing closed grammar validates every node and the depth bound.
    used = variables(expr)
    pending, count = [expr], 0
    while pending:
        guard.check_time()
        item = pending.pop()
        count += 1
        _over("predicate nodes", count, limits.max_predicate_nodes)
        if isinstance(item, Not):
            pending.append(item.operand)
        elif isinstance(item, (And, Xor, Eq)):
            pending.extend((item.left, item.right))
    wires = set()
    for name in used:
        guard.check_time()
        match = _VARIABLE.fullmatch(name)
        if match is None or match[1] != prefix or not 0 <= int(match[2]) < width:
            raise ValueError(f"expected canonical {prefix}.<global wire> in the source width")
        wires.add(int(match[2]))
    return wires


def _map_expression(expr: Expr | None, mapping: dict[int, int]) -> Expr | None:
    if expr is None or isinstance(expr, Const):
        return expr
    if isinstance(expr, Var):
        prefix, wire = expr.name.split(".")
        return Var(f"{prefix}.{mapping[int(wire)]}")
    if isinstance(expr, Not):
        return Not(_map_expression(expr.operand, mapping))
    return type(expr)(_map_expression(expr.left, mapping), _map_expression(expr.right, mapping))


def _wires(value: Any, width: int, name: str) -> tuple[int, ...]:
    if (type(value) not in (tuple, list) or len(set(value)) != len(value)
            or any(type(q) is not int or not 0 <= q < width for q in value)):
        raise ValueError(f"{name} needs distinct in-range global wires")
    return tuple(value)


def _request(value: Any, source_pin: str, request_pin: str, width: int,
             size: int, guard: Guard, limits: CompositionLimits):
    if type(value) not in (dict, bytes):
        raise TypeError("request must be a JSON object or exact JSON bytes")
    if type(value) is bytes:
        _over("request bytes", len(value), limits.max_request_bytes)
        value = parse_json(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    _over("request bytes", len(raw), limits.max_request_bytes)
    document = parse_json(raw)  # own a snapshot, with no aliases to caller data
    if type(document) is not dict or set(document) != {
        "kind", "schema_version", "source_file_sha256", "prefix_start_op", "op_span",
        "replacement", "replacement_wires", "contract",
    }:
        raise ValueError("indexed request has missing or unknown fields")
    if (document["kind"] != _KIND or type(document["schema_version"]) is not int
            or document["schema_version"] != 1):
        raise ValueError("unsupported indexed request schema")
    if canonical_sha256(document) != request_pin:
        raise ReceiptMismatch("request differs from the consumer's independent pin")
    if document["source_file_sha256"] != source_pin:
        raise ReceiptMismatch("request does not designate the independently pinned source")
    if type(document["prefix_start_op"]) is not int or document["prefix_start_op"] != 0:
        raise UnsupportedOperation("composition requires prefix_start_op=0")
    span = document["op_span"]
    if (type(span) is not list or len(span) != 2 or any(type(i) is not int for i in span)
            or not 0 <= span[0] < span[1] <= size):
        raise ValueError("op_span needs a nonempty global half-open operation interval")
    replacement_doc = document["replacement"]
    if type(replacement_doc) is not dict or type(replacement_doc.get("gates")) is not list:
        raise ValueError("replacement must be a classical circuit")
    _over("replacement operations", len(replacement_doc["gates"]), limits.max_replacement_ops)
    if type(replacement_doc.get("width")) is not int:
        raise ValueError("replacement needs an integer width")
    _over("replacement width", replacement_doc["width"], limits.max_support_wires)
    replacement = circuit_from_dict(replacement_doc)
    replacement.validate()
    if any(g.name not in {"x", "cx", "ccx"} for g in replacement.gates):
        raise UnsupportedOperation("replacement accepts only X/CX/CCX")
    wires = _wires(document["replacement_wires"], width, "replacement_wires")
    if len(wires) != replacement.width:
        raise ValueError("replacement_wires must map every local replacement wire")
    contract = _classical_contract(document["contract"])
    clean = _wires(contract.clean_at_cut, width, "clean_at_cut")
    restored = _wires(contract.restored_at_cut, width, "restored_at_cut")
    initial = set()
    for pair in contract.initial_constants:
        guard.check_time()
        if (len(pair) != 2 or type(pair[0]) is not int or not 0 <= pair[0] < width
                or type(pair[1]) is not int or pair[1] not in (0, 1) or pair[0] in initial):
            raise ValueError("initial constants need unique in-range (wire, 0/1) pairs")
        initial.add(pair[0])
    initial |= _expression(contract.initial_assumption, "x", width, guard, limits)
    observed = set(clean) | _expression(contract.cut_assumption, "u", width, guard, limits)
    support = initial | observed | set(restored) | set(wires)
    _over("common support wires", len(support), limits.max_support_wires)
    guard.check_time()
    return document, replacement, wires, contract, initial, observed, support


def _dependencies(guard: Guard) -> dict:
    """Conservatively pin installed Python sources and the actual SAT binaries."""
    root = Path(__file__).resolve().parents[1]
    hashes = {}
    for path in sorted(root.rglob("*.py")):
        guard.check_time()
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    solver = {}
    for name in ("pysat.solvers", "pysolvers"):
        try:
            spec = importlib.util.find_spec(name)
        except ModuleNotFoundError:
            spec = None
        if spec is not None and spec.origin:
            guard.check_time()
            solver[name] = hashlib.sha256(Path(spec.origin).read_bytes()).hexdigest()
    try:
        version = importlib.metadata.version("python-sat")
    except importlib.metadata.PackageNotFoundError:
        version = None
    guard.check_time()
    return {"symq_python_sources": hashes, "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "sqlite": sqlite3.sqlite_version, "python_sat": version, "sat_files": solver}


def _base_report(source_pin: str, request_pin: str) -> dict:
    return {"kind": _KIND, "schema_version": 1, "source_file_sha256": source_pin,
            "request_sha256": request_pin, "status": "inconclusive", "reason": "",
            "theorem": "classical_full_source_under_declared_initial_domain",
            "applicable_plan": None, "complete_candidate": None,
            "global_cost": None, "independent_certificate": False}


def _check(index, request, source_pin, request_pin, limits, query_limits, session):
    meta = index.metadata()
    if meta["source_file_sha256"] != source_pin:
        raise ReceiptMismatch("index differs from the consumer's independent source pin")
    doc, replacement, rwires, contract, initial, observed, support = _request(
        request, source_pin, request_pin, meta["global_width"], meta["source_ops"], session, limits)
    start, stop = doc["op_span"]
    query = {"expected_source_sha256": source_pin, "limits": query_limits,
             "budget": session.remaining_budget()}
    window = index.window(start_op=start, stop_op=stop, **query)
    block = index.verify_window(window, start_op=start, stop_op=stop, **query)
    # A constant Q needs no observed variable; use one harmless extra observation
    # so even that case uses the existing nonempty-observation cone grammar.
    outputs = tuple(sorted(observed)) or (window["global_wires"][0],)
    cone = index.cone(start_op=0, stop_op=start, observed_wires=outputs, **query)
    prefix = index.verify_cone(cone, start_op=0, stop_op=start, observed_wires=outputs, **query)
    support |= set(window["global_wires"]) | set(cone["global_wires"])
    _over("common support wires", len(support), limits.max_support_wires)
    global_wires = sorted(support)
    mapping = {q: i for i, q in enumerate(global_wires)}

    def remap(circuit, wires):
        gates = []
        for gate in circuit.gates:
            session.check_time()
            gates.append(Gate(gate.name, tuple(mapping[wires[q]] for q in gate.qubits)))
        return gates

    c = remap(prefix, cone["global_wires"])
    b = remap(block, window["global_wires"])
    r = Circuit(len(mapping), remap(replacement, rwires))
    reduced = Circuit(len(mapping), c + b)
    local_contract = SubstitutionContract(
        tuple((mapping[q], bit) for q, bit in contract.initial_constants),
        tuple(mapping[q] for q in contract.clean_at_cut),
        tuple(mapping[q] for q in contract.restored_at_cut),
        _map_expression(contract.cut_assumption, mapping),
        _map_expression(contract.initial_assumption, mapping))
    local_contract.validate(len(mapping))
    dependencies = _dependencies(session)
    proof = check_substitution(reduced, (len(c), len(c) + len(b)), r,
                               contract=local_contract, budget=session.remaining_budget())
    session.check_time()
    report = _base_report(source_pin, request_pin)
    report.update({"request": doc, "source": meta, "dependencies": dependencies,
                   "dependencies_sha256": canonical_sha256(dependencies),
                   "limits": {"composition": asdict(limits), "query": asdict(query_limits)},
                   "extractions": {"window": window, "origin_cone": cone},
                   "support": {"local_to_global": global_wires,
                               "initial_domain_wires": sorted(initial),
                               "identity_domain_inputs_outside_cone": sorted(
                                   initial - set(cone["global_wires"])),
                               "observed_cut_wires": list(outputs),
                               "required_cut_wires": sorted(observed)},
                   "reduced": {"scope": "origin_cone_then_complete_window_only",
                               "source": reduced.to_dict(), "replacement": r.to_dict(),
                               "local_span": [len(c), len(c) + len(b)],
                               "contract": local_contract.document(),
                               "proof": proof.to_dict(),
                               "cost_scope": "reduced_program_only_not_global"},
                   "composition": {"extraction": "recomputed_exact_selected_output_closure",
                                   "supplied_initial_domain": doc["contract"],
                                   "conditions_used": local_contract.document(),
                                   "proved_facts": [o.name for o in proof.obligations
                                                    if o.status == "passed"],
                                   "external_preparation_proved": False,
                                   "global_counterexample": None,
                                   "witness_scope": "reduced_obligation_only"},
                   "status": proof.outcome, "reason": proof.reason})
    if proof.equivalent:
        report["applicable_plan"] = {
            "source_file_sha256": source_pin, "request_sha256": request_pin,
            "dependencies_sha256": report["dependencies_sha256"],
            "global_op_span": [start, stop], "replacement": replacement.to_dict(),
            "replacement_wires": list(rwires),
            "scope": "replace_complete_window_in_pinned_source_under_declared_domain",
            "resource_scope": "existing_wires_classical_restoration_only_no_allocator"}
    session.check_time()
    return report


def _run(function, source_pin, request_pin, budget):
    _pin(source_pin, "expected_source_sha256")
    _pin(request_pin, "expected_request_sha256")
    budget = Budget(max_seconds=30) if budget is None else budget
    if type(budget) is not Budget:
        raise TypeError("budget must be Budget or None")
    if any(getattr(budget, k) is not None for k in ("max_terms", "max_nodes", "max_bytes")):
        raise ValueError("indexed composition uses time and explicit index/query/composition limits")
    try:
        with VerificationSession(budget) as session:
            return function(session)
    except (ResourceLimitExceeded, UnsupportedOperation) as error:
        report = _base_report(source_pin, request_pin)
        report.update(status="unsupported" if isinstance(error, UnsupportedOperation)
                      else "inconclusive", reason=str(error))
        return report


def check_indexed_substitution(index: KmxSourceIndex, request: dict | bytes, *,
                               expected_source_sha256: str, expected_request_sha256: str,
                               limits: CompositionLimits = _LIMITS,
                               query_limits: QueryLimits = _QUERY_LIMITS,
                               budget: Budget | None = None) -> dict:
    """Reuse an owned index, verify both extractions, and issue a conditional plan."""
    from symq.labs.kmb_source_index import KmbSourceIndex

    if type(index) not in (KmxSourceIndex, KmbSourceIndex):
        raise TypeError("a builder-issued strict classical source index is required")
    if type(limits) is not CompositionLimits or type(query_limits) is not QueryLimits:
        raise TypeError("explicit composition/query limit types are required")
    limits.__post_init__()
    query_limits.__post_init__()
    return _run(lambda s: _check(index, request, expected_source_sha256,
                                expected_request_sha256, limits, query_limits, s),
                expected_source_sha256, expected_request_sha256, budget)


def prove_indexed_substitution(path: str | Path, request: dict | bytes, *,
                               expected_source_sha256: str, expected_request_sha256: str,
                               index_limits: IndexLimits = _INDEX_LIMITS,
                               limits: CompositionLimits = _LIMITS,
                               query_limits: QueryLimits = _QUERY_LIMITS,
                               budget: Budget | None = None) -> dict:
    """Build from the complete source and share one deadline through cleanup."""
    def run(session):
        from symq.labs.kmb_source_index import build_kmb_index

        builder = build_kmb_index if Path(path).suffix.lower() == ".kmb" else build_kmx_index
        with builder(path, expected_source_sha256=expected_source_sha256,
                     limits=index_limits, budget=session.remaining_budget()) as index:
            return check_indexed_substitution(
                index, request, expected_source_sha256=expected_source_sha256,
                expected_request_sha256=expected_request_sha256, limits=limits,
                query_limits=query_limits, budget=session.remaining_budget())
    return _run(run, expected_source_sha256, expected_request_sha256, budget)


def replay_indexed_substitution(path: str | Path, request: dict | bytes, receipt: dict, *,
                                expected_source_sha256: str, expected_request_sha256: str,
                                index_limits: IndexLimits = _INDEX_LIMITS,
                                limits: CompositionLimits = _LIMITS,
                                query_limits: QueryLimits = _QUERY_LIMITS,
                                budget: Budget | None = None) -> dict:
    """Rebuild the index and every obligation; saved handles/verdicts have no authority.

    A decisive replay must reproduce the whole closed receipt, including the
    dependency identities. A resource/unavailable replay never returns a plan.
    """
    def run(session):
        if type(receipt) is not dict:
            raise TypeError("receipt must be a JSON object")
        fresh = prove_indexed_substitution(
            path, request, expected_source_sha256=expected_source_sha256,
            expected_request_sha256=expected_request_sha256, index_limits=index_limits,
            limits=limits, query_limits=query_limits, budget=session.remaining_budget())
        if fresh["status"] in DECISIVE and not _same(receipt, fresh, session):
            raise ReceiptMismatch("composition receipt differs from freshly rebuilt proof")
        session.check_time()
        return fresh
    return _run(run, expected_source_sha256, expected_request_sha256, budget)
