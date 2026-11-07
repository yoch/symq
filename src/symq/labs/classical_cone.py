"""Source-pinned backward cones and exact classical cut predicates (research API).

For X/CX/CCX/MCX, a gate is needed iff its target is live in the backwards
slice; its controls then become live. The resulting circuit preserves the
requested output bits for *every* state at the chosen starting cut. Other
local outputs need not agree. An intermediate cut has arbitrary inputs: an
initial constant is never silently moved across the omitted prefix.

This first implementation snapshots an already materialized Circuit. It is
not a streaming file index, a quantum-support theorem, or rewrite permission.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from symq.circuit import Circuit, Gate
from symq.errors import InternalInconsistency, ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.domains import expression_to_dict
from symq.hashing import canonical_sha256
from symq.labs.classical_transcript import Program, digest
from symq.resources import Budget, Guard
from symq.sat._solve import solve_with_deadline
from symq.sat.assumptions import MAX_DEPTH, And, Const, Eq, Expr, Not, Var, Xor, evaluate, tseitin
from symq.sat.encoding import Encoder, _solver_factory, encode_circuit, solver_name

__all__ = [
    "ClassicalCone", "ConeAttempt", "ConeExtraction", "ConeLimits", "ConePredicateResult",
    "extract_classical_cone", "prove_cone_predicate", "replay_cone_predicate",
    "verify_classical_cone",
]

_ISSUED = object()


@dataclass(frozen=True)
class ConeLimits:
    """Allocation/work caps; these are not process RSS or hard wall-clock limits."""

    max_source_gates: int = 200_000
    max_source_width: int = 100_000
    max_cone_gates: int = 20_000
    max_cone_width: int = 256
    max_scanned_gates: int = 1_000_000
    max_attempts: int = 16
    max_predicate_nodes: int = 4096
    max_clauses: int = 250_000
    max_variables: int = 100_000

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


_DEFAULT_LIMITS = ConeLimits()


@dataclass(frozen=True)
class ClassicalCone:
    source_sha256: str
    source_width: int
    source_gate_count: int
    span: tuple[int, int]
    observed_wires: tuple[int, ...]
    wires: tuple[int, ...]
    gate_indices: tuple[int, ...]
    program: Program

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_sha256": self.source_sha256, "source_width": self.source_width,
            "source_gate_count": self.source_gate_count, "span": list(self.span),
            "position_basis": "zero_based_circuit_gate_half_open",
            "observed_wires": list(self.observed_wires), "wires": list(self.wires),
            "gate_indices": list(self.gate_indices), "program": self.program.circuit().to_dict(),
            "cone_sha256": digest(self.program), "boundary_inputs": "arbitrary",
            "theorem": "classical_selected_outputs_for_all_boundary_states",
        }


@dataclass(frozen=True)
class ConeExtraction:
    outcome: str
    reason: str
    cone: ClassicalCone | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "kind": "symq_classical_cone", "outcome": self.outcome,
            "reason": self.reason, "cone": None if self.cone is None else self.cone.to_dict(),
            "predicate_proved": False, "candidate_authorized": False,
        }


@dataclass(frozen=True)
class ConeAttempt:
    start_op: int
    outcome: str
    cone_sha256: str
    wires: tuple[int, ...]
    selected_gates: int
    local_input: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_op": self.start_op, "outcome": self.outcome,
            "cone_sha256": self.cone_sha256, "wires": list(self.wires),
            "selected_gates": self.selected_gates, "local_input": self.local_input,
            "witness_kind": None if self.local_input is None else
                ("projected_source_input" if self.start_op == 0 else "arbitrary_cut_input"),
        }


@dataclass(frozen=True)
class ConePredicateResult:
    outcome: str
    reason: str
    source_sha256: str
    at: int
    initial_constants: tuple[tuple[int, int], ...]
    predicate: Expr | None
    initial_start: int
    expand_cut: bool
    attempts: tuple[ConeAttempt, ...] = ()
    cone: ClassicalCone | None = None
    counterexample_input: int | None = None
    engine: str = "unavailable"
    _seal: Any = field(default=None, repr=False, compare=False)

    def _claim(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome, "source_sha256": self.source_sha256, "at": self.at,
            "initial_constants": [list(p) for p in self.initial_constants],
            "predicate": (None if self.predicate is None else expression_to_dict(self.predicate)),
            "initial_start": self.initial_start,
            "expand_cut": self.expand_cut, "attempts": [a.to_dict() for a in self.attempts],
            "cone": None if self.cone is None else self.cone.to_dict(),
            "counterexample_input": self.counterexample_input,
        }

    @property
    def proved(self) -> bool:
        return (self.outcome == "proved" and type(self._seal) is tuple
                and len(self._seal) == 2 and self._seal[0] is _ISSUED
                and self._seal[1] == canonical_sha256(self._claim()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "kind": "symq_cone_predicate", **self._claim(),
            "reason": self.reason, "engine": self.engine,
            "theorem": "classical_source_cut_predicate", "candidate_authorized": False,
            "proof_format": "structural_cone_and_fresh_sat_replay",
        }

    def cut_assumption(self, source: Circuit, *, at: int) -> Expr:
        """Supply a proved predicate to the existing substitution checker.

        Carry ``initial_constants`` into its SubstitutionContract. That checker
        still proves its own prefix, local equivalence and restoration obligations.
        """
        if not self.proved or type(at) is not int or at != self.at:
            raise ValueError("a freshly proved predicate at this exact position is required")
        if type(source) is not Circuit:
            raise TypeError("source must be a Circuit")
        if digest(Program.freeze(source.snapshot())) != self.source_sha256:
            raise ValueError("source differs from the proved source")
        assert self.predicate is not None
        return self.predicate


class _Stopped(Exception):
    pass


def _guard(budget: Budget | None, limits: ConeLimits) -> Guard:
    if type(limits) is not ConeLimits:
        raise TypeError("limits must be ConeLimits")
    limits.__post_init__()
    guard = Guard(Budget(max_seconds=30) if budget is None else budget)
    if any(getattr(guard.budget, name) is not None
           for name in ("max_terms", "max_nodes", "max_bytes")):
        raise ValueError("cones use time budgets and explicit ConeLimits, not symbolic budgets")
    return guard


def _snapshot(source: Circuit, expected: str, guard: Guard, limits: ConeLimits) -> Program:
    guard.check_time()
    if (type(expected) is not str or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)):
        raise ValueError("expected_source_sha256 must be an independently supplied SHA-256")
    if type(source) is not Circuit or type(source.gates) is not list:
        raise TypeError("source must be a materialized Circuit with an actual gate list")
    if type(source.width) is not int or source.width < 1:
        raise ValueError("source width must be a positive integer")
    if source.width > limits.max_source_width:
        raise _Stopped("materialized source width cap exceeded")
    if len(source.gates) > limits.max_source_gates:
        raise _Stopped("materialized source gate cap exceeded")
    frozen = Program.freeze(source.snapshot(check=guard.check_time))
    guard.check_time()
    if digest(frozen) != expected:
        raise ValueError("source SHA-256 does not match the independently supplied pin")
    guard.check_time()
    return frozen


def _span(start: int, at: int, size: int) -> None:
    if type(start) is not int or type(at) is not int or not 0 <= start <= at <= size:
        raise ValueError("require integer positions 0 <= start_op <= at <= source gate count")


def _wires(wires: tuple[int, ...], width: int) -> tuple[int, ...]:
    if (type(wires) is not tuple or not wires
            or len(wires) > width
            or any(type(q) is not int or not 0 <= q < width for q in wires)
            or len(set(wires)) != len(wires)):
        raise ValueError("observed_wires must be a nonempty tuple of distinct in-range wires")
    return tuple(sorted(wires))


def _slice(source: Program, source_sha256: str, start: int, at: int,
           observed: tuple[int, ...], guard: Guard, limits: ConeLimits) -> ClassicalCone:
    live = set(observed)
    if len(live) > limits.max_cone_width:
        raise _Stopped("cone width cap exceeded")
    selected = []
    for index in range(at - 1, start - 1, -1):
        guard.check_time()
        gate = source.gates[index]
        if gate.target in live:
            if len(selected) >= limits.max_cone_gates:
                raise _Stopped("cone gate cap exceeded")
            selected.append(index)
            for q in gate.controls:
                live.add(q)
                if len(live) > limits.max_cone_width:
                    raise _Stopped("cone width cap exceeded")
    wires = tuple(sorted(live))
    mapping = {wire: local for local, wire in enumerate(wires)}
    selected.reverse()
    gates = []
    for index in selected:
        guard.check_time()
        gate = source.gates[index]
        gates.append(Gate(gate.name, tuple(mapping[q] for q in gate.qubits)))
    local = Program(len(wires), tuple(gates))
    guard.check_time()
    return ClassicalCone(source_sha256, source.width, len(source.gates), (start, at),
                         observed, wires, tuple(selected), local)


def extract_classical_cone(
    source: Circuit, *, at: int, observed_wires: tuple[int, ...],
    expected_source_sha256: str, start_op: int = 0, limits: ConeLimits = _DEFAULT_LIMITS,
    budget: Budget | None = None,
) -> ConeExtraction:
    """Return the exact backwards slice on selected outputs, with explicit source pins.

    Success does not prove any predicate or any cut-state preparation. Every
    boundary bit is arbitrary. Unsupported gates are refused even outside the
    selected interval; this function accepts the classical Circuit grammar only.
    """
    guard = _guard(budget, limits)
    try:
        frozen = _snapshot(source, expected_source_sha256, guard, limits)
        _span(start_op, at, len(frozen.gates))
        observed = _wires(observed_wires, frozen.width)
        if at - start_op > limits.max_scanned_gates:
            raise _Stopped("backward scan work cap exceeded")
        cone = _slice(frozen, expected_source_sha256, start_op, at, observed, guard, limits)
        guard.check_time()
        return ConeExtraction("extracted", "selected outputs preserved for every boundary input", cone)
    except (_Stopped, ResourceLimitExceeded) as error:
        return ConeExtraction("inconclusive", str(error))
    except UnsupportedOperation as error:
        return ConeExtraction("unsupported", str(error))


def _same(value: Any, expected: Any, guard: Guard) -> bool:
    """Strict scalar types, bounded by the expected document, including bool/int."""
    guard.check_time()
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return (value.keys() == expected.keys()
                and all(_same(value[k], v, guard) for k, v in expected.items()))
    if type(expected) is list:
        return len(value) == len(expected) and all(
            _same(a, b, guard) for a, b in zip(value, expected))
    return bool(value == expected)


def verify_classical_cone(
    source: Circuit, receipt: dict[str, Any], *, at: int, observed_wires: tuple[int, ...],
    expected_source_sha256: str, start_op: int = 0, limits: ConeLimits = _DEFAULT_LIMITS,
    budget: Budget | None = None,
) -> ConeExtraction:
    """Rebuild the closure from a separately pinned source and compare every field."""
    guard = _guard(budget, limits)
    try:
        fresh = extract_classical_cone(
            source, at=at, observed_wires=observed_wires, start_op=start_op,
            expected_source_sha256=expected_source_sha256, limits=limits,
            budget=guard.inherited_budget(),
        )
        if fresh.outcome != "extracted":
            return fresh
        if not _same(receipt, fresh.to_dict(), guard):
            raise ValueError("cone receipt differs from the source, position, closure or mapping")
        return fresh
    except (_Stopped, ResourceLimitExceeded) as error:
        return ConeExtraction("inconclusive", str(error))


def _predicate(expression: Expr, width: int, guard: Guard, limits: ConeLimits
               ) -> tuple[Expr, tuple[int, ...]]:
    count = 0
    used: set[int] = set()

    def copy(node: Expr, depth: int = 1) -> Expr:
        nonlocal count
        guard.check_time()
        count += 1
        if count > limits.max_predicate_nodes:
            raise _Stopped("predicate node cap exceeded")
        if depth > MAX_DEPTH:
            raise ValueError("predicate exceeds the Boolean grammar depth bound")
        if type(node) is Const:
            return Const(node.value)
        if type(node) is Var:
            name = node.name
            if type(name) is not str or not name.startswith("u.") or not name[2:].isascii():
                raise ValueError("predicate variables must be canonical u.<global wire> names")
            suffix = name[2:]
            if (not suffix.isdecimal() or len(suffix) > len(str(width))
                    or str(int(suffix)) != suffix or not 0 <= int(suffix) < width):
                raise ValueError("predicate wire is malformed or outside the source width")
            used.add(int(suffix))
            return Var(name)
        if type(node) is Not:
            return Not(copy(node.operand, depth + 1))
        if type(node) in (And, Xor, Eq):
            return type(node)(copy(node.left, depth + 1), copy(node.right, depth + 1))
        raise TypeError("predicate must use the closed Boolean expression grammar")

    frozen = copy(expression)
    if not used:
        raise ValueError("a cone predicate must reference at least one source wire")
    return frozen, tuple(sorted(used))


def _constants(value: tuple[tuple[int, int], ...], width: int,
               guard: Guard) -> tuple[tuple[int, int], ...]:
    if type(value) is not tuple:
        raise TypeError("initial_constants must be a tuple of pairs")
    if len(value) > width:
        raise ValueError("too many initial constants for the source width")
    seen: set[int] = set()
    for pair in value:
        guard.check_time()
        if (type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not int or not 0 <= pair[0] < width
                or type(pair[1]) is not int or pair[1] not in (0, 1) or pair[0] in seen):
            raise ValueError("initial constants need unique in-range (wire, 0/1) pairs")
        seen.add(pair[0])
    return tuple(sorted(value))


class _Encoder(Encoder):
    def __init__(self, guard: Guard, limits: ConeLimits) -> None:
        super().__init__()
        self.guard, self.limits = guard, limits

    def new(self) -> int:
        self.guard.check_time()
        if self.next_variable > self.limits.max_variables:
            raise _Stopped("SAT variable cap exceeded")
        return super().new()

    def add(self, *literals: int) -> None:
        self.guard.check_time()
        if len(self.clauses) >= self.limits.max_clauses:
            raise _Stopped("SAT clause cap exceeded")
        super().add(*literals)


def _violates(cone: ClassicalCone, predicate: Expr, value: int, guard: Guard) -> bool:
    state = cone.program.circuit().run(value, check=guard.check_time)
    assignment = {f"u.{wire}": (state >> local) & 1
                  for local, wire in enumerate(cone.wires)}
    return not evaluate(predicate, assignment)


def _query(cone: ClassicalCone, predicate: Expr, constants: tuple[tuple[int, int], ...],
           factory: Any, guard: Guard, limits: ConeLimits) -> int | None:
    encoder = _Encoder(guard, limits)
    steps = encode_circuit(encoder, cone.program.circuit(), checkpoint=guard.check_time)
    local = {q: i for i, q in enumerate(cone.wires)}
    # Original-input assumptions apply ONLY at the actual source origin.
    used_constants = constants if cone.span[0] == 0 else ()
    for q, bit in used_constants:
        guard.check_time()
        if q in local:
            literal = steps.inputs[local[q]]
            encoder.add(literal if bit else -literal)
    encoder.add(-tseitin(predicate, encoder, lambda name: steps.outputs[local[int(name[2:])]]))
    guard.check_time()
    solver = factory(bootstrap_with=encoder.clauses)
    try:
        guard.check_time()
        answer, timed_out = solve_with_deadline(solver, guard.deadline)
        if timed_out or answer is None:
            raise _Stopped("SAT query inconclusive or deadline exhausted")
        if answer is False:
            return None
        if answer is not True:
            raise InternalInconsistency("unexpected SAT answer")
        model = solver.get_model()
        if model is None:
            raise InternalInconsistency("SAT returned no model")
        positive = {literal for literal in model if literal > 0}
        value = sum(1 << q for q, literal in enumerate(steps.inputs) if literal in positive)
        if any(q in local and ((value >> local[q]) & 1) != bit for q, bit in used_constants):
            raise InternalInconsistency("SAT witness violates the initial constants")
        if not _violates(cone, predicate, value, guard):
            raise InternalInconsistency("SAT witness does not violate the cone predicate")
        return value
    finally:
        solver.delete()
        guard.check_time()  # no decisive result after an over-budget cleanup


def prove_cone_predicate(
    source: Circuit, *, at: int, predicate: Expr, expected_source_sha256: str,
    initial_constants: tuple[tuple[int, int], ...] = (), start_op: int = 0,
    expand_cut: bool = True, limits: ConeLimits = _DEFAULT_LIMITS, budget: Budget | None = None,
) -> ConePredicateResult:
    """Prove a known Boolean predicate on the real source at ``at``.

    Start at the requested cut and double the lookback on a local SAT witness.
    An arbitrary-cut witness is only ``not_proved``. At source origin, lift and
    replay it on the full prefix before reporting ``precondition_failed``.
    Distinct constant assignments define a nonempty original-input domain;
    general relational input assumptions are intentionally unsupported here.
    """
    guard = _guard(budget, limits)
    attempts: list[ConeAttempt] = []
    cone = None
    engine = "unavailable"
    frozen_predicate = None
    constants: tuple[tuple[int, int], ...] = ()

    def result(outcome: str, reason: str, witness: int | None = None) -> ConePredicateResult:
        value = ConePredicateResult(outcome, reason, expected_source_sha256, at, constants,
                                    frozen_predicate, start_op, expand_cut, tuple(attempts),
                                    cone, witness, engine)
        if outcome == "proved":
            guard.check_time()
            object.__setattr__(value, "_seal", (_ISSUED, canonical_sha256(value._claim())))
            guard.check_time()
        return value

    try:
        frozen = _snapshot(source, expected_source_sha256, guard, limits)
        _span(start_op, at, len(frozen.gates))
        if type(expand_cut) is not bool:
            raise ValueError("expand_cut must be Boolean")
        constants = _constants(initial_constants, frozen.width, guard)
        frozen_predicate, observed = _predicate(predicate, frozen.width, guard, limits)
        factory = _solver_factory()
        guard.check_time()
        if factory is None:
            return result("unsupported", "no interruptible SAT solver is available")
        engine = solver_name(factory)
        start, scanned = start_op, 0
        while True:
            guard.check_time()
            if len(attempts) >= limits.max_attempts:
                raise _Stopped("cut expansion attempt cap exceeded")
            scanned += at - start
            if scanned > limits.max_scanned_gates:
                raise _Stopped("backward scan work cap exceeded")
            cone = _slice(frozen, expected_source_sha256, start, at, observed, guard, limits)
            witness = _query(cone, frozen_predicate, constants, factory, guard, limits)
            outcome = "proved" if witness is None else "not_proved"
            attempts.append(ConeAttempt(start, outcome, digest(cone.program), cone.wires,
                                        len(cone.program.gates), witness))
            if witness is None:
                return result("proved", "the exact cone proves the predicate at the source position")
            if start == 0:
                value = sum(1 << q for q, bit in constants if bit)
                for local, q in enumerate(cone.wires):
                    value = (value & ~(1 << q)) | (((witness >> local) & 1) << q)
                prefix = Circuit(frozen.width, list(frozen.gates[:at]))
                state = prefix.run(value, check=guard.check_time)
                assignment = {f"u.{q}": (state >> q) & 1 for q in observed}
                if (any(((value >> q) & 1) != bit for q, bit in constants)
                        or evaluate(frozen_predicate, assignment)):
                    raise InternalInconsistency("lifted cone witness does not refute the real prefix")
                guard.check_time()
                return result("precondition_failed", "a legal source input refutes the predicate", value)
            if not expand_cut:
                return result("not_proved", "arbitrary cut witness; reachability is not established")
            start = max(0, at - 2 * max(1, at - start))
    except (_Stopped, ResourceLimitExceeded) as error:
        return result("inconclusive", str(error))
    except UnsupportedOperation as error:
        return result("unsupported", str(error))


def _replay_cone_predicate(
    source: Circuit, receipt: dict[str, Any], *, at: int, predicate: Expr,
    expected_source_sha256: str, initial_constants: tuple[tuple[int, int], ...] = (),
    limits: ConeLimits, guard: Guard,
) -> ConePredicateResult:
    fields = {
        "schema_version", "kind", "outcome", "source_sha256", "at", "initial_constants",
        "predicate", "initial_start", "expand_cut", "attempts", "cone", "counterexample_input",
        "reason", "engine", "theorem", "candidate_authorized", "proof_format",
    }
    if (type(receipt) is not dict or set(receipt) != fields
            or type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
            or receipt["kind"] != "symq_cone_predicate" or receipt["outcome"] != "proved"
            or receipt["candidate_authorized"] is not False
            or receipt["theorem"] != "classical_source_cut_predicate"
            or receipt["proof_format"] != "structural_cone_and_fresh_sat_replay"
            or receipt["counterexample_input"] is not None
            or type(receipt["reason"]) is not str or type(receipt["engine"]) is not str):
        raise ValueError("a version-one positive cone-predicate receipt is required")
    if (type(receipt["attempts"]) is not list or not receipt["attempts"]
            or len(receipt["attempts"]) > limits.max_attempts):
        raise ValueError("receipt has an invalid or over-cap attempt list")
    fresh = prove_cone_predicate(
        source, at=at, predicate=predicate, expected_source_sha256=expected_source_sha256,
        initial_constants=initial_constants, start_op=receipt["initial_start"],
        expand_cut=receipt["expand_cut"], limits=limits, budget=guard.inherited_budget(),
    )
    if fresh.outcome in ("inconclusive", "unsupported"):
        return fresh
    if not fresh.proved:
        raise ValueError("fresh proof contradicts the saved positive result")
    expected = fresh.to_dict()
    for field_name in fields - {"reason", "engine", "attempts"}:
        if not _same(receipt[field_name], expected[field_name], guard):
            raise ValueError(f"cone-predicate receipt {field_name} differs from the pinned task")
    if len(receipt["attempts"]) != len(fresh.attempts):
        raise ValueError("receipt cut expansion history differs from fresh replay")
    for saved, actual in zip(receipt["attempts"], fresh.attempts):
        wanted = actual.to_dict()
        if type(saved) is not dict or saved.keys() != wanted.keys():
            raise ValueError("invalid cone attempt record")
        for field_name in wanted.keys() - {"local_input"}:
            if not _same(saved[field_name], wanted[field_name], guard):
                raise ValueError("receipt cone attempt differs from fresh replay")
        witness = saved["local_input"]
        if actual.local_input is None:
            if witness is not None:
                raise ValueError("a proved cone cannot have a violating witness")
            continue
        if type(witness) is not int or witness < 0 or witness >> len(actual.wires):
            raise ValueError("saved cone witness is outside the local input width")
        rebuilt = extract_classical_cone(
            source, at=at, observed_wires=fresh.cone.observed_wires,  # type: ignore[union-attr]
            expected_source_sha256=expected_source_sha256, start_op=actual.start_op,
            limits=limits, budget=guard.inherited_budget(),
        )
        if rebuilt.outcome != "extracted":
            return ConePredicateResult(
                rebuilt.outcome, rebuilt.reason, expected_source_sha256, at,
                fresh.initial_constants, fresh.predicate, fresh.initial_start, fresh.expand_cut,
            )
        assert rebuilt.cone is not None
        if not _violates(rebuilt.cone, fresh.predicate, witness, guard):
            raise ValueError("saved intermediate cut witness does not violate the predicate")
    guard.check_time()
    return fresh


def replay_cone_predicate(
    source: Circuit, receipt: dict[str, Any], *, at: int, predicate: Expr,
    expected_source_sha256: str, initial_constants: tuple[tuple[int, int], ...] = (),
    limits: ConeLimits = _DEFAULT_LIMITS, budget: Budget | None = None,
) -> ConePredicateResult:
    """Freshly re-prove a positive receipt against independently supplied task pins.

    The saved cut search is replayed. SAT witnesses may differ, so each saved
    intermediate witness is checked concretely rather than compared to a new
    model. Solver label and reason are historical strings. This is not LRAT.
    """
    guard = _guard(budget, limits)
    try:
        return _replay_cone_predicate(
            source, receipt, at=at, predicate=predicate,
            expected_source_sha256=expected_source_sha256,
            initial_constants=initial_constants, limits=limits, guard=guard,
        )
    except (_Stopped, ResourceLimitExceeded) as error:
        return ConePredicateResult("inconclusive", str(error), expected_source_sha256, at,
                                   (), None, 0, False)
