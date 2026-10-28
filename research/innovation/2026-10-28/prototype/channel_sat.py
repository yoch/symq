"""Bounded SAT decision for the *full* sign-phase/HMR quantum channel (issue #73).

Research-only pilot, independent of qant. Reuses the existing exact factored
HMR semantics (F, phi0, G); does NOT enumerate 2**M measurement outcomes.
For all basis coherences |x><y| the full channel is
    (-1)**(phi0(x) XOR phi0(y)) [G(x)=G(y)] |F(x)><F(y)|.
This checker proves three UNSAT queries, each with independent CNF inputs:
(1) F_L(x) != F_R(x)
(2) K_L(x,y) != K_R(x,y), K_P = AND_j (g_Pj(x)==g_Pj(y))
(3) common K=1 and differing relative phases.

Only the *full* data+ancilla channel is in scope. Traced-ancilla equivalence
is a different theorem and deliberately rejected/not offered. Glucose/PySAT
is an OPTIONAL dependency, already part of the SymQ test extras.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from factored import FactoredPhase, factor

from symq.anf import ANF
from symq.equivalence import InternalInconsistency
from symq.phase import PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded
from symq.sat.encoding import Encoder, SatUnavailable, _solver_factory, solver_available
from symq.sat.miter import _Watchdog


@dataclass(frozen=True)
class ChannelSATResult:
    outcome: str             # equivalent | different | inconclusive
    reason: str               # outputs | kernel | relative_phase | none | timeout | limit
    witness: tuple[int, ...] | None = None   # x, or (x,y)
    clauses: int = 0
    variables: int = 0
    seconds: float = 0.0
    queries: int = 0


class _ANFEncoder:
    """Exact Tseitin lift of ANFs into a single pair-input Boolean miter."""

    def __init__(self, width: int):
        self.enc = Encoder()
        self.width = width
        self.x = [self.enc.new() for _ in range(width)]
        self.y = [self.enc.new() for _ in range(width)]
        self.true = self.enc.new()
        self.enc.add(self.true)
        self.cache: dict[tuple[tuple[int, ...], int], int] = {}
        self.monomials: dict[tuple[int, int], int] = {}

    def _monomial(self, mask: int, which: int) -> int:
        key = mask, which
        if key in self.monomials:
            return self.monomials[key]
        inputs = self.x if which == 0 else self.y
        if mask == 0:
            literal = self.true
        else:
            literal = self.enc.conjunction([
                inputs[i] for i in range(self.width) if mask >> i & 1
            ])
        self.monomials[key] = literal
        return literal

    def polynomial(self, anf: ANF, which: int) -> int:
        terms = tuple(sorted(anf.terms))
        key = terms, which
        if key in self.cache:
            return self.cache[key]
        if any(mask >> self.width for mask in terms):
            raise ValueError("ANF variable lies outside the data width")
        if not terms:
            literal = -self.true
        else:
            literal = self._monomial(terms[0], which)
            for mask in terms[1:]:
                literal = self.enc.xor_gate(literal, self._monomial(mask, which))
        self.cache[key] = literal
        return literal

    def kernel(self, facts: FactoredPhase) -> int:
        equalities = []
        for coeff in facts.g:
            if not coeff.terms or coeff.terms == frozenset({0}):
                continue
            x = self.polynomial(coeff, 0)
            y = self.polynomial(coeff, 1)
            equalities.append(-self.enc.xor_gate(x, y))
        return self.enc.conjunction(equalities)


def _kernel(facts: FactoredPhase, x: int, y: int) -> bool:
    return all(g.evaluate(x) == g.evaluate(y) for g in facts.g)


def _output(facts: FactoredPhase, x: int) -> tuple[int, ...]:
    return tuple(f.evaluate(x) for f in facts.outputs)


def _relative(facts: FactoredPhase, x: int, y: int) -> int:
    return facts.phi0.evaluate(x) ^ facts.phi0.evaluate(y)


def _check_witness(
    label: str, facts_left: FactoredPhase, facts_right: FactoredPhase, witness: tuple[int, ...]
) -> None:
    if label == "outputs":
        x, = witness
        good = _output(facts_left, x) != _output(facts_right, x)
    else:
        x, y = witness
        k_left, k_right = _kernel(facts_left, x, y), _kernel(facts_right, x, y)
        if label == "kernel":
            good = k_left != k_right
        elif label == "relative_phase":
            good = (k_left and k_right and
                    _relative(facts_left, x, y) != _relative(facts_right, x, y))
        else:
            raise ValueError(label)
    if not good:
        raise InternalInconsistency(f"SAT {label} witness fails independent ANF evaluation")


def _query(
    a: FactoredPhase, b: FactoredPhase, label: str, started: float,
    seconds: float | None, max_clauses: int,
) -> ChannelSATResult:
    width = a.data
    cnf = _ANFEncoder(width)
    encoder = cnf.enc
    if label == "outputs":
        differences = [encoder.xor_gate(cnf.polynomial(f, 0), cnf.polynomial(g, 0))
                       for f, g in zip(a.outputs, b.outputs)]
        encoder.add(*differences)
    elif label == "kernel":
        encoder.add(encoder.xor_gate(cnf.kernel(a), cnf.kernel(b)))
    elif label == "relative_phase":
        kl, kr = cnf.kernel(a), cnf.kernel(b)
        encoder.add(kl)
        encoder.add(kr)
        rel_l = encoder.xor_gate(cnf.polynomial(a.phi0, 0), cnf.polynomial(a.phi0, 1))
        rel_r = encoder.xor_gate(cnf.polynomial(b.phi0, 0), cnf.polynomial(b.phi0, 1))
        encoder.add(encoder.xor_gate(rel_l, rel_r))
    else:
        raise ValueError(label)

    c, v = len(encoder.clauses), encoder.next_variable - 1
    elapsed = time.perf_counter() - started
    if c > max_clauses:
        return ChannelSATResult("inconclusive", "limit", clauses=c, variables=v,
                                seconds=elapsed, queries=1)
    if seconds is not None and elapsed >= seconds:
        return ChannelSATResult("inconclusive", "timeout", clauses=c, variables=v,
                                seconds=elapsed, queries=1)
    factory = _solver_factory()
    if factory is None:
        raise SatUnavailable("no interruptible SAT solver available")
    solver = factory(bootstrap_with=encoder.clauses)
    model = None
    answer = None
    timed_out = False
    try:
        remaining = None if seconds is None else seconds - (time.perf_counter() - started)
        if remaining is not None and remaining <= 0:
            timed_out = True
        elif remaining is None:
            answer = solver.solve()
        else:
            watchdog = _Watchdog(remaining, solver.interrupt)
            watchdog.start()
            try:
                answer = solver.solve_limited(expect_interrupt=True)
            finally:
                fired = watchdog.stop()
            timed_out = fired
        if answer is True and not timed_out:
            model = solver.get_model()
    finally:
        solver.delete()

    elapsed = time.perf_counter() - started
    if seconds is not None and elapsed >= seconds:
        timed_out = True
    if timed_out or answer is None:
        return ChannelSATResult("inconclusive", "timeout" if timed_out else "unknown",
                                clauses=c, variables=v, seconds=elapsed, queries=1)
    if answer is False:
        return ChannelSATResult("equivalent", "none", clauses=c, variables=v,
                                seconds=elapsed, queries=1)
    if model is None:
        raise InternalInconsistency("SAT returned no model for a satisfying channel miter")
    positive = {lit for lit in model if lit > 0}
    def pack(variables: list[int]) -> int:
        return sum((int(lit in positive) << i) for i, lit in enumerate(variables))
    witness = ((pack(cnf.x),) if label == "outputs" else (pack(cnf.x), pack(cnf.y)))
    _check_witness(label, a, b, witness)
    if seconds is not None and time.perf_counter() - started >= seconds:
        return ChannelSATResult("inconclusive", "timeout", clauses=c, variables=v,
                                seconds=time.perf_counter() - started, queries=1)
    return ChannelSATResult("different", label, witness=witness, clauses=c,
                            variables=v, seconds=time.perf_counter() - started, queries=1)


def check_channel_sat(
    left: PhaseProgram, right: PhaseProgram, *, budget: Budget | None = None,
    max_clauses: int = 250_000,
) -> ChannelSATResult:
    """Compare FULL channels only; never conflate a timeout/unsupported with equivalence."""
    started = time.perf_counter()
    if not isinstance(left, PhaseProgram) or not isinstance(right, PhaseProgram):
        raise TypeError("two PhasePrograms required")
    left.validate()
    right.validate()
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("full channel comparison needs matching data and ancilla widths")
    if type(max_clauses) is not int or max_clauses < 1:
        raise ValueError("positive max_clauses required")
    if not solver_available():
        raise SatUnavailable("install symq[sat] for the optional channel pilot")
    budget = budget or Budget()
    try:
        a = factor(left, budget)
        b = factor(right, budget)
    except ResourceLimitExceeded:
        return ChannelSATResult("inconclusive", "limit",
                                seconds=time.perf_counter() - started)
    clause_total = variable_total = queries = 0
    for label in ("outputs", "kernel", "relative_phase"):
        q = _query(a, b, label, started, budget.max_seconds, max_clauses)
        clause_total += q.clauses
        variable_total += q.variables
        queries += 1
        if q.outcome != "equivalent":
            return ChannelSATResult(q.outcome, q.reason, q.witness, clause_total,
                                    variable_total, time.perf_counter() - started, queries)
    return ChannelSATResult("equivalent", "none", clauses=clause_total,
                            variables=variable_total, seconds=time.perf_counter()-started,
                            queries=queries)
