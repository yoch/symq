"""Discover exact Boolean cut invariants in a fixed monomial dictionary.

The prefix is an X/CX/CCX/MCX ``Circuit`` and the input contract is classical.
Samples propose relations; only a fresh UNSAT query certifies their soundness.
Reachable sample rows also certify completeness *within the chosen dictionary*.
This is not a quantum-support analysis or an independently checkable UNSAT proof.

Every successful receipt binds a frozen prefix, input contract and dictionary.
Replaying it re-executes the witnesses and reruns the exact SAT obligation.
It never authorizes a rewrite: ``cut_assumption`` supplies an expression to the
existing substitution checker, which must still prove its own obligations.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from symq.circuit import Circuit, Gate
from symq.errors import InternalInconsistency, ResourceLimitExceeded, SatUnavailable
from symq.experimental.domains import expression_to_dict
from symq.hashing import canonical_sha256
from symq.labs.classical_transcript import Program, digest
from symq.resources import Budget, Guard
from symq.sat._solve import solve_with_deadline
from symq.sat.assumptions import (
    MAX_DEPTH,
    And,
    Const,
    Eq,
    Expr,
    Not,
    Var,
    Xor,
    evaluate,
    tseitin,
    validate,
)
from symq.sat.encoding import Encoder, _solver_factory, solver_name

__all__ = [
    "CutInvariantResult", "InvariantLimits", "discover_cut_invariants",
    "replay_cut_invariants",
]

_KIND = "symq_cut_invariants"
_ISSUED = object()
_RECEIPT_FIELDS = {
    "schema_version", "kind", "outcome", "prefix_sha256", "problem_sha256",
    "dictionary", "invariants", "sample_inputs", "rank", "problem", "reason",
    "refinements", "sat_queries", "max_clauses", "max_variables", "seconds",
    "engine", "counterexample_input", "theorem", "candidate_authorized", "proof_format",
}


@dataclass(frozen=True)
class InvariantLimits:
    """Structural caps, in addition to the shared wall-clock ``Budget``.

    Clauses/variables bound each SAT query, not process RSS. Refinements count
    counterexamples after the initial legal input; zero is a useful strict cap.
    """

    max_monomials: int = 512
    max_refinements: int = 512
    max_clauses: int = 250_000
    max_variables: int = 100_000
    max_prefix_gates: int = 100_000
    max_assumption_nodes: int = 4096

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            lower = 0 if name == "max_refinements" else 1
            if type(value) is not int or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")


_DEFAULT_LIMITS = InvariantLimits()


@dataclass(frozen=True)
class _Problem:
    prefix: Program
    initial_constants: tuple[tuple[int, int], ...]
    assumption: Expr
    dictionary: tuple[int, ...]

    def document(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix.circuit().to_dict(),
            "initial_constants": [list(pair) for pair in self.initial_constants],
            "assumption": expression_to_dict(self.assumption),
            "dictionary": list(self.dictionary),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document())


@dataclass(frozen=True)
class CutInvariantResult:
    """An exact result or an explicit refusal, with no candidate invariants on refusal.

    ``invariants`` are bit vectors over ``dictionary``: each selected monomial
    participates in an XOR equal to zero. A complete result gives a basis of
    *all* such relations on the nonempty prefix image. ``sample_inputs`` are
    legal original inputs, never unattached cut assignments.

    The private seal prevents accidental consumption of a hand-edited result;
    it is not a cryptographic signature. Serialized receipts always need replay.
    """

    outcome: str
    reason: str
    prefix_sha256: str
    problem_sha256: str
    dictionary: tuple[int, ...]
    invariants: tuple[int, ...]
    sample_inputs: tuple[int, ...]
    rank: int
    refinements: int
    sat_queries: int
    max_clauses: int
    max_variables: int
    seconds: float
    engine: str
    counterexample_input: int | None = None
    _problem: _Problem | None = field(default=None, repr=False, compare=False)
    _seal: Any = field(default=None, repr=False, compare=False)

    def _claim(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "prefix_sha256": self.prefix_sha256,
            "problem_sha256": self.problem_sha256,
            "dictionary": list(self.dictionary),
            "invariants": list(self.invariants),
            "sample_inputs": list(self.sample_inputs),
            "rank": self.rank,
            "problem": None if self._problem is None else self._problem.document(),
        }

    @property
    def proved(self) -> bool:
        return (
            self.outcome == "complete"
            and type(self._seal) is tuple and len(self._seal) == 2
            and self._seal[0] is _ISSUED
            and self._seal[1] == canonical_sha256(self._claim())
        )

    def to_dict(self) -> dict[str, Any]:
        """Export an untrusted receipt; :func:`replay_cut_invariants` rechecks it."""
        return {
            "schema_version": 1, "kind": _KIND,
            **self._claim(), "reason": self.reason,
            "refinements": self.refinements, "sat_queries": self.sat_queries,
            "max_clauses": self.max_clauses, "max_variables": self.max_variables,
            "seconds": self.seconds, "engine": self.engine,
            "counterexample_input": self.counterexample_input,
            "theorem": "classical_prefix_dictionary_invariants",
            "candidate_authorized": False,
            "proof_format": "witness_rows_and_fresh_sat_replay",
        }

    def cut_assumption(self, prefix: Circuit) -> Expr:
        """Return the proved conjunction over ``u.<wire>`` for this exact prefix.

        This is an input to ``SubstitutionContract(cut_assumption=...)``, not a
        replacement for the substitution proof. The contract must carry the
        same initial restrictions. That checker re-proves the prefix condition.
        """
        if not self.proved or self._problem is None:
            raise ValueError("only an issued or freshly replayed complete result is usable")
        if digest(_freeze_prefix(prefix, Guard(), None)) != self.prefix_sha256:
            raise ValueError("the prefix differs from the proved source")
        features = [
            _balanced([Var(f"u.{wire}") for wire in _bits(mask)], And, Const(True))
            for mask in self.dictionary
        ]
        relations = [
            Not(_balanced([features[i] for i in _bits(row)], Xor, Const(False)))
            for row in self.invariants
        ]
        result = _balanced(relations, And, Const(True))
        validate(result, frozenset(f"u.{q}" for q in range(prefix.width)))
        return result


def _balanced(expressions: list[Expr], op: Any, empty: Expr) -> Expr:
    if not expressions:
        return empty
    level = expressions
    while len(level) > 1:
        level = [op(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
                 for i in range(0, len(level), 2)]
    return level[0]


def _bits(value: int):
    while value:
        bit = value & -value
        yield bit.bit_length() - 1
        value ^= bit


class _Stopped(Exception):
    pass


class _BoundedEncoder(Encoder):
    def __init__(self, limits: InvariantLimits, guard: Guard) -> None:
        super().__init__()
        self.limits = limits
        self.guard = guard

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

    def fork(self) -> _BoundedEncoder:
        self.guard.check_time()
        other = _BoundedEncoder(self.limits, self.guard)
        other.clauses = list(self.clauses)  # existing clauses are never mutated
        other.next_variable = self.next_variable
        other._true = self._true
        other._gates = dict(self._gates)
        self.guard.check_time()
        return other


@dataclass
class _Run:
    guard: Guard
    limits: InvariantLimits
    factory: Any = None
    problem: _Problem | None = None
    rows: dict[int, int] = field(default_factory=dict)
    samples: list[int] = field(default_factory=list)
    refinements: int = 0
    queries: int = 0
    clauses: int = 0
    variables: int = 0

    def result(self, outcome: str, reason: str, *,
               invariants: tuple[int, ...] = (), witness: int | None = None) -> CutInvariantResult:
        if outcome != "inconclusive":
            self.guard.check_time()
        problem = self.problem
        result = CutInvariantResult(
            outcome, reason, "" if problem is None else digest(problem.prefix),
            "" if problem is None else problem.sha256,
            () if problem is None else problem.dictionary,
            invariants if outcome == "complete" else (), tuple(self.samples),
            len(self.rows), self.refinements, self.queries, self.clauses,
            self.variables, time.perf_counter() - self.guard.started,
            "unavailable" if self.factory is None else solver_name(self.factory),
            witness, problem,
        )
        if outcome == "complete":
            self.guard.check_time()
            object.__setattr__(result, "_seal", (_ISSUED, canonical_sha256(result._claim())))
        if outcome != "inconclusive":
            self.guard.check_time()
        object.__setattr__(result, "seconds", time.perf_counter() - self.guard.started)
        return result


def _run(budget: Budget | None, limits: InvariantLimits) -> _Run:
    if type(limits) is not InvariantLimits:
        raise TypeError("limits must be InvariantLimits")
    limits.__post_init__()
    guard = Guard(Budget(max_seconds=30) if budget is None else budget)
    if any(getattr(guard.budget, field) is not None
           for field in ("max_terms", "max_nodes", "max_bytes")):
        raise ValueError("cut invariant SAT supports time budgets and explicit InvariantLimits")
    return _Run(guard, limits)


def _assumption(expression: Expr | None, width: int, run: _Run) -> Expr:
    count = 0

    def copy(node: Expr, depth: int = 1) -> Expr:
        nonlocal count
        run.guard.check_time()
        count += 1
        if count > run.limits.max_assumption_nodes:
            raise _Stopped("assumption node cap exceeded")
        if depth > MAX_DEPTH:
            raise ValueError("assumption exceeds the Boolean grammar depth bound")
        if type(node) is Const:
            return Const(node.value)
        if type(node) is Var:
            if type(node.name) is not str:
                raise ValueError("assumption variable names must be plain strings")
            return Var(node.name)
        if type(node) is Not:
            return Not(copy(node.operand, depth + 1))
        if type(node) in (Xor, And, Eq):
            return type(node)(copy(node.left, depth + 1), copy(node.right, depth + 1))
        raise TypeError("assumption must use the closed Boolean expression grammar")

    result = copy(Const(True) if expression is None else expression)
    validate(result, frozenset(f"x.{wire}" for wire in range(width)))
    return result


def _freeze_prefix(prefix: Circuit, guard: Guard,
                   limits: InvariantLimits | None) -> Program:
    """Rebuild every Gate; Circuit.validate alone trusts frozen gate internals.

    Reconstruction also detaches source gate objects. A caller that bypassed a
    frozen dataclass through object.__setattr__ must not introduce unknown gates
    or malformed wire tuples into the proof grammar.
    """
    guard.check_time()
    if type(prefix) is not Circuit:
        raise TypeError("prefix must be a reversible Circuit")
    width = prefix.width
    if type(width) is not int or width < 1:
        raise ValueError("prefix width must be a positive integer")
    if type(prefix.gates) is not list:
        raise TypeError("prefix gates must be an actual list of Gate objects")
    if limits is not None:
        if width > limits.max_variables:
            raise _Stopped("SAT variable cap exceeded by prefix width")
        if len(prefix.gates) > limits.max_prefix_gates:
            raise _Stopped("prefix gate cap exceeded")
    gates = []
    for gate in prefix.gates:
        guard.check_time()
        if type(gate) is not Gate or type(gate.name) is not str:
            raise TypeError("prefix instructions must be exact Gate objects with plain names")
        if type(gate.qubits) is not tuple:
            raise TypeError("prefix gate qubits must be an immutable tuple")
        for qubit in gate.qubits:
            guard.check_time()
            if type(qubit) is not int or not 0 <= qubit < width:
                raise ValueError("prefix qubits must be plain integers within its width")
        gates.append(Gate(gate.name, gate.qubits))
        if limits is not None and len(gates) > limits.max_prefix_gates:
            raise _Stopped("prefix gate cap exceeded")
    frozen = Program(width, tuple(gates))
    guard.check_time()
    return frozen


def _prepare(run: _Run, prefix: Circuit, constants: tuple[tuple[int, int], ...],
             assumption: Expr | None, dictionary: tuple[int, ...] | None,
             degree: int) -> _Problem:
    run.guard.check_time()
    frozen = _freeze_prefix(prefix, run.guard, run.limits)
    if type(constants) is not tuple:
        raise TypeError("initial_constants must be an immutable tuple of pairs")
    seen = set()
    for pair in constants:
        run.guard.check_time()
        if (type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not int or not 0 <= pair[0] < frozen.width
                or type(pair[1]) is not int or pair[1] not in (0, 1)):
            raise ValueError("initial constants need unique in-range (wire, 0/1) pairs")
        if pair[0] in seen:
            raise ValueError("duplicate initial constant wire")
        seen.add(pair[0])
    expr = _assumption(assumption, frozen.width, run)
    if type(degree) is not int or degree < 0:
        raise ValueError("degree must be a nonnegative integer")
    if dictionary is None:
        count = 0
        for order in range(min(degree, frozen.width) + 1):
            run.guard.check_time()
            count += math.comb(frozen.width, order)
            if count > run.limits.max_monomials:
                raise _Stopped("monomial dictionary cap exceeded")
        terms = []
        for order in range(min(degree, frozen.width) + 1):
            for wires in combinations(range(frozen.width), order):
                run.guard.check_time()
                terms.append(sum(1 << q for q in wires))
        dictionary = tuple(terms)
    if type(dictionary) is not tuple or not dictionary:
        raise ValueError("dictionary must be a nonempty immutable tuple of monomial masks")
    if len(dictionary) > run.limits.max_monomials:
        raise _Stopped("monomial dictionary cap exceeded")
    if any(type(mask) is not int or mask < 0 or mask >> frozen.width for mask in dictionary):
        raise ValueError("dictionary masks must be nonnegative integers within the prefix width")
    if len(set(dictionary)) != len(dictionary):
        raise ValueError("duplicate monomial in dictionary")
    normalized = tuple(sorted(dictionary, key=lambda m: (m.bit_count(), m)))
    problem = _Problem(frozen, tuple(sorted(constants)), expr, normalized)
    run.problem = problem
    run.guard.check_time()
    return problem


def _encode(run: _Run) -> tuple[_BoundedEncoder, list[int], list[int]]:
    problem = run.problem
    assert problem is not None
    encoder = _BoundedEncoder(run.limits, run.guard)
    inputs = [encoder.new() for _ in range(problem.prefix.width)]
    state = list(inputs)
    for gate in problem.prefix.gates:
        run.guard.check_time()
        active = encoder.conjunction([state[q] for q in gate.controls])
        state[gate.target] = encoder.xor_gate(state[gate.target], active)
    for wire, value in problem.initial_constants:
        encoder.add(inputs[wire] if value else -inputs[wire])
    names = {f"x.{q}": literal for q, literal in enumerate(inputs)}
    encoder.add(tseitin(problem.assumption, encoder, names.__getitem__))
    run.guard.check_time()
    return encoder, inputs, state


def _solve(run: _Run, encoder: _BoundedEncoder, inputs: list[int]) -> int | None:
    """Return a concrete input for SAT, None for UNSAT, or raise on unknown."""
    run.guard.check_time()
    run.queries += 1
    run.clauses = max(run.clauses, len(encoder.clauses))
    run.variables = max(run.variables, encoder.next_variable - 1)
    solver = run.factory(bootstrap_with=encoder.clauses)
    value = None
    try:
        run.guard.check_time()
        answer, timed_out = solve_with_deadline(solver, run.guard.deadline)
        if timed_out or answer is None:
            raise _Stopped("SAT time/conflict budget exhausted")
        if answer:
            model = solver.get_model()
            if model is None:
                raise InternalInconsistency("SAT returned no model")
            positive = {literal for literal in model if literal > 0}
            value = sum(1 << q for q, literal in enumerate(inputs) if literal in positive)
        run.guard.check_time()
    finally:
        solver.delete()
        run.guard.check_time()  # setup, model extraction and cleanup all consume the budget
    return value


def _features(run: _Run, encoder: _BoundedEncoder, state: list[int]) -> list[int]:
    assert run.problem is not None
    features = []
    for mask in run.problem.dictionary:
        run.guard.check_time()
        features.append(encoder.conjunction([state[q] for q in _bits(mask)]))
    return features


def _row(run: _Run, value: int) -> int:
    problem = run.problem
    assert problem is not None
    if type(value) is not int or value < 0 or value >> problem.prefix.width:
        raise ValueError("sample is not an original input within the prefix width")
    run.guard.check_time()
    assignment = {f"x.{q}": (value >> q) & 1 for q in range(problem.prefix.width)}
    if (any(((value >> q) & 1) != b for q, b in problem.initial_constants)
            or not evaluate(problem.assumption, assignment)):
        raise ValueError("sample input violates the declared initial domain")
    state = problem.prefix.circuit().run(value)
    row = 0
    for index, mask in enumerate(problem.dictionary):
        run.guard.check_time()
        if state & mask == mask:
            row |= 1 << index
    run.guard.check_time()
    return row


def _add_row(run: _Run, row: int) -> bool:
    while row:
        run.guard.check_time()
        pivot = row.bit_length() - 1
        if pivot not in run.rows:
            run.rows[pivot] = row
            return True
        row ^= run.rows[pivot]
    return False


def _kernel(run: _Run) -> tuple[int, ...]:
    assert run.problem is not None
    basis = []
    for free in range(len(run.problem.dictionary)):
        run.guard.check_time()
        if free in run.rows:
            continue
        vector = 1 << free
        # Highest-bit pivots: each pivot depends only on lower coordinates.
        for pivot in sorted(run.rows):
            run.guard.check_time()
            if (run.rows[pivot] & vector).bit_count() & 1:
                vector |= 1 << pivot
        basis.append(vector)
    return tuple(basis)


def _violating_input(run: _Run, encoder: _BoundedEncoder, inputs: list[int],
                     features: list[int], basis: tuple[int, ...]) -> int | None:
    if not basis:
        run.guard.check_time()
        return None
    query = encoder.fork()
    violations = []
    for row in basis:
        parity = -query.true()
        for index in _bits(row):
            run.guard.check_time()
            parity = query.xor_gate(parity, features[index])
        violations.append(parity)
    query.add(*violations)
    witness = _solve(run, query, inputs)
    if witness is not None:
        actual = _row(run, witness)
        if not any((actual & row).bit_count() & 1 for row in basis):
            raise InternalInconsistency("SAT invariant counterexample failed concrete replay")
    return witness


def _solver(run: _Run) -> None:
    run.guard.check_time()
    run.factory = _solver_factory()
    run.guard.check_time()
    if run.factory is None:
        raise SatUnavailable("an interruptible python-sat solver is unavailable")


def _same_document(value: Any, expected: Any, guard: Guard) -> bool:
    """Compare against bounded trusted structure, including JSON bool/int distinctions."""
    guard.check_time()
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return (len(value) == len(expected) and value.keys() == expected.keys()
                and all(_same_document(value[key], item, guard)
                        for key, item in expected.items()))
    if type(expected) is list:
        return len(value) == len(expected) and all(
            _same_document(a, b, guard) for a, b in zip(value, expected))
    return bool(value == expected)


def discover_cut_invariants(
    prefix: Circuit,
    *,
    initial_constants: tuple[tuple[int, int], ...] = (),
    assumption: Expr | None = None,
    dictionary: tuple[int, ...] | None = None,
    degree: int = 2,
    limits: InvariantLimits = _DEFAULT_LIMITS,
    budget: Budget | None = None,
) -> CutInvariantResult:
    """Learn the complete invariant space in a fixed dictionary using exact SAT.

    Unspecified input wires are arbitrary, including dirty ancillas. Constants
    and ``assumption`` (names ``x.<wire>``) restrict only the original inputs.
    The dictionary contains square-free monomial masks on actual cut wires.
    With no dictionary, all masks of degree <= ``degree`` are used, including 1.
    ``budget=None`` means 30 seconds; explicit ``Budget()`` removes that deadline.
    Resource limits or absent SAT return ``inconclusive`` with no invariants.
    Invalid grammars/types raise, and an empty input domain returns ``empty_domain``.
    """
    run = _run(budget, limits)
    try:
        _prepare(run, prefix, initial_constants, assumption, dictionary, degree)
        _solver(run)
        encoder, inputs, state = _encode(run)
        seed = _solve(run, encoder, inputs)
        if seed is None:
            del encoder, inputs, state
            return run.result("empty_domain", "the initial domain is unsatisfiable")
        row = _row(run, seed)
        _add_row(run, row)
        run.samples.append(seed)
        features = _features(run, encoder, state)
        while True:
            basis = _kernel(run)
            witness = _violating_input(run, encoder, inputs, features, basis)
            if witness is None:
                del encoder, inputs, state, features
                return run.result("complete", "all dictionary relations proved by exact SAT",
                                  invariants=basis)
            if run.refinements >= limits.max_refinements:
                raise _Stopped("counterexample refinement cap reached")
            if not _add_row(run, _row(run, witness)):
                raise InternalInconsistency("counterexample did not strictly increase row rank")
            run.samples.append(witness)
            run.refinements += 1
    except (_Stopped, ResourceLimitExceeded, SatUnavailable) as error:
        return run.result("inconclusive", str(error))


def replay_cut_invariants(
    prefix: Circuit,
    receipt: dict[str, Any],
    *,
    initial_constants: tuple[tuple[int, int], ...] = (),
    assumption: Expr | None = None,
    limits: InvariantLimits = _DEFAULT_LIMITS,
    budget: Budget | None = None,
) -> CutInvariantResult:
    """Freshly check a complete receipt against a separately supplied prefix/domain.

    The reachable witness rows establish the rank; their canonical nullspace
    must exactly equal the claimed invariant basis. An exact SAT query then
    proves soundness on *all* legal inputs. Together these establish completeness
    in the fixed dictionary. This reuses the SAT encoder/solver trust boundary;
    it is not LRAT, a solver-independent proof, or authorization to rewrite.
    """
    run = _run(budget, limits)
    try:
        if (type(receipt) is not dict or set(receipt) != _RECEIPT_FIELDS
                or type(receipt.get("schema_version")) is not int
                or receipt.get("schema_version") != 1 or receipt.get("kind") != _KIND
                or receipt.get("outcome") != "complete"):
            raise ValueError("a version-one complete cut-invariant receipt is required")
        if (receipt["theorem"] != "classical_prefix_dictionary_invariants"
                or receipt["candidate_authorized"] is not False
                or receipt["counterexample_input"] is not None
                or receipt["proof_format"] != "witness_rows_and_fresh_sat_replay"):
            raise ValueError("receipt has a contradictory theorem or authorization claim")
        dictionary = receipt.get("dictionary")
        samples = receipt.get("sample_inputs")
        claimed = receipt.get("invariants")
        if not all(type(value) is list for value in (dictionary, samples, claimed)):
            raise ValueError("receipt dictionary, samples and invariant basis must be lists")
        if not samples or len(samples) > limits.max_monomials + 1:
            raise ValueError("receipt must contain a bounded nonempty witness list")
        if len(claimed) > limits.max_monomials:
            raise ValueError("receipt invariant basis exceeds the dictionary cap")
        problem = _prepare(run, prefix, initial_constants, assumption, tuple(dictionary), 0)
        # No serialized assertion may silently alter the caller's source/domain.
        if (receipt.get("prefix_sha256") != digest(problem.prefix)
                or receipt.get("problem_sha256") != problem.sha256
                or not _same_document(receipt.get("problem"), problem.document(), run.guard)
                or dictionary != list(problem.dictionary)):
            raise ValueError("receipt source, initial domain or dictionary identity mismatch")
        _solver(run)
        for index, value in enumerate(samples):
            row = _row(run, value)
            increased = _add_row(run, row)
            if index and not increased:
                raise ValueError("receipt has a redundant counterexample row")
            run.samples.append(value)
        basis = _kernel(run)
        if (any(type(row) is not int for row in claimed)
                or tuple(claimed) != basis or type(receipt.get("rank")) is not int
                or receipt["rank"] != len(run.rows)):
            raise ValueError("receipt basis is not the complete canonical witness nullspace")
        encoder, inputs, state = _encode(run)
        witness = _violating_input(run, encoder, inputs, _features(run, encoder, state), basis)
        del encoder, inputs, state
        if witness is not None:
            return run.result("not_proved", "a claimed invariant is false on a legal input",
                              witness=witness)
        return run.result("complete", "witness rank and all invariants freshly reverified",
                          invariants=basis)
    except (_Stopped, ResourceLimitExceeded, SatUnavailable) as error:
        return run.result("inconclusive", str(error))
