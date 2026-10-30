"""Reconstruct immutable HMR events and check phase discharge at exact points.

This is an algebraic obligation checker, not a repair synthesizer or a full
channel theorem. Measurement in Z and unproved reset are outside this grammar.
"""
from __future__ import annotations

from dataclasses import dataclass

from symq.anf import ANF
from symq.circuit import UnsupportedOperation
from symq.experimental.composition import FrozenHybridProgram, hybrid_digest
from symq.experimental.hybrid import HybridProgram
from symq.resources import Budget, Guard, ResourceLimitExceeded, session_scoped


class UnresolvedPhaseDebt(ValueError):
    pass


@dataclass(frozen=True)
class MeasurementEvent:
    identity: int
    operation_index: int
    wire: int
    destination: str
    variable: int
    measured_value: ANF


@dataclass(frozen=True)
class PhaseDischarge:
    event: int
    after_operation: int

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 0 for v in (self.event, self.after_operation)):
            raise ValueError("nonnegative immutable event and operation indices required")


@dataclass(frozen=True)
class LedgerPoint:
    after_operation: int
    phase: ANF
    values: tuple[ANF, ...]
    classical: tuple[tuple[str, ANF], ...]


@dataclass(frozen=True)
class PhaseLedgerProof:
    source_sha256: str
    events: tuple[MeasurementEvent, ...]
    discharges: tuple[PhaseDischarge, ...]
    points: tuple[LedgerPoint, ...]
    final_phase: ANF

    def assert_fresh(self, program: HybridProgram) -> None:
        if hybrid_digest(program) != self.source_sha256:
            raise ValueError("phase ledger source stream changed; reconstruction required")


def _coefficient(phase: ANF, variable: int) -> ANF:
    mask = 1 << variable
    return ANF.from_terms(term ^ mask for term in phase.terms if term & mask)


@session_scoped
def verify_phase_ledger(
    program: HybridProgram, discharges: tuple[PhaseDischarge, ...], *,
    budget: Budget | None = None, require_all_events: bool = True,
    max_variables: int = 128, max_operations: int = 20_000,
) -> PhaseLedgerProof:
    """Replay actual operations and prove every supplied debt is zero there.

    Event identity is assigned by operation order, independently of mutable bit
    names. A claim cannot supply a replacement event, polynomial or phase. Any
    later reintroduced event debt is rejected at the final boundary as well.
    """
    guard = Guard(budget)
    guard.check_time()
    frozen = FrozenHybridProgram.freeze(program)
    if (type(discharges) is not tuple or any(type(d) is not PhaseDischarge for d in discharges)
            or len(set(discharges)) != len(discharges)):
        raise ValueError("unique immutable discharge claims required")
    if type(require_all_events) is not bool:
        raise TypeError("explicit require_all_events flag required")
    for name, val in (("max_variables", max_variables), ("max_operations", max_operations)):
        if type(val) is not int or val < 1:
            raise ValueError(f"{name} must be positive")
    if guard.budget.max_nodes is not None:
        raise ValueError("phase ledger uses explicit ANF; max_nodes is unsupported")
    count = sum(op.kind == "hmr" for op in frozen.ops)
    if frozen.data + count > max_variables:
        raise ResourceLimitExceeded("ledger variables", max_variables, frozen.data + count)
    if len(frozen.ops) > max_operations:
        raise ResourceLimitExceeded("ledger operations", max_operations, len(frozen.ops))
    if any(d.event >= count or d.after_operation >= len(frozen.ops) for d in discharges):
        raise ValueError("discharge references an unknown event or operation")
    values = [ANF.variable(q) for q in range(frozen.data)] + [ANF()] * frozen.ancillas
    classical: dict[str, ANF] = {}
    phase = ANF()
    events = []
    points = []
    requested = {d.after_operation for d in discharges}
    one = ANF.constant(1)

    def mul(left: ANF, right: ANF) -> ANF:
        # Guard the potential cross product before allocating it.
        guard.check_time()
        guard.check_terms(len(left.terms) * len(right.terms))
        answer = left * right
        guard.check_terms(len(answer.terms))
        return answer

    def condition(name: str | None) -> ANF:
        if name is None:
            return one
        return classical[name.removeprefix("!")] ^ (one if name.startswith("!") else ANF())

    for index, op in enumerate(frozen.ops):
        guard.check_time()
        active = condition(op.condition)
        if op.kind == "store":
            classical[op.slot] = ANF.constant(op.value)
        elif op.kind == "invert":
            classical[op.slot] ^= active
        elif op.kind == "oxor":
            classical[op.slot] ^= classical[op.source]
        elif op.kind in {"x", "cx", "ccx", "mcx"}:
            *controls, target = op.wires
            value = active
            for q in controls:
                value = mul(value, values[q])
            values[target] ^= value
        elif op.kind in {"swap", "cswap"}:
            a, b = op.wires[-2:]
            control = active if op.kind == "swap" else mul(active, values[op.wires[0]])
            difference = mul(control, values[a] ^ values[b])
            values[a] ^= difference
            values[b] ^= difference
        elif op.kind in {"z", "cz", "ccz", "neg"}:
            sign = active
            for q in op.wires:
                sign = mul(sign, values[q])
            phase ^= sign
        elif op.kind == "hmr":
            event = MeasurementEvent(len(events), index, op.wires[0], op.slot,
                                     frozen.data + len(events), values[op.wires[0]])
            events.append(event)
            classical[op.slot] = ANF.variable(event.variable)
            phase ^= mul(classical[op.slot], event.measured_value)
            values[op.wires[0]] = ANF()
        elif op.kind == "reset" and values[op.wires[0]] in (ANF(), one):
            values[op.wires[0]] = ANF()
        else:
            raise UnsupportedOperation(f"ledger op {index}: {op.kind} needs channel semantics")
        guard.check_terms(sum(len(v.terms) for v in values) + len(phase.terms)
                          + sum(len(v.terms) for v in classical.values()))
        if index in requested:
            points.append(LedgerPoint(index, phase, tuple(values), tuple(sorted(classical.items()))))
    by_point = {p.after_operation: p for p in points}
    for claim in discharges:
        event = events[claim.event]
        if claim.after_operation < event.operation_index:
            raise UnresolvedPhaseDebt("a discharge cannot precede its immutable measurement event")
        debt = _coefficient(by_point[claim.after_operation].phase, event.variable)
        if debt.terms:
            raise UnresolvedPhaseDebt(
                f"event {claim.event}: nonzero phase debt after op {claim.after_operation}")
    if require_all_events and {d.event for d in discharges} != set(range(count)):
        raise UnresolvedPhaseDebt("every immutable measurement event needs a discharge point")
    if require_all_events:
        for event in events:
            if _coefficient(phase, event.variable).terms:
                raise UnresolvedPhaseDebt(f"event {event.identity}: debt reintroduced after discharge")
    guard.check_time()
    return PhaseLedgerProof(hybrid_digest(frozen), tuple(events), discharges, tuple(points), phase)
