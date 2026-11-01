"""Research-only synthesis of exact measurement-phase repairs from live wires.

This constructs conditional Z/CZ/CCZ corrections at the end of a restricted
PhaseProgram, under its declared zero-ancilla input contract. No arbitrary
reset, S/T/H, classical value-feed-forward or full CPTP-channel claim.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from itertools import combinations
from time import perf_counter

from symq.anf import ANF
from symq.backends import make_algebra
from symq.phase import PhaseProgram, phase_semantics
from symq.resources import Budget, Guard, ResourceLimitExceeded


class PhaseDebtUnresolved(ValueError):
    """An outcome-phase debt is not expressible by the allowed live-wire signs."""


def fingerprint(program: PhaseProgram) -> str:
    program.validate()
    data = {
        "kind": "restricted_sign_hmr",
        "data": program.data,
        "ancillas": program.ancillas,
        "ops": [[op.kind, list(op.qubits), op.outcome] for op in program.ops],
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Repair:
    outcome: int
    controls: tuple[int, ...]


@dataclass(frozen=True)
class RepairProof:
    source_sha256: str
    repaired_sha256: str
    repairs: tuple[Repair, ...]
    base_phase: ANF
    native_audit: str | None
    original_event_count: int

    def assert_fresh(self, source: PhaseProgram, repaired: PhaseProgram) -> None:
        """Persistent receipts are NOT authority: reject modified source/target IR."""
        if (fingerprint(source) != self.source_sha256 or
                fingerprint(repaired) != self.repaired_sha256):
            raise ValueError("phase-repair transcript changed after proof")


def _coefficients(program: PhaseProgram, phase: ANF) -> tuple[ANF, tuple[ANF, ...]]:
    """Decompose an affine outcome phase without confusing events and bit storage."""
    mask = (1 << program.data)-1
    base: set[int] = set()
    debts: list[set[int]] = [set() for _ in range(program.measurements)]
    for term in phase.terms:
        outcome_bits = term >> program.data
        if not outcome_bits:
            base.add(term)
        elif outcome_bits.bit_count() == 1:
            event = outcome_bits.bit_length()-1
            if event >= program.measurements:
                raise RuntimeError("outcome outside declared phase variables")
            debts[event].add(term & mask)
        else:
            # Current strict PhaseProgram is affine in measurement outcomes;
            # an IR extension must NOT silently inherit this theorem.
            raise PhaseDebtUnresolved("nonaffine measurement-outcome term")
    return ANF(frozenset(base)), tuple(ANF(frozenset(p)) for p in debts)


def _integer_columns(polynomials: list[ANF], debts: tuple[ANF, ...]):
    monomials = sorted(set().union(
        *(p.terms for p in (*polynomials, *debts))
    ))
    ranks = {monom: i for i, monom in enumerate(monomials)}

    def encode(poly: ANF) -> int:
        return sum(1 << ranks[m] for m in poly.terms)

    return [encode(p) for p in polynomials], [encode(d) for d in debts]


def _elimination(columns: list[int], targets: list[int], guard: Guard
                 ) -> list[int]:
    """Deterministic GF(2) span solver. Not a minimum-gate optimization."""
    pivots: dict[int, tuple[int, int]] = {}
    for index, column in enumerate(columns):
        guard.check_time()
        vector = column
        chosen = 1 << index
        while vector:
            p = vector.bit_length()-1
            if p not in pivots:
                pivots[p] = (vector, chosen)
                break
            v, used = pivots[p]
            vector ^= v
            chosen ^= used
    solutions = []
    for event, target in enumerate(targets):
        vector, chosen = target, 0
        while vector:
            guard.check_time()
            p = vector.bit_length()-1
            if p not in pivots:
                raise PhaseDebtUnresolved(
                    f"event {event}: debt outside the span of live Z/CZ/CCZ corrections"
                )
            v, used = pivots[p]
            vector ^= v
            chosen ^= used
        solutions.append(chosen)
    return solutions


def _native_check(outputs: tuple[ANF, ...], debts: tuple[ANF, ...],
                  all_controls: list[tuple[int, ...]], selected: list[int],
                  data: int, backend: str, budget: Budget | None,
                  guard: Guard) -> None:
    """Optional native Boolean coefficient parity audit, NOT a channel proof."""
    guard.check_time()
    remaining = guard.deadline - perf_counter() if guard.deadline is not None else None
    if remaining is not None and remaining <= 0:
        guard.check_time()
        raise ResourceLimitExceeded("seconds", budget.max_seconds, budget.max_seconds)
    local_budget = replace(budget, max_seconds=remaining) if remaining is not None else budget
    algebra = make_algebra(backend, data, local_budget)
    values = [algebra.from_anf(f) for f in outputs]
    for event, bits in enumerate(selected):
        guard.check_time()
        accumulated = algebra.zero()
        for index, controls in enumerate(all_controls):
            if bits >> index & 1:
                accumulated = algebra.xor(
                    accumulated, algebra.product([values[q] for q in controls])
                )
        if not algebra.equal(accumulated, algebra.from_anf(debts[event])):
            raise RuntimeError("native coefficient audit disagrees with independent ANF")
    guard.check_time()


def synthesize_feedback(
    program: PhaseProgram, *, max_arity: int = 2,
    max_candidates: int = 128, max_ops: int = 256, max_data: int = 8,
    budget: Budget | None = None, audit_backend: str | None = None,
) -> tuple[PhaseProgram, RepairProof]:
    """Construct *late* sign corrections, then prove O1/O2 and unchanged base phase.

    Allowed late corrections are Z/CZ/CCZ on currently live output wires,
    classically controlled by one immutable HMR event. If impossible under
    the selected arity/width, refuse: never erase a phase debt by assumption.
    The optional explicit native backend audits the Boolean coefficient equations.
    """
    guard = Guard(budget)
    if type(program) is not PhaseProgram:
        raise TypeError("PhaseProgram required")
    program.validate()
    if (type(max_arity) is not int or not 1 <= max_arity <= 3 or
            type(max_candidates) is not int or max_candidates < 1 or
            type(max_ops) is not int or max_ops < 1 or
            type(max_data) is not int or max_data < 1):
        raise ValueError("positive synthesis bounds and arity 1..3 required")
    if len(program.ops) > max_ops or program.data > max_data:
        raise ResourceLimitExceeded("program size", max_ops, len(program.ops))
    if budget is not None and budget.max_nodes is not None and audit_backend is None:
        raise ValueError("max_nodes requires an explicitly selected ZDD audit")
    guard.check_time()
    source_sha = fingerprint(program)
    sem = phase_semantics(program)
    guard.check_time()
    guard.check_terms(max((len(f.terms) for f in (*sem.outputs, sem.phase)), default=0))
    if any(sem.outputs[q].terms for q in range(program.data, program.width)):
        raise PhaseDebtUnresolved("dirty output ancilla: value restoration unproved")

    base, debts = _coefficients(program, sem.phase)
    options: list[tuple[int, ...]] = []
    columns: list[ANF] = []
    for size in range(1, max_arity+1):
        for qs in combinations(range(program.width), size):
            guard.check_time()
            term = ANF.constant(1)
            for q in qs:
                term = term * sem.outputs[q]
                guard.check_terms(len(term.terms))
            if not term.terms:
                continue
            options.append(qs)
            columns.append(term)
            if len(options) > max_candidates:
                raise ResourceLimitExceeded("candidate corrections", max_candidates, len(options))
    coeff_bits, debt_bits = _integer_columns(columns, debts)
    selected = _elimination(coeff_bits, debt_bits, guard)
    repairs: list[Repair] = []
    repaired = PhaseProgram(program.data, program.ancillas, list(program.ops))
    for event, chosen in enumerate(selected):
        for i, qs in enumerate(options):
            if chosen >> i & 1:
                repaired.mcz_if(event, *qs)
                repairs.append(Repair(event, qs))
    repar = phase_semantics(repaired)
    guard.check_time()
    if (repar.outputs != sem.outputs or repar.phase != base or repar.violations()):
        raise RuntimeError("feedback repair failed independent strict phase proof")
    if audit_backend is not None:
        _native_check(sem.outputs, debts, options, selected, program.data,
                      audit_backend, budget, guard)
    receipt = RepairProof(source_sha, fingerprint(repaired), tuple(repairs), base,
                          audit_backend, program.measurements)
    guard.check_time()
    return repaired, receipt
