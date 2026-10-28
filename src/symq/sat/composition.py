"""One worked assume/guarantee composition, with the two obligations checked separately.

The setup. A circuit is split as ``A ; B`` and a candidate replacement as ``A' ; B'``. The cut has
its own state: ``A`` and ``A'`` may leave *different* values ``u`` and ``u'``, so the interface is a
**relation** ``R(u, u')``, not equality of cut wires. That is the point of issue #71: blind equality
cannot express "the two prefixes differ by a mask", and a relation that carries the correlation is
what makes a wrong composition fail rather than pass.

Obligations, each one SAT query:

0. **domain**: ``P(x)`` must be *satisfiable*. If it is not, every implication below is vacuous and
   would certify nothing. This query is the reason the pilot can never issue an empty certificate.
1. **prefix**: ``P(x) AND NOT R(A(x), A'(x))`` must be UNSAT — the prefixes always establish ``R``.
2. **interface**: ``R(u, u') AND NOT Pre_B(u)`` must be UNSAT — the relation implies what the second
   block needs, so obligation 3 is not being checked under an unattainable precondition.
3. **suffix**: ``R(u, u') AND Pre_B(u) AND NOT post(B(u), B'(u'))`` must be UNSAT.

``post`` is the declared output relation plus restoration. A counterexample from any query is a real
input assignment and is replayed through ``Circuit.run`` before being reported.

Soundness of the rule, in one paragraph. Take any input ``x`` satisfying ``P``. By (1), the two
prefixes leave states ``(u, u')`` satisfying ``R``. By (2) those states satisfy ``Pre_B``. By (3),
every pair of suffix states reachable from a ``Pre_B``-state under a ``R``-related cut satisfies
``post``. Since (1) quantifies over *all* ``x`` in the domain and ``R`` is asserted jointly over
``u`` and ``u'`` in one query, no correlation between the two cut states can be forgotten: a
composition that dropped a correlation would satisfy (1) while failing (3), which is exactly the
adversarial test in the suite.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from symq.circuit import Circuit
from symq.equivalence import InternalInconsistency
from symq.resources import Budget

from .assumptions import And, Const, Eq, Expr, Not, Var, tseitin, validate
from .encoding import (
    Encoder,
    SatUnavailable,
    _solver_factory,
    encode_circuit,
    solver_available,
    solver_name,
)
from .miter import _Watchdog

MAX_SECONDS_DEFAULT = 30.0


@dataclass(frozen=True)
class Interface:
    """``P(x)`` and ``R(u, v)``.

    ``P`` is over names ``x.<wire>``; ``R`` is over ``u.<wire>`` (left prefix output) and
    ``v.<wire>`` (right prefix output), both of the same width.
    """

    width: int
    precondition: Expr
    relation: Expr

    def validate(self, width: int) -> None:
        if self.width != width:
            raise ValueError(f"interface width {self.width} != prefix width {width}")
        validate(self.precondition, frozenset(f"x.{wire}" for wire in range(width)))
        validate(self.relation, frozenset(
            [f"u.{wire}" for wire in range(width)] + [f"v.{wire}" for wire in range(width)]))


@dataclass(frozen=True)
class Guarantee:
    """``Pre_B(u)`` for the second block, and ``post(B(u), B'(u'))`` over both outputs.

    Names: ``u.<wire>`` for the left cut, ``s.<wire>`` for the left final state, ``t.<wire>`` for
    the right final state. ``Pre_B`` mentions only ``u`` because it constrains the left block's
    entry; ``v`` is the right block's entry and is tied to ``u`` through ``R``.
    """

    width: int
    precondition: Expr
    postcondition: Expr

    def validate(self, width: int) -> None:
        if self.width != width:
            raise ValueError(f"guarantee width {self.width} != circuit width {width}")
        validate(self.precondition, frozenset(f"u.{wire}" for wire in range(width)))
        validate(self.postcondition, frozenset(
            [f"s.{wire}" for wire in range(width)] + [f"t.{wire}" for wire in range(width)]))


@dataclass
class Obligation:
    """One SAT query: what was asked, what came back, and whether the answer is the wanted one."""

    name: str
    wanted: str
    satisfiable: bool | None
    seconds: float
    clauses: int
    variables: int
    witness: dict[str, int] | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        if self.satisfiable is None:
            return False
        return (self.satisfiable is True) == (self.wanted == "sat")


@dataclass
class CompositionVerdict:
    accepted: bool
    obligations: list[Obligation] = field(default_factory=list)
    reason: str = ""

    def by_name(self, name: str) -> Obligation:
        matches = [item for item in self.obligations if item.name == name]
        if not matches:
            raise KeyError(name)
        return matches[0]

    @property
    def total_seconds(self) -> float:
        return sum(item.seconds for item in self.obligations)


def _literal_maps(width: int) -> dict[str, int]:
    """One CNF literal per symbolic name, in a fixed order so results are reproducible."""
    mapping: dict[str, int] = {}
    variable = 1
    for prefix in ("x.", "u.", "v.", "s.", "t."):
        for wire in range(width):
            mapping[f"{prefix}{wire}"] = variable
            variable += 1
    return mapping


def _solve(solver, deadline: float | None):
    if deadline is None:
        return solver.solve()
    remaining = max(deadline - time.perf_counter(), 0.001)
    watchdog = _Watchdog(remaining, solver.interrupt)
    watchdog.start()
    try:
        return solver.solve_limited(expect_interrupt=True)
    finally:
        watchdog.stop()


def _run(expression: Expr, mapping: dict[str, int], *, name: str, wanted: str,
         deadline: float | None, witness_names: tuple[str, ...] = ("x.",)) -> Obligation:
    """Assert ``expression`` and ask for a model; ``wanted`` says which answer is the good one."""
    encoder = Encoder()
    encoder.next_variable = max(mapping.values()) + 1
    literal = tseitin(expression, encoder, mapping.__getitem__)
    encoder.add(literal)
    factory = _solver_factory()
    solver = factory(bootstrap_with=encoder.clauses)
    started = time.perf_counter()
    try:
        answer = _solve(solver, deadline)
        elapsed = time.perf_counter() - started
        if answer is None:
            return Obligation(name, wanted, None, elapsed, len(encoder.clauses),
                              encoder.next_variable - 1, detail="budget exhausted")
        witness = None
        if answer:
            positive = {value for value in solver.get_model() if value > 0}
            witness = {key: int(value in positive) for key, value in mapping.items()
                       if key.startswith(witness_names)}
        return Obligation(name, wanted, bool(answer), elapsed, len(encoder.clauses),
                          encoder.next_variable - 1, witness)
    finally:
        solver.delete()


def check_composition(*, prefix_left: Circuit, prefix_right: Circuit, suffix_left: Circuit,
                      suffix_right: Circuit, interface: Interface, guarantee: Guarantee,
                      budget: Budget | None = None) -> CompositionVerdict:
    """Check the four obligations of the composition rule; never certify a vacuous contract."""
    if not solver_available():
        raise SatUnavailable("no SAT solver installed: pip install python-sat")
    width = prefix_left.width
    if not (prefix_right.width == suffix_left.width == suffix_right.width == width):
        raise ValueError("all four blocks must have the same width")
    interface.validate(width)
    guarantee.validate(width)
    deadline = None
    if budget is not None and budget.max_seconds is not None:
        deadline = time.perf_counter() + float(budget.max_seconds)
    mapping = _literal_maps(width)

    # 0. Domain: an unsatisfiable precondition would make everything below vacuous.
    domain = _run(interface.precondition, mapping, name="domain", wanted="sat",
                  deadline=deadline)
    obligations = [domain]
    if domain.satisfiable is not True:
        return CompositionVerdict(
            False, obligations,
            "the precondition is unsatisfiable, so every implication over it is vacuous")

    # 1. Prefix: P and NOT R over the two prefixes' cut states.
    obligations.append(_prefix_obligation(prefix_left, prefix_right, interface, deadline))
    # 2. Interface: R and NOT Pre_B, purely symbolic over the cut names.
    obligations.append(_run(And(interface.relation, Not(guarantee.precondition)), mapping,
                            name="interface", wanted="unsat", deadline=deadline))
    # 3. Suffix: R and Pre_B and NOT post over the two whole circuits.
    obligations.append(_suffix_obligation(prefix_left, prefix_right, suffix_left, suffix_right,
                                          interface, guarantee, deadline))
    accepted = all(item.ok for item in obligations)
    return CompositionVerdict(accepted, obligations,
                              "" if accepted else "at least one obligation failed")


def _prefix_obligation(prefix_left: Circuit, prefix_right: Circuit, interface: Interface,
                       deadline: float | None) -> Obligation:
    """``P(x) AND NOT R(A(x), A'(x))`` over a shared input assignment."""
    encoder = Encoder()
    left_steps = encode_circuit(encoder, prefix_left)
    right_steps = encode_circuit(encoder, prefix_right)
    mapping: dict[str, int] = {}
    for wire in range(prefix_left.width):
        first, second = left_steps.inputs[wire], right_steps.inputs[wire]
        encoder.equiv(first, second)
        mapping[f"x.{wire}"] = first
        mapping[f"u.{wire}"] = left_steps.outputs[wire]
        mapping[f"v.{wire}"] = right_steps.outputs[wire]
    violation = And(interface.precondition, Not(interface.relation))
    literal = tseitin(violation, encoder, mapping.__getitem__)
    encoder.add(literal)
    return _finish(encoder, "prefix", "unsat", deadline, mapping)


def _suffix_obligation(prefix_left: Circuit, prefix_right: Circuit, suffix_left: Circuit,
                       suffix_right: Circuit, interface: Interface, guarantee: Guarantee,
                       deadline: float | None) -> Obligation:
    """``R and Pre_B and NOT post``, with ``R`` asserted on the intermediate states.

    The cut names are bound to the *prefix outputs* and the final names to the *whole-circuit
    outputs*, so the relation constrains the intermediate state -- which a monolithic miter cannot
    express. This is the obligation that fails when a correlation is dropped.
    """
    left_whole = Circuit(prefix_left.width, [*prefix_left.gates, *suffix_left.gates])
    right_whole = Circuit(prefix_right.width, [*prefix_right.gates, *suffix_right.gates])
    encoder = Encoder()
    left_steps = encode_circuit(encoder, left_whole)
    right_steps = encode_circuit(encoder, right_whole)
    # The cut is a layer of the *same* encoding: re-encoding would allocate fresh variables that
    # no clause connects to the rest of the formula.
    left_cut = left_steps.layers[len(prefix_left.gates)]
    right_cut = right_steps.layers[len(prefix_right.gates)]
    mapping: dict[str, int] = {}
    for wire in range(prefix_left.width):
        first, second = left_steps.inputs[wire], right_steps.inputs[wire]
        encoder.equiv(first, second)
        mapping[f"x.{wire}"] = first
        mapping[f"u.{wire}"] = left_cut[wire]
        mapping[f"v.{wire}"] = right_cut[wire]
        mapping[f"s.{wire}"] = left_steps.outputs[wire]
        mapping[f"t.{wire}"] = right_steps.outputs[wire]
    violation = And(And(interface.relation, guarantee.precondition),
                    Not(guarantee.postcondition))
    literal = tseitin(violation, encoder, mapping.__getitem__)
    encoder.add(literal)
    return _finish(encoder, "composition", "unsat", deadline, mapping)


def _finish(encoder: Encoder, name: str, wanted: str, deadline: float | None,
            mapping: dict[str, int]) -> Obligation:
    factory = _solver_factory()
    solver = factory(bootstrap_with=encoder.clauses)
    started = time.perf_counter()
    try:
        answer = _solve(solver, deadline)
        elapsed = time.perf_counter() - started
        if answer is None:
            return Obligation(name, wanted, None, elapsed, len(encoder.clauses),
                              encoder.next_variable - 1, detail="budget exhausted")
        witness = None
        if answer:
            positive = {value for value in solver.get_model() if value > 0}
            witness = {key: int(value in positive) for key, value in mapping.items()
                       if key.startswith("x.")}
        return Obligation(name, wanted, bool(answer), elapsed, len(encoder.clauses),
                          encoder.next_variable - 1, witness)
    finally:
        solver.delete()


def solver_label() -> str:
    return solver_name(_solver_factory())


def replay_witness(left: Circuit, right: Circuit, obligation: Obligation) -> int:
    """Turn a reported witness into an input and execute both circuits on it.

    A witness that does not stay inside the declared domain is an encoding bug, and is reported as
    such rather than returned as a counterexample.
    """
    if not obligation.witness:
        raise ValueError("this obligation did not report a witness")
    value = 0
    for key, bit in obligation.witness.items():
        if bit:
            value |= 1 << int(key.split(".")[1])
    if not 0 <= value < (1 << left.width):
        raise InternalInconsistency("a witness is outside the input domain")
    left.run(value)
    right.run(value)
    return value


def equality_all(prefix: str, suffix: str, width: int) -> Expr:
    """``prefix[i] = suffix[i]`` for every wire, as one conjunction (the naive interface)."""
    expression: Expr = Const(True)
    for wire in range(width):
        expression = And(expression, Eq(Var(f"{prefix}{wire}"), Var(f"{suffix}{wire}")))
    return expression


def always_true() -> Expr:
    return Const(True)


def all_outputs_equal(width: int) -> Expr:
    return equality_all("s.", "t.", width)


