"""Declarative, pinned classical rewrite bricks; every use proves its actual site.

A brick packages two local circuits, cut obligations and reproducible examples.
It contains no executable callbacks, proof tokens or cached PASS decision. A
consumer supplies the intended brick/source pins and the site's initial domain;
the existing preparer and contextual checker run afresh. Saved output is ordinary
untrusted data, not an authorization for another source or site.

Only phase-free X/CX/CCX/MCX circuits are supported. This module makes the existing
classical basis-state claim, not a coherent/HMR/instrument or economic claim.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from symq.circuit import Circuit, circuit_from_dict
from symq.experimental.domains import expression_from_dict
from symq.experimental.serialization import parse_json
from symq.labs.classical_transcript import Program, digest
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite import Weights, call_budget
from symq.labs.rewrite_locator import locate_exact
from symq.labs.rewrite_prepare import prepare_local_classical
from symq.labs.rewrite_request import run_request
from symq.resources import Budget, Guard, ResourceLimitExceeded
from symq.sat.assumptions import And, Const, Eq, Expr, Not, Var, Xor

__all__ = ["ClassicalRewriteBrick", "check_brick_examples", "load_classical_brick",
           "run_classical_brick"]

_KIND = "symq_classical_rewrite_brick"
_PIN = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
MAX_BRICK_BYTES = 2_000_000
MAX_SOURCE_GATES = 100_000
MAX_SOURCE_WIDTH = 4096
MAX_LOCAL_WIDTH = 256
MAX_EXAMPLES = 32


def _keys(value: Any, expected: set[str], name: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{name} requires exactly {sorted(expected)}")
    return value


def _text(value: Any, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise ValueError(f"{name} must be a nonempty plain string of at most 4096 characters")
    return value


def _pin(value: Any, name: str) -> str:
    if type(value) is not str or _PIN.fullmatch(value) is None:
        raise ValueError(f"{name} must be an independently chosen lowercase SHA-256")
    return value


def _circuit(value: Any, name: str, *, local: bool = False) -> Circuit:
    if type(value) is not dict or type(value.get("gates")) is not list:
        raise ValueError(f"{name} must be an explicit classical circuit")
    if len(value["gates"]) > MAX_SOURCE_GATES:
        raise ValueError(f"{name} exceeds the {MAX_SOURCE_GATES}-gate bound")
    width = value.get("width")
    if type(width) is not int or not 1 <= width <= MAX_LOCAL_WIDTH:
        raise ValueError(f"{name} width must be in 1..{MAX_LOCAL_WIDTH}")
    result = circuit_from_dict(value)
    if local and not result.gates:
        raise ValueError("a brick pattern must identify a nonempty interval")
    return result


def _cut_contract(value: Any, width: int) -> SubstitutionContract:
    doc = _keys(value, {"clean_at_cut", "restored_at_cut", "cut_assumption"}, "cut contract")
    for name in ("clean_at_cut", "restored_at_cut"):
        if type(doc[name]) is not list or any(type(q) is not int for q in doc[name]):
            raise ValueError(f"{name} must contain plain integer local wires")
    assumption = doc["cut_assumption"]
    result = SubstitutionContract(
        clean_at_cut=tuple(doc["clean_at_cut"]),
        restored_at_cut=tuple(doc["restored_at_cut"]),
        cut_assumption=None if assumption is None else expression_from_dict(assumption),
    )
    result.validate(width)
    return result


def _constants(value: Any, width: int) -> tuple[tuple[int, int], ...]:
    if type(value) is not list or any(type(pair) is not list or len(pair) != 2 for pair in value):
        raise ValueError("example initial_constants must be [[global wire, bit], ...]")
    constants = tuple(tuple(pair) for pair in value)
    SubstitutionContract(initial_constants=constants).validate(width)
    return constants


def _validate_document(value: Any) -> dict:
    doc = _keys(value, {"schema_version", "kind", "name", "theorem", "phase_policy",
                        "classical_mapping", "pattern", "replacement", "cut_contract",
                        "sources", "examples"}, "rewrite brick")
    if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("unsupported brick schema_version")
    if doc["kind"] != _KIND or doc["theorem"] != "classical":
        raise ValueError("only classical rewrite bricks are supported")
    if doc["phase_policy"] != "phase_free_only" or doc["classical_mapping"] != []:
        raise ValueError("phase/HMR/measurement and classical-slot mappings are unsupported")
    _text(doc["name"], "brick name")
    pattern = _circuit(doc["pattern"], "pattern", local=True)
    replacement = _circuit(doc["replacement"], "replacement")
    if pattern.width != replacement.width:
        raise ValueError("pattern and replacement must have the same local width")
    touched = {q for gate in pattern.gates for q in gate.qubits}
    if touched != set(range(pattern.width)):
        raise ValueError("the pattern must mention every local wire; no ancilla mapping is guessed")
    _cut_contract(doc["cut_contract"], pattern.width)
    sources = doc["sources"]
    if type(sources) is not list or not 1 <= len(sources) <= MAX_EXAMPLES:
        raise ValueError("a brick needs explicit source and license records")
    for source in sources:
        _keys(source, {"origin", "source_url", "source_revision", "license", "license_url"},
              "source/license record")
        if source["origin"] not in ("authored", "adapted"):
            raise ValueError("source origin must be authored or adapted")
        for field in ("source_url", "license", "license_url"):
            _text(source[field], field)
        if source["origin"] == "adapted" or source["source_revision"] is not None:
            revision = _text(source["source_revision"], "source_revision")
            if _REVISION.fullmatch(revision) is None:
                raise ValueError("source_revision must pin a lowercase 40/64-digit content identity")
    cases = doc["examples"]
    if type(cases) is not list or not 2 <= len(cases) <= MAX_EXAMPLES:
        raise ValueError(f"a brick needs 2..{MAX_EXAMPLES} positive/mutant examples")
    names, kinds = set(), set()
    negative_mutant = False
    for case in cases:
        _keys(case, {"name", "kind", "source", "initial_constants", "replacement",
                     "expected_outcome"}, "brick example")
        name = _text(case["name"], "example name")
        if name in names:
            raise ValueError("example names must be unique")
        names.add(name)
        kind, expected = case["kind"], case["expected_outcome"]
        if kind not in ("positive", "mutant"):
            raise ValueError("example kind must be positive or mutant")
        kinds.add(kind)
        if (kind == "positive" and (expected != "equivalent" or case["replacement"] is not None)
                or kind == "mutant" and expected not in (
                    "equivalent", "precondition_failed", "not_proved")):
            raise ValueError("examples need decisive expectations, never a stored PASS authority")
        negative_mutant |= kind == "mutant" and expected in ("precondition_failed", "not_proved")
        source = _circuit(case["source"], "example source")
        if source.width < pattern.width:
            raise ValueError("example source is narrower than the local pattern")
        _constants(case["initial_constants"], source.width)
        if case["replacement"] is not None:
            mutant = _circuit(case["replacement"], "mutant replacement")
            if mutant.width != pattern.width:
                raise ValueError("mutant replacement has a different local width")
    if kinds != {"positive", "mutant"}:
        raise ValueError("both positive and mutant examples are required")
    if not negative_mutant:
        raise ValueError("at least one mutant needs a decisive negative expectation")
    return doc


@dataclass(frozen=True)
class ClassicalRewriteBrick:
    """Immutable source bytes, not a proof token. Every use revalidates them."""

    data: bytes
    sha256: str

    def to_dict(self) -> dict:
        return _validate_document(parse_json(self.data))


def load_classical_brick(data: bytes, *, expected_sha256: str) -> ClassicalRewriteBrick:
    """Read a closed declarative document against the consumer's exact byte pin.

    Whitespace is part of this file identity. Source URLs/license declarations
    are metadata, not authenticated legal clearance or mathematical authority.
    Nothing is imported, executed, proved or fetched while loading a brick.
    """
    _pin(expected_sha256, "expected_sha256")
    if type(data) is not bytes:
        raise TypeError("brick data must be immutable bytes")
    if len(data) > MAX_BRICK_BYTES:
        raise ValueError(f"brick exceeds {MAX_BRICK_BYTES} bytes")
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise ValueError("brick SHA-256 does not match the consumer pin")
    try:
        _validate_document(parse_json(data))
    except RecursionError as error:
        raise ValueError("brick nesting exceeds the parser's supported depth") from error
    return ClassicalRewriteBrick(data, actual)


def _document(brick: ClassicalRewriteBrick, expected: str) -> dict:
    if type(brick) is not ClassicalRewriteBrick:
        raise TypeError("a ClassicalRewriteBrick is required")
    fresh = load_classical_brick(brick.data, expected_sha256=expected)
    if brick.sha256 != fresh.sha256:
        raise ValueError("brick object has a stale or altered identity")
    return fresh.to_dict()


def _map_expression(expression: Expr | None, wires: tuple[int, ...]) -> Expr | None:
    if expression is None or type(expression) is Const:
        return expression
    if type(expression) is Var:
        # The local closed grammar and variable names were already validated.
        return Var(f"u.{wires[int(expression.name[2:])]}")
    if type(expression) is Not:
        return Not(_map_expression(expression.operand, wires))
    if type(expression) not in (And, Xor, Eq):
        raise ValueError("unsupported local cut expression")
    return type(expression)(_map_expression(expression.left, wires),
                            _map_expression(expression.right, wires))


def _run(brick: ClassicalRewriteBrick, source: Circuit, *, expected_brick_sha256: str,
         expected_source_sha256: str, initial_constants: tuple[tuple[int, int], ...],
         budget: Budget | None, weights: Weights | None,
         mutant_replacement: dict | None = None) -> dict:
    guard = Guard(call_budget(budget))
    if any(getattr(guard.budget, key) is not None for key in ("max_terms", "max_nodes", "max_bytes")):
        raise ValueError("classical brick proof supports cooperative time, not term/node/byte budgets")
    _pin(expected_brick_sha256, "expected_brick_sha256")
    _pin(expected_source_sha256, "expected_source_sha256")
    result = {"schema_version": 1, "kind": "symq_classical_brick_run",
              "expected_brick_sha256": expected_brick_sha256,
              "expected_source_sha256": expected_source_sha256,
              "status": "inconclusive", "preparation": None, "proof_report": None,
              "quantum_mapping": None, "classical_mapping": [],
              "saved_result_is_authority": False}
    try:
        guard.check_time()
        doc = _document(brick, expected_brick_sha256)
        if type(source) is not Circuit or type(source.gates) is not list:
            raise TypeError("source must be a classical Circuit")
        if type(source.width) is not int or source.width < 1:
            raise ValueError("source width must be a positive plain integer")
        if source.width > MAX_SOURCE_WIDTH:
            raise ResourceLimitExceeded("source width", MAX_SOURCE_WIDTH, source.width)
        if len(source.gates) > MAX_SOURCE_GATES:
            raise ResourceLimitExceeded("source gates", MAX_SOURCE_GATES, len(source.gates))
        frozen = source.snapshot(check=guard.check_time)
        if digest(Program.freeze(frozen)) != expected_source_sha256:
            raise ValueError("source SHA-256 does not match the consumer pin")
        local = _cut_contract(doc["cut_contract"], doc["pattern"]["width"])
        pattern = circuit_from_dict(doc["pattern"])
        candidate = circuit_from_dict(doc["replacement"] if mutant_replacement is None
                                      else mutant_replacement)
        SubstitutionContract(initial_constants=initial_constants).validate(frozen.width)
        guard.check_time()
        location = locate_exact(frozen, pattern)
        if location["status"] != "unique":
            guard.check_time()
            result.update(status=location["status"], location=location)
            return result
        match = location["matches"][0]
        wires = tuple(match["wires"])
        if (len(wires) != pattern.width or len(set(wires)) != len(wires)
                or any(type(q) is not int or not 0 <= q < frozen.width for q in wires)):
            raise ValueError("the brick needs a complete injective local-to-global mapping")
        contract = SubstitutionContract(
            initial_constants=tuple(sorted(initial_constants)),
            clean_at_cut=tuple(sorted(wires[q] for q in local.clean_at_cut)),
            restored_at_cut=tuple(sorted(wires[q] for q in local.restored_at_cut)),
            cut_assumption=_map_expression(local.cut_assumption, wires),
        )
        guard.check_time()
        prepared = prepare_local_classical(frozen, pattern, candidate, contract=contract,
                                           weights=weights, engine="sat")
        if (not prepared.ready or prepared.request.span != tuple(match["span"])
                or prepared.location["matches"][0]["wires"] != list(wires)):
            raise ValueError("the fresh preparer did not reproduce the selected site")
        guard.check_time()
        report = run_request(prepared.request, guard.inherited_budget())
        guard.check_time()
        result.update(status=report["result"]["outcome"], preparation=prepared.to_dict(),
                      proof_report=report, quantum_mapping=list(wires))
        return result
    except ResourceLimitExceeded as error:
        # Do not expose even a positive inner report if the whole-call deadline expired.
        result.update(status="inconclusive", reason=str(error), proof_report=None)
        return result


def run_classical_brick(brick: ClassicalRewriteBrick, source: Circuit, *,
                        expected_brick_sha256: str, expected_source_sha256: str,
                        initial_constants: tuple[tuple[int, int], ...],
                        budget: Budget | None = None, weights: Weights | None = None) -> dict:
    """Locate, prepare and prove one actual site with an explicit global input domain.

    No certificate or previous example result is an accepted argument. Unmentioned
    input wires are arbitrary. The brick contributes only local cut/restoration
    requirements; the actual source must establish them at this invocation.
    Multiple matches or unmapped wires never select a candidate. The returned
    embedded report uses the existing fresh-replay contract of `symq rewrite`.
    """
    return _run(brick, source, expected_brick_sha256=expected_brick_sha256,
                expected_source_sha256=expected_source_sha256,
                initial_constants=initial_constants, budget=budget, weights=weights)


def check_brick_examples(brick: ClassicalRewriteBrick, *, expected_brick_sha256: str,
                         budget: Budget | None = None) -> dict:
    """Re-execute every declared example; labels and prior runs have no proof authority.

    Matching a negative expectation is a successful regression test, not a proof
    of global circuit inequivalence. No example can authorize another site.
    """
    shared_budget = call_budget(budget)
    guard = Guard(shared_budget)
    rows = []
    try:
        guard.check_time()
        doc = _document(brick, expected_brick_sha256)
        for case in doc["examples"]:
            guard.check_time()
            source = circuit_from_dict(case["source"])
            run = _run(
                brick, source, expected_brick_sha256=expected_brick_sha256,
                expected_source_sha256=digest(Program.freeze(source)),
                initial_constants=_constants(case["initial_constants"], source.width),
                budget=shared_budget, weights=None, mutant_replacement=case["replacement"],
            )
            rows.append({"name": case["name"], "kind": case["kind"],
                         "expected_outcome": case["expected_outcome"],
                         "matches_expected": run["status"] == case["expected_outcome"], "run": run})
        guard.check_time()
    except ResourceLimitExceeded as error:
        return {"schema_version": 1, "kind": "symq_brick_example_checks",
                "brick_sha256": expected_brick_sha256, "examples": rows,
                "status": "inconclusive", "reason": str(error),
                "all_expectations_met": False, "authorizes_other_sites": False}
    return {"schema_version": 1, "kind": "symq_brick_example_checks",
            "brick_sha256": expected_brick_sha256, "examples": rows,
            "status": "completed",
            "all_expectations_met": all(row["matches_expected"] for row in rows),
            "authorizes_other_sites": False}
