"""Sign-phase reversible programs with X-basis measure-and-reset (``hmr``).

See ``docs/research/PHASE_HMR_SPEC.md`` for the semantics, obligations and theorems this
module implements. Variables of the symbolic semantics are the data inputs
``x_0..x_{d-1}`` (ANF variables ``0..d-1``) followed by measurement outcomes
``m_0..m_{M-1}`` (ANF variables ``d..d+M-1``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .anf import ANF
from .circuit import UnsupportedOperation

_X_FAMILY = {"x": 1, "cx": 2, "ccx": 3}
_Z_FAMILY = {"z": 1, "cz": 2, "ccz": 3}


@dataclass(frozen=True)
class Op:
    kind: str
    """``mcx``, ``mcz``, ``hmr`` or ``mcz_if``."""
    qubits: tuple[int, ...]
    outcome: int | None = None


@dataclass
class PhaseProgram:
    data: int
    ancillas: int = 0
    ops: list[Op] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.data, int) or self.data < 1:
            raise ValueError("at least one data wire is required")
        if not isinstance(self.ancillas, int) or self.ancillas < 0:
            raise ValueError("ancilla count must be a nonnegative integer")

    @property
    def width(self) -> int:
        return self.data + self.ancillas

    @property
    def measurements(self) -> int:
        return sum(op.kind == "hmr" for op in self.ops)

    def _wires(self, qubits: tuple[int, ...], minimum: int) -> tuple[int, ...]:
        if len(qubits) < minimum:
            raise ValueError("not enough qubits")
        if any(not isinstance(q, int) or not 0 <= q < self.width for q in qubits):
            raise ValueError("qubit index out of range")
        if len(set(qubits)) != len(qubits):
            raise ValueError("qubits must be distinct")
        return qubits

    def append(self, name: str, *qubits: int) -> PhaseProgram:
        """Add a gate by name; names outside the fragment raise ``UnsupportedOperation``."""
        if name in _X_FAMILY or name == "mcx":
            arity = _X_FAMILY.get(name)
            if arity is not None and len(qubits) != arity:
                raise ValueError("incorrect gate arity")
            self.ops.append(Op("mcx", self._wires(qubits, 1)))
        elif name in _Z_FAMILY or name == "mcz":
            arity = _Z_FAMILY.get(name)
            if arity is not None and len(qubits) != arity:
                raise ValueError("incorrect gate arity")
            self.ops.append(Op("mcz", self._wires(qubits, 1)))
        else:
            raise UnsupportedOperation(f"{name!r} is outside the sign-phase/HMR fragment")
        return self

    def x(self, target: int) -> PhaseProgram:
        return self.append("x", target)

    def cx(self, control: int, target: int) -> PhaseProgram:
        return self.append("cx", control, target)

    def ccx(self, a: int, b: int, target: int) -> PhaseProgram:
        return self.append("ccx", a, b, target)

    def mcx(self, *qubits: int) -> PhaseProgram:
        return self.append("mcx", *qubits)

    def z(self, qubit: int) -> PhaseProgram:
        return self.append("z", qubit)

    def cz(self, a: int, b: int) -> PhaseProgram:
        return self.append("cz", a, b)

    def ccz(self, a: int, b: int, c: int) -> PhaseProgram:
        return self.append("ccz", a, b, c)

    def mcz(self, *qubits: int) -> PhaseProgram:
        return self.append("mcz", *qubits)

    def hmr(self, qubit: int) -> int:
        """X-basis measurement then reset of ``qubit``; returns the outcome index."""
        index = self.measurements
        self.ops.append(Op("hmr", self._wires((qubit,), 1), index))
        return index

    def mcz_if(self, outcome: int, *qubits: int) -> PhaseProgram:
        """``mcz(*qubits)`` applied iff measurement ``outcome`` returned 1."""
        if not isinstance(outcome, int) or not 0 <= outcome < self.measurements:
            raise ValueError("feed-forward may only use an earlier measurement outcome")
        self.ops.append(Op("mcz_if", self._wires(qubits, 1), outcome))
        return self

    def z_if(self, outcome: int, qubit: int) -> PhaseProgram:
        return self.mcz_if(outcome, qubit)

    def cz_if(self, outcome: int, a: int, b: int) -> PhaseProgram:
        return self.mcz_if(outcome, a, b)


def _product(values: list[ANF]) -> ANF:
    result = ANF.constant(1)
    for value in values:
        result = result * value
    return result


@dataclass(frozen=True)
class PhaseSemantics:
    data: int
    ancillas: int
    measurements: int
    outputs: tuple[ANF, ...]
    phase: ANF

    @property
    def outcome_mask(self) -> int:
        return ((1 << self.measurements) - 1) << self.data

    def violations(self) -> list[str]:
        """Unmet obligations: O1 (clean ancillas) and O2 (outcome independence)."""
        problems = [
            f"O1: ancilla wire {w} ends as {sorted(self.outputs[w].terms)}, not 0"
            for w in range(self.data, self.data + self.ancillas)
            if self.outputs[w].terms
        ]
        dependent = [m for m in self.phase.terms if m & self.outcome_mask]
        if dependent:
            problems.append(
                f"O2: phase depends on measurement outcomes ({len(dependent)} monomials)"
            )
        return problems


def phase_semantics(program: PhaseProgram) -> PhaseSemantics:
    state = [ANF.variable(w) if w < program.data else ANF() for w in range(program.width)]
    phase = ANF()
    for op in program.ops:
        if op.kind == "mcx":
            *controls, target = op.qubits
            state[target] = state[target] ^ _product([state[c] for c in controls])
        elif op.kind == "mcz":
            phase = phase ^ _product([state[q] for q in op.qubits])
        elif op.kind == "hmr":
            (qubit,) = op.qubits
            phase = phase ^ (ANF.variable(program.data + op.outcome) * state[qubit])
            state[qubit] = ANF()
        elif op.kind == "mcz_if":
            outcome = ANF.variable(program.data + op.outcome)
            phase = phase ^ (outcome * _product([state[q] for q in op.qubits]))
        else:
            raise UnsupportedOperation(op.kind)
    return PhaseSemantics(program.data, program.ancillas, program.measurements, tuple(state),
                          phase)


@dataclass(frozen=True)
class PhaseEquivalence:
    equivalent: bool
    up_to_global_phase: bool
    violations: tuple[str, ...] = ()
    witness: int | None = None
    """Data input on which the two unitaries differ (when both obligations hold)."""


def _min_monomial(value: ANF) -> int | None:
    return min(value.terms, key=lambda m: (m.bit_count(), m), default=None)


def check_phase_equivalence(left: PhaseProgram, right: PhaseProgram) -> PhaseEquivalence:
    """Decide ``U_left = U_right`` (or ``= −U_right``) for programs meeting O1 and O2.

    Programs violating an obligation are never certified: the result lists the violations.
    """
    if left.data != right.data:
        raise ValueError("programs must have the same number of data wires")
    a, b = phase_semantics(left), phase_semantics(right)
    violations = tuple(f"left {v}" for v in a.violations()) + tuple(
        f"right {v}" for v in b.violations()
    )
    if violations:
        return PhaseEquivalence(False, False, violations)
    for wire in range(left.data):
        if a.outputs[wire] != b.outputs[wire]:
            return PhaseEquivalence(
                False, False, witness=_min_monomial(a.outputs[wire] ^ b.outputs[wire])
            )
    difference = a.phase ^ b.phase
    if not difference.terms:
        return PhaseEquivalence(True, True)
    if difference == ANF.constant(1):
        return PhaseEquivalence(False, True)
    return PhaseEquivalence(False, False, witness=_min_monomial(difference))
