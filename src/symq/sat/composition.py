"""One worked assume/guarantee composition, with four separately checked obligations.

The setup. A circuit is split as ``A ; B`` and a candidate replacement as ``A' ; B'``. The cut has
its own state: ``A`` and ``A'`` may leave *different* values ``u`` and ``v``, so the interface is a
**relation** ``R(u, v)``, not equality of cut wires. That is the point of issue #71: blind equality
cannot express "the two prefixes differ by a mask", and a relation that carries the correlation is
what makes a wrong composition fail rather than pass.

Obligations, each one SAT query:

0. **domain**: ``P(x)`` must be *satisfiable*. If it is not, every implication below is vacuous and
   would certify nothing. This query is the reason the checker can never issue an empty certificate.
1. **prefix**: ``P(x) AND NOT R(A(x), A'(x))`` must be UNSAT — the prefixes always establish ``R``.
   Both prefixes are driven by the *same* input ``x``; this is the only obligation that does so.
2. **interface**: ``R(u, v) AND NOT Pre_B(u)`` must be UNSAT — the relation implies what the second
   block needs, so obligation 3 is not checked under an unattainable precondition.
3. **suffix**: ``R(u, v) AND Pre_B(u) AND NOT post(B(u), B'(v))`` must be UNSAT.

The suffix obligation is **local**. It encodes only ``B`` and ``B'``, starting from two fresh,
independent symbolic cut states ``u`` and ``v``. Neither prefix appears in it, ``u`` and ``v`` are
not tied together, and their only connection is ``R``. That is what makes the result reusable: once
obligations 1 and 2 hold, *any* pair of prefixes satisfying ``P`` lands in a cut pair covered by
obligation 3, whatever the prefixes' internals are.

An earlier revision instead encoded ``A;B`` and ``A';B'`` with the two initial inputs tied, then
asserted ``R`` at the internal cut. That is a **reachable-state** check on one specific pair of
circuits, not the universal statement above: it accepts whenever the prefixes happen to make the
conclusion true, even if ``R`` alone does not imply it. See
``test_the_weak_relation_is_rejected_on_the_audit_counterexample`` for the counterexample that
distinguishes them.

Soundness of the rule, in one paragraph. Take any input ``x`` satisfying ``P``. By (1), the two
prefixes leave states ``(u, v)`` satisfying ``R``. By (2) the left state satisfies ``Pre_B``. By (3),
every pair of cut states satisfying ``R AND Pre_B`` is sent by ``(B, B')`` to a pair satisfying
``post``. Composing, ``(A;B)(x)`` and ``(A';B')(x)`` satisfy ``post``. Obligation (3) is quantified
over all cut pairs, not just the reachable ones, so this argument needs no knowledge of how the
prefixes reach the cut — which is exactly what a compositional proof buys.

Witness handling. A counterexample to (1) is an input ``x``. A counterexample to (2) or (3) is a
**pair of cut states** ``(u, v)``, not necessarily reachable from any ``x``. The two are never
converted into one another; each is replayed against concrete semantics by :func:`replay_witness`
before being reported.

Budget. :func:`check_composition` starts one clock at entry and passes a shared :class:`_Clock` to
every obligation. Each obligation checks the clock before and after encoding, before and after
solver creation, cooperatively during solving, and after model extraction, witness verification and
cleanup. A result obtained after the deadline is reported as a timeout, never as a certified
verdict, and a timeout is never confused with an unsatisfiable precondition.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from symq.circuit import Circuit
from symq.resources import Budget

from .assumptions import And, Const, Eq, Expr, Not, Var, evaluate, tseitin, validate
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


class CompositionBudget:
    """A cooperative deadline shared by every obligation of one :func:`check_composition` call.

    The clock starts when the object is built, that is, at the public entry point, so encoding time
    counts against the budget instead of being invisible. Every phase asks :meth:`expired`; when it
    says yes the obligation reports itself as a timeout rather than as a verdict.
    """

    def __init__(self, seconds: float | None) -> None:
        self._started = time.perf_counter()
        self._deadline = None if seconds is None else self._started + float(seconds)

    @classmethod
    def from_budget(cls, budget: Budget | None) -> CompositionBudget:
        if budget is None or budget.max_seconds is None:
            return cls(None)
        return cls(float(budget.max_seconds))

    def expired(self) -> bool:
        return self._deadline is not None and time.perf_counter() > self._deadline

    def remaining(self) -> float | None:
        if self._deadline is None:
            return None
        return self._deadline - time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self._started

    @property
    def bounded(self) -> bool:
        return self._deadline is not None


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
        validate(
            self.relation,
            frozenset(
                [f"u.{wire}" for wire in range(width)] + [f"v.{wire}" for wire in range(width)]
            ),
        )


@dataclass(frozen=True)
class Guarantee:
    """``Pre_B(u)`` for the second block, and ``post(B(u), B'(v))`` over both outputs.

    Names: ``u.<wire>`` for the left cut state, ``s.<wire>`` for the left final state, ``t.<wire>``
    for the right final state. The left cut is the only state ``Pre_B`` constrains because it is the
    left suffix that runs from it; the right suffix starts from ``v`` and is tied to ``u`` only by
    ``R``.
    """

    width: int
    precondition: Expr
    postcondition: Expr

    def validate(self, width: int) -> None:
        if self.width != width:
            raise ValueError(f"guarantee width {self.width} != circuit width {width}")
        validate(self.precondition, frozenset(f"u.{wire}" for wire in range(width)))
        validate(
            self.postcondition,
            frozenset(
                [f"s.{wire}" for wire in range(width)] + [f"t.{wire}" for wire in range(width)]
            ),
        )


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
    def timed_out(self) -> bool:
        """``True`` when the budget ended the query before it could produce a verdict."""
        return self.satisfiable is None and "budget" in self.detail

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

    @property
    def timed_out(self) -> bool:
        return any(item.timed_out for item in self.obligations)


def _literal_maps(width: int) -> dict[str, int]:
    """One CNF literal per symbolic name, in a fixed order so results are reproducible."""
    mapping: dict[str, int] = {}
    variable = 1
    for prefix in ("x.", "u.", "v.", "s.", "t."):
        for wire in range(width):
            mapping[f"{prefix}{wire}"] = variable
            variable += 1
    return mapping


def _solve(solver, clock: CompositionBudget):
    """Solve under ``clock``; return ``(answer, timed_out)``.

    No solver is started once the deadline has passed, and a fired watchdog always wins: an answer
    that arrives after the deadline is discarded, because certifying it would report work the budget
    did not cover.
    """
    remaining = clock.remaining()
    if remaining is not None and remaining <= 0:
        return None, True
    if remaining is None:
        answer = solver.solve()
        return answer, clock.expired()
    watchdog = _Watchdog(remaining, solver.interrupt)
    watchdog.start()
    try:
        # A conflict ceiling counts conflicts, not seconds; the watchdog is the elapsed-time
        # mechanism, exactly as in the miter.
        if hasattr(solver, "conf_budget"):
            solver.conf_budget(50_000_000)
        answer = solver.solve_limited(expect_interrupt=True)
    finally:
        fired = watchdog.stop()
    if fired or clock.expired():
        return None, True
    return answer, False


def _witness_from(
    solver_model, mapping: dict[str, int], prefixes: tuple[str, ...]
) -> dict[str, int]:
    """Extract the named literals of one prefix from a model."""
    positive = {literal for literal in solver_model if literal > 0}
    return {
        name: int(variable in positive)
        for name, variable in mapping.items()
        if name.startswith(prefixes)
    }


def _timeout(
    encoder: Encoder,
    *,
    name: str,
    wanted: str,
    clock: CompositionBudget,
    started: float,
    detail: str,
) -> Obligation:
    """One place that builds a timeout obligation, so no phase can forget a field."""
    return Obligation(
        name,
        wanted,
        None,
        time.perf_counter() - started,
        len(encoder.clauses),
        encoder.next_variable - 1,
        detail=detail,
    )


def _finish(
    encoder: Encoder,
    mapping: dict[str, int],
    *,
    name: str,
    wanted: str,
    clock: CompositionBudget,
    started: float,
    witness_prefixes: tuple[str, ...],
    verify,
) -> Obligation:
    """Run and concretely validate one SAT query under the shared entry-time deadline.

    A provisional SAT/UNSAT verdict is not returned until *after* solver.delete().
    This matters because cleanup can itself consume the last part of the deadline.
    The elapsed seconds include encoding, setup, solve, model, replay and cleanup.
    """
    from symq.equivalence import InternalInconsistency

    def timeout(detail: str) -> Obligation:
        return _timeout(
            encoder, name=name, wanted=wanted, clock=clock, started=started, detail=detail
        )

    if clock.expired():
        return timeout("budget exhausted before solver creation")

    solver = None
    result: Obligation | None = None
    try:
        factory = _solver_factory()
        solver = factory(bootstrap_with=encoder.clauses)
        if clock.expired():
            result = timeout("budget exhausted after solver creation")
        else:
            answer, interrupted = _solve(solver, clock)
            if interrupted:
                result = timeout("budget exhausted during solving")
            elif answer is None:
                # A conflict ceiling or other unknown answer is not an UNSAT proof,
                # nor does it mean the domain itself is unsatisfiable.
                result = Obligation(
                    name, wanted, None, 0.0,
                    len(encoder.clauses), encoder.next_variable - 1,
                    detail="solver returned no definitive answer",
                )
            else:
                witness = None
                if answer:
                    if clock.expired():
                        result = timeout("budget exhausted before model extraction")
                    else:
                        model = solver.get_model()
                        if model is None:
                            raise InternalInconsistency("SAT returned a model-free satisfiable result")
                        witness = _witness_from(model, mapping, witness_prefixes)
                        if clock.expired():
                            result = timeout("budget exhausted during witness extraction")
                        else:
                            outcome = verify(witness)
                            if outcome is not True:
                                raise InternalInconsistency(
                                    f"obligation {name!r} reported a witness that concrete execution "
                                    f"does not confirm: {outcome}"
                                )
                if result is None:
                    result = Obligation(
                        name, wanted, bool(answer), 0.0,
                        len(encoder.clauses), encoder.next_variable - 1,
                        witness,
                    )
    finally:
        if solver is not None:
            solver.delete()

    # Do not expose a provisional decisive result if *cleanup* crossed the deadline.
    if clock.expired():
        return timeout("budget exhausted during solver cleanup or finalization")
    if result is None:
        raise InternalInconsistency(f"obligation {name!r} finished without a result")
    result.seconds = time.perf_counter() - started
    return result


def check_composition(
    *,
    prefix_left: Circuit,
    prefix_right: Circuit,
    suffix_left: Circuit,
    suffix_right: Circuit,
    interface: Interface,
    guarantee: Guarantee,
    budget: Budget | None = None,
) -> CompositionVerdict:
    """Check the four obligations of the composition rule; never certify a vacuous contract."""
    clock = CompositionBudget.from_budget(budget)
    if not solver_available():
        raise SatUnavailable("no SAT solver installed: pip install python-sat")
    width = prefix_left.width
    if not (prefix_right.width == suffix_left.width == suffix_right.width == width):
        raise ValueError("all four blocks must have the same width")
    interface.validate(width)
    guarantee.validate(width)

    obligations: list[Obligation] = []
    domain = _domain_obligation(interface, width, clock)
    obligations.append(domain)
    if domain.timed_out:
        return CompositionVerdict(False, obligations, "budget exhausted during the domain query")
    if domain.satisfiable is None:
        return CompositionVerdict(
            False, obligations, "domain query was inconclusive: no certificate"
        )
    if domain.satisfiable is False:
        return CompositionVerdict(
            False,
            obligations,
            "the precondition is unsatisfiable, so every implication over it is vacuous",
        )

    obligations.append(_prefix_obligation(prefix_left, prefix_right, interface, clock))
    obligations.append(_interface_obligation(interface, guarantee, width, clock))
    obligations.append(_suffix_obligation(suffix_left, suffix_right, interface, guarantee, clock))

    if any(item.timed_out for item in obligations):
        return CompositionVerdict(
            False,
            obligations,
            "budget exhausted: no verdict is certified for the obligations that timed out",
        )
    accepted = all(item.ok for item in obligations)
    return CompositionVerdict(
        accepted, obligations, "" if accepted else "at least one obligation failed"
    )


def _domain_obligation(interface: Interface, width: int, clock: CompositionBudget) -> Obligation:
    """``P(x)`` must be satisfiable, or every implication over it is vacuous."""
    def verify(witness: dict[str, int]) -> bool | str:
        value = _bits(witness, "x.", width)
        names = {f"x.{wire}": (value >> wire) & 1 for wire in range(width)}
        return True if evaluate(interface.precondition, names) else "model does not satisfy P"

    return _symbolic_obligation(
        interface.precondition,
        width,
        name="domain",
        wanted="sat",
        clock=clock,
        witness_prefixes=("x.",),
        verify=verify,
    )


def _interface_obligation(
    interface: Interface, guarantee: Guarantee, width: int, clock: CompositionBudget
) -> Obligation:
    """``R(u, v) AND NOT Pre_B(u)`` over fresh cut names: no circuit is encoded at all."""
    expression = And(interface.relation, Not(guarantee.precondition))

    def verify(witness: dict[str, int]) -> bool | str:
        u = _bits(witness, "u.", width)
        v = _bits(witness, "v.", width)
        left = {f"u.{wire}": (u >> wire) & 1 for wire in range(width)}
        right = {f"v.{wire}": (v >> wire) & 1 for wire in range(width)}
        if not evaluate(interface.relation, {**left, **right}):
            return "the reported pair does not satisfy R"
        if evaluate(guarantee.precondition, left):
            return "the reported pair satisfies Pre_B, so it is not a violation"
        return True

    return _symbolic_obligation(
        expression,
        width,
        name="interface",
        wanted="unsat",
        clock=clock,
        witness_prefixes=("u.", "v."),
        verify=verify,
    )


def _symbolic_obligation(
    expression: Expr,
    width: int,
    *,
    name: str,
    wanted: str,
    clock: CompositionBudget,
    witness_prefixes: tuple[str, ...],
    verify,
) -> Obligation:
    """One query over named literals only, with no circuit variables in scope."""
    started = time.perf_counter()
    mapping = _literal_maps(width)
    encoder = Encoder()
    encoder.next_variable = max(mapping.values()) + 1
    literal = tseitin(expression, encoder, mapping.__getitem__)
    encoder.add(literal)
    if clock.expired():
        return Obligation(
            name,
            wanted,
            None,
            time.perf_counter() - started,
            len(encoder.clauses),
            encoder.next_variable - 1,
            detail="budget exhausted after encoding",
        )
    return _finish(
        encoder,
        mapping,
        name=name,
        wanted=wanted,
        clock=clock,
        started=started,
        witness_prefixes=witness_prefixes,
        verify=verify if verify is not None else (lambda _witness: True),
    )


def _bits(witness: dict[str, int], prefix: str, width: int) -> int:
    """Pack one prefix of a named witness into a little-endian integer."""
    value = 0
    for wire in range(width):
        if witness.get(f"{prefix}{wire}"):
            value |= 1 << wire
    return value


def _prefix_obligation(
    prefix_left: Circuit,
    prefix_right: Circuit,
    interface: Interface,
    clock: CompositionBudget,
) -> Obligation:
    """``P(x) AND NOT R(A(x), A'(x))`` over a shared input assignment.

    Obligation 1 is the only one that ties the two blocks to a common ``x``; it is what turns the
    local suffix lemma into a statement about the composed circuits.
    """
    started = time.perf_counter()
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
    if clock.expired():
        return Obligation(
            "prefix",
            "unsat",
            None,
            time.perf_counter() - started,
            len(encoder.clauses),
            encoder.next_variable - 1,
            detail="budget exhausted after encoding",
        )

    def verify(witness: dict[str, int]) -> bool | str:
        value = _bits(witness, "x.", prefix_left.width)
        if not evaluate(
            interface.precondition,
            {f"x.{wire}": (value >> wire) & 1 for wire in range(prefix_left.width)},
        ):
            return "the reported input does not satisfy P"
        cut_left = prefix_left.run(value)
        cut_right = prefix_right.run(value)
        names = {
            **{f"u.{wire}": (cut_left >> wire) & 1 for wire in range(prefix_left.width)},
            **{f"v.{wire}": (cut_right >> wire) & 1 for wire in range(prefix_left.width)},
        }
        if evaluate(interface.relation, names):
            return "the reported input satisfies R, so it is not a violation"
        return True

    return _finish(
        encoder,
        mapping,
        name="prefix",
        wanted="unsat",
        clock=clock,
        started=started,
        witness_prefixes=("x.",),
        verify=verify,
    )


def _suffix_obligation(
    suffix_left: Circuit,
    suffix_right: Circuit,
    interface: Interface,
    guarantee: Guarantee,
    clock: CompositionBudget,
) -> Obligation:
    """``R(u, v) AND Pre_B(u) AND NOT post(B(u), B'(v))`` over **independent** cut states.

    This obligation encodes ``suffix_left`` and ``suffix_right`` and nothing else. Their inputs are
    fresh symbolic variables ``u`` and ``v`` with no clause linking them; the only constraint on the
    pair is ``R``. Consequently an UNSAT answer is a genuine local lemma -- it holds for every pair
    of cut states the relation admits, not just for those a particular pair of prefixes happens to
    produce.
    """
    started = time.perf_counter()
    encoder = Encoder()
    left_steps = encode_circuit(encoder, suffix_left)
    right_steps = encode_circuit(encoder, suffix_right)
    mapping: dict[str, int] = {}
    for wire in range(suffix_left.width):
        mapping[f"u.{wire}"] = left_steps.inputs[wire]
        mapping[f"v.{wire}"] = right_steps.inputs[wire]
        mapping[f"s.{wire}"] = left_steps.outputs[wire]
        mapping[f"t.{wire}"] = right_steps.outputs[wire]
    violation = And(And(interface.relation, guarantee.precondition), Not(guarantee.postcondition))
    literal = tseitin(violation, encoder, mapping.__getitem__)
    encoder.add(literal)
    if clock.expired():
        return Obligation(
            "suffix",
            "unsat",
            None,
            time.perf_counter() - started,
            len(encoder.clauses),
            encoder.next_variable - 1,
            detail="budget exhausted after encoding",
        )

    def verify(witness: dict[str, int]) -> bool | str:
        width = suffix_left.width
        u = _bits(witness, "u.", width)
        v = _bits(witness, "v.", width)
        left_names = {f"u.{wire}": (u >> wire) & 1 for wire in range(width)}
        right_names = {f"v.{wire}": (v >> wire) & 1 for wire in range(width)}
        if not evaluate(interface.relation, {**left_names, **right_names}):
            return "the reported pair does not satisfy R"
        if not evaluate(guarantee.precondition, left_names):
            return "the reported pair does not satisfy Pre_B"
        out_left = suffix_left.run(u)
        out_right = suffix_right.run(v)
        post = {
            **{f"s.{wire}": (out_left >> wire) & 1 for wire in range(width)},
            **{f"t.{wire}": (out_right >> wire) & 1 for wire in range(width)},
        }
        if evaluate(guarantee.postcondition, post):
            return "executing the suffixes on the pair satisfies post, so it is not a violation"
        return True

    return _finish(
        encoder,
        mapping,
        name="suffix",
        wanted="unsat",
        clock=clock,
        started=started,
        witness_prefixes=("u.", "v."),
        verify=verify,
    )


def solver_label() -> str:
    return solver_name(_solver_factory())


@dataclass(frozen=True)
class ReplayedWitness:
    """A witness turned into concrete states, with the violation it demonstrates.

    ``kind`` says which obligation it came from, because the two kinds are not interchangeable: a
    prefix witness is one original input ``x``, whereas a cut witness is a **pair** ``(u, v)`` of
    cut states that need not be reachable from any ``x``.
    """

    obligation: str
    kind: str
    inputs: tuple[int, ...]
    detail: str


def replay_witness(
    obligation: Obligation,
    *,
    interface: Interface,
    guarantee: Guarantee | None = None,
    prefix_left: Circuit | None = None,
    prefix_right: Circuit | None = None,
    suffix_left: Circuit | None = None,
    suffix_right: Circuit | None = None,
) -> ReplayedWitness:
    """Re-derive the violated obligation from concrete execution, independently of the CNF.

    Each obligation is replayed against its *own* semantics, and nothing is converted between kinds:

    * ``domain``: the witness is an input satisfying ``P``.
    * ``prefix``: the witness is an input satisfying ``P`` whose two prefixes violate ``R``.
    * ``interface``: the witness is a cut pair satisfying ``R`` but not ``Pre_B``. No input ``x`` is
      invented for it.
    * ``suffix``: the witness is a cut pair satisfying ``R`` and ``Pre_B`` whose suffix images violate
      ``post``.

    Any disagreement raises :class:`InternalInconsistency` rather than returning a witness.
    """
    from symq.equivalence import InternalInconsistency

    if obligation.satisfiable is not True:
        raise ValueError("only a satisfiable obligation has a witness to replay")
    if not obligation.witness:
        raise ValueError("this obligation did not report a witness")
    width = interface.width
    witness = obligation.witness

    if obligation.name == "domain":
        value = _bits(witness, "x.", width)
        names = {f"x.{wire}": (value >> wire) & 1 for wire in range(width)}
        if not evaluate(interface.precondition, names):
            raise InternalInconsistency("the domain witness does not satisfy P")
        return ReplayedWitness("domain", "input", (value,), "satisfies P")

    if obligation.name == "prefix":
        if prefix_left is None or prefix_right is None:
            raise ValueError("a prefix witness needs both prefixes")
        value = _bits(witness, "x.", width)
        names = {f"x.{wire}": (value >> wire) & 1 for wire in range(width)}
        if not evaluate(interface.precondition, names):
            raise InternalInconsistency("the prefix witness does not satisfy P")
        cut_left = prefix_left.run(value)
        cut_right = prefix_right.run(value)
        relation_names = {
            **{f"u.{wire}": (cut_left >> wire) & 1 for wire in range(width)},
            **{f"v.{wire}": (cut_right >> wire) & 1 for wire in range(width)},
        }
        if evaluate(interface.relation, relation_names):
            raise InternalInconsistency("the prefix witness satisfies R, so it violates nothing")
        return ReplayedWitness(
            "prefix",
            "input",
            (value,),
            f"A(x)={cut_left:#0{width + 2}b} and A'(x)={cut_right:#0{width + 2}b} disagree on R",
        )

    if obligation.name == "interface":
        if guarantee is None:
            raise ValueError("an interface witness needs the guarantee")
        u = _bits(witness, "u.", width)
        v = _bits(witness, "v.", width)
        left = {f"u.{wire}": (u >> wire) & 1 for wire in range(width)}
        right = {f"v.{wire}": (v >> wire) & 1 for wire in range(width)}
        if not evaluate(interface.relation, {**left, **right}):
            raise InternalInconsistency("the reported cut pair does not satisfy R")
        if evaluate(guarantee.precondition, left):
            raise InternalInconsistency("the reported cut pair satisfies Pre_B")
        return ReplayedWitness(
            "interface",
            "cut",
            (u, v),
            f"R holds on ({u:#0{width + 2}b}, {v:#0{width + 2}b}) but Pre_B fails on the left state",
        )

    if obligation.name == "suffix":
        if guarantee is None or suffix_left is None or suffix_right is None:
            raise ValueError("a suffix witness needs the guarantee and both suffixes")
        u = _bits(witness, "u.", width)
        v = _bits(witness, "v.", width)
        left = {f"u.{wire}": (u >> wire) & 1 for wire in range(width)}
        right = {f"v.{wire}": (v >> wire) & 1 for wire in range(width)}
        if not evaluate(interface.relation, {**left, **right}):
            raise InternalInconsistency("the reported cut pair does not satisfy R")
        if not evaluate(guarantee.precondition, left):
            raise InternalInconsistency("the reported cut pair does not satisfy Pre_B")
        out_left = suffix_left.run(u)
        out_right = suffix_right.run(v)
        post = {
            **{f"s.{wire}": (out_left >> wire) & 1 for wire in range(width)},
            **{f"t.{wire}": (out_right >> wire) & 1 for wire in range(width)},
        }
        if evaluate(guarantee.postcondition, post):
            raise InternalInconsistency("the pair satisfies post, so it violates nothing")
        return ReplayedWitness(
            "suffix",
            "cut",
            (u, v),
            f"B(u)={out_left:#0{width + 2}b} and B'(v)={out_right:#0{width + 2}b} violate post",
        )

    raise ValueError(f"obligation {obligation.name!r} has no replay semantics")


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
