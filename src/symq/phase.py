"""Sign-phase reversible programs with X-basis measure-and-reset (``hmr``).

See ``docs/reference/phase-hmr-spec.md`` for the semantics, obligations and theorems this
module implements. Variables of the symbolic semantics are the data inputs
``x_0..x_{d-1}`` (ANF variables ``0..d-1``) followed by measurement outcomes
``m_0..m_{M-1}`` (ANF variables ``d..d+M-1``).

Architecture and Domain Boundary:
---------------------------------
This module is a pure-Python formal reference engine for the **sign-phase** fragment with HMR:
every phase is a power of ``(-1)``, i.e. a Boolean exponent over GF(2). There are no 8th roots
of unity, no ``S``/``T`` gates and no non-real phases. Every gate in the accepted grammar adds a
phase of ``+1`` or ``-1``, and the semantics is exact Boolean arithmetic over GF(2); no modular
arithmetic over a larger ring is involved anywhere.

The engine is decoupled from the configurable ``Algebra`` runtime, does not use dynamic resource
budgets (``Budget``), and does not leverage the native C core (``zdd-native``), which is dedicated
to pure reversible Boolean circuits (``symq.circuit``).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .anf import ANF
from .circuit import UnsupportedOperation
from .errors import InternalInconsistency
from .resources import Budget, Guard, session_scoped

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
        # ``bool`` is an ``int`` subclass in Python, so ``True`` would otherwise be accepted as a
        # width of 1. Dimensions are checked for the exact type, as elsewhere in symq.
        if isinstance(self.data, bool) or not isinstance(self.data, int) or self.data < 1:
            raise ValueError("at least one data wire is required")
        if isinstance(self.ancillas, bool) or not isinstance(self.ancillas, int) or self.ancillas < 0:
            raise ValueError("ancilla count must be a nonnegative integer")

    @property
    def width(self) -> int:
        return self.data + self.ancillas

    @property
    def measurements(self) -> int:
        return sum(op.kind == "hmr" for op in self.ops)

    def snapshot(self, *, check: Callable[[], None] | None = None) -> PhaseProgram:
        """A detached, revalidated copy for analyses that must not trust the original objects.

        Requires exact types (``Op``, ``str`` kind, ``tuple`` of ``int`` qubits, ``int`` or
        ``None`` outcome), rebuilds every instruction and validates the copy, so nothing in it
        is shared with the original or depends on subclass behaviour. ``check`` is called once
        per instruction.
        """
        if (type(self.data) is not int or type(self.ancillas) is not int
                or self.data < 1 or self.ancillas < 0):
            raise ValueError("invalid program dimensions")
        if type(self.ops) is not list:
            raise UnsupportedOperation("ops must be an actual list of Op values")
        exact = ("Op fields must be exact types (str kind, tuple of exact integers, "
                 "outcome None or exact integers)")
        ops = []
        for position, op in enumerate(self.ops):
            if check is not None:
                check()
            if type(op) is not Op or type(op.kind) is not str or type(op.qubits) is not tuple:
                raise UnsupportedOperation(f"instruction {position}: {exact}")
            # O(1) bound before any per-qubit scan: no instruction can touch more wires than exist.
            if len(op.qubits) > self.width:
                raise UnsupportedOperation(
                    f"instruction {position}: more qubits than width {self.width}")
            if (any(type(q) is not int for q in op.qubits)
                    or (op.outcome is not None and type(op.outcome) is not int)):
                raise UnsupportedOperation(f"instruction {position}: {exact}")
            ops.append(Op(op.kind, op.qubits, op.outcome))
        copy = PhaseProgram(self.data, self.ancillas, ops)
        copy.validate(check=check)
        return copy

    def validate(self, *, check: Callable[[], None] | None = None) -> None:
        """Re-check the whole instruction list against the fragment contract.

        ``ops`` is public and mutable, so the builders' guards are not enough: every
        analysis validates the list it is given, or an ``Op`` built by hand (or appended
        after construction) could be interpreted as an instruction the semantics does not
        define, and a certificate could be issued for an invalid program.
        """
        measurements = 0
        for position, op in enumerate(self.ops):
            if check is not None:
                check()  # optional cooperative budget, once per instruction
            where = f"instruction {position}"
            if not isinstance(op, Op):
                raise UnsupportedOperation(f"{where}: expected Op, got {type(op).__name__}")
            qubits = op.qubits
            if not isinstance(qubits, tuple) or not qubits:
                raise UnsupportedOperation(f"{where}: qubits must be a nonempty tuple")
            if any(not isinstance(q, int) or isinstance(q, bool) for q in qubits):
                raise UnsupportedOperation(f"{where}: qubit indices must be integers")
            if any(not 0 <= q < self.width for q in qubits):
                raise UnsupportedOperation(f"{where}: qubit index outside 0..{self.width - 1}")
            if len(set(qubits)) != len(qubits):
                raise UnsupportedOperation(f"{where}: qubit indices must be distinct")
            if op.kind == "mcx":
                # ``x`` on one wire is the empty product (an unconditional flip).
                if op.outcome is not None:
                    raise UnsupportedOperation(f"{where}: 'mcx' takes no outcome")
            elif op.kind == "mcz":
                if op.outcome is not None:
                    raise UnsupportedOperation(f"{where}: 'mcz' takes no outcome")
            elif op.kind == "hmr":
                if len(qubits) != 1:
                    raise UnsupportedOperation(f"{where}: 'hmr' acts on exactly one qubit")
                # ``phase_semantics`` computes ``data + op.outcome``, so a raw ``None`` here would
                # reach it as ``int + None`` and raise ``TypeError`` instead of a defined refusal.
                # The builders always set the index; a hand-built ``Op`` must too.
                if op.outcome is None:
                    raise UnsupportedOperation(
                        f"{where}: 'hmr' requires an explicit outcome index "
                        f"(expected {measurements})"
                    )
                if isinstance(op.outcome, bool) or not isinstance(op.outcome, int):
                    raise UnsupportedOperation(
                        f"{where}: 'hmr' outcome must be an integer, not "
                        f"{type(op.outcome).__name__}"
                    )
                if op.outcome != measurements:
                    raise UnsupportedOperation(
                        f"{where}: 'hmr' outcome {op.outcome!r} is not the next measurement "
                        f"index {measurements}"
                    )
                measurements += 1
            elif op.kind == "mcz_if":
                if op.outcome is None:
                    raise UnsupportedOperation(f"{where}: 'mcz_if' needs an outcome index")
                if isinstance(op.outcome, bool) or not isinstance(op.outcome, int):
                    raise UnsupportedOperation(
                        f"{where}: 'mcz_if' outcome must be an integer, not "
                        f"{type(op.outcome).__name__}"
                    )
                if not 0 <= op.outcome < measurements:
                    raise UnsupportedOperation(
                        f"{where}: 'mcz_if' outcome {op.outcome!r} is not an earlier "
                        f"measurement (0..{measurements - 1})"
                    )
            else:
                raise UnsupportedOperation(f"{where}: {op.kind!r} is outside the fragment")

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
        # ``0 <= False < measurements`` is true, so a boolean would slip through as outcome 0.
        if (isinstance(outcome, bool) or not isinstance(outcome, int)
                or not 0 <= outcome < self.measurements):
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


def _outcome(op: Op) -> int:
    """The outcome index of an ``hmr``/``mcz_if`` operation (guaranteed by ``validate``)."""
    if op.outcome is None:
        raise InternalInconsistency(f"validated {op.kind} operation without an outcome index")
    return op.outcome


def phase_semantics(program: PhaseProgram, *, budget: Budget | None = None,
                    _guard: Guard | None = None) -> PhaseSemantics:
    """Exact ANF semantics of ``program``.

    ``budget.max_seconds`` bounds the walk and ``budget.max_terms`` the size of every wire and of
    the phase polynomial; exceeding either raises ``ResourceLimitExceeded``. ``max_nodes`` does
    not apply (no diagram is built).
    """
    if not isinstance(program, PhaseProgram):
        raise TypeError("a PhaseProgram is required")
    guard = _guard if _guard is not None else Guard(budget)
    program.validate()
    state = [ANF.variable(w) if w < program.data else ANF() for w in range(program.width)]
    phase = ANF()
    for op in program.ops:
        guard.check_time()
        if op.kind == "mcx":
            *controls, target = op.qubits
            state[target] = state[target] ^ _product([state[c] for c in controls])
        elif op.kind == "mcz":
            phase = phase ^ _product([state[q] for q in op.qubits])
        elif op.kind == "hmr":
            (qubit,) = op.qubits
            phase = phase ^ (ANF.variable(program.data + _outcome(op)) * state[qubit])
            state[qubit] = ANF()
        elif op.kind == "mcz_if":
            outcome = ANF.variable(program.data + _outcome(op))
            phase = phase ^ (outcome * _product([state[q] for q in op.qubits]))
        else:
            raise UnsupportedOperation(op.kind)
        guard.check_terms(len(phase.terms))
        for qubit in op.qubits:
            guard.check_terms(len(state[qubit].terms))
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


@session_scoped
def check_phase_equivalence(left: PhaseProgram, right: PhaseProgram, *,
                            budget: Budget | None = None) -> PhaseEquivalence:
    """Decide ``U_left = U_right`` (or ``= −U_right``) for programs meeting O1 and O2.

    Programs violating an obligation are never certified: the result lists the violations.
    A witness is replayed through the independent state-vector oracle
    (:mod:`symq.phase_oracle`) before it is returned. ``budget`` bounds the whole call (see
    :func:`phase_semantics`); the evaluation uses exact ANF polynomials in Python.
    """
    if not isinstance(left, PhaseProgram) or not isinstance(right, PhaseProgram):
        raise TypeError("two PhaseProgram objects are required")
    if left.data != right.data:
        raise ValueError("programs must have the same number of data wires")
    guard = Guard(budget)
    a = phase_semantics(left, _guard=guard)
    b = phase_semantics(right, _guard=guard)
    violations = tuple(f"left {v}" for v in a.violations()) + tuple(
        f"right {v}" for v in b.violations()
    )
    if violations:
        return PhaseEquivalence(False, False, violations)
    for wire in range(left.data):
        if a.outputs[wire] != b.outputs[wire]:
            witness = _min_monomial(a.outputs[wire] ^ b.outputs[wire])
            return PhaseEquivalence(False, False, witness=_replayed(left, right, witness, guard))
    difference = a.phase ^ b.phase
    if not difference.terms:
        return PhaseEquivalence(True, True)
    if difference == ANF.constant(1):
        return PhaseEquivalence(False, True)
    witness = _min_monomial(difference)
    return PhaseEquivalence(False, False, witness=_replayed(left, right, witness, guard))


def _replayed(left: PhaseProgram, right: PhaseProgram, witness: int | None,
              guard: Guard) -> int:
    """Return ``witness`` after checking it with the independent state-vector oracle.

    Both programs satisfy O1 and O2, so every outcome sequence gives the same basis state and
    sign; the all-zero outcome sequence is therefore representative.
    """
    from .phase_oracle import run_program

    guard.check_time()
    if witness is None or not 0 <= witness < (1 << left.data):
        raise InternalInconsistency("phase difference without a valid data witness")
    if run_program(left, witness, 0) == run_program(right, witness, 0):
        raise InternalInconsistency(
            "phase witness fails independent state-vector replay")
    return witness
