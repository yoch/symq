"""Exact sparse dyadic phases on basis permutations; no Hadamards or measurements.

Angles are rational turns: Fraction(1,16) denotes exp(2*pi*i/16). Coefficients
live in Z/(2**k). Boolean parity is lifted as a+b-2ab, retaining cross terms.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from symq.anf import ANF
from symq.circuit import UnsupportedOperation
from symq.resources import Budget, Guard, session_scoped

_PERMUTATIONS = {"x": 1, "cx": 2, "ccx": 3}
_PHASES = {"t": Fraction(1, 8), "tdg": Fraction(-1, 8), "s": Fraction(1, 4),
           "sdg": Fraction(-1, 4), "z": Fraction(1, 2), "cz": Fraction(1, 2),
           "ccz": Fraction(1, 2)}
_ARITY = {**_PERMUTATIONS, "t": 1, "tdg": 1, "s": 1, "sdg": 1,
          "z": 1, "cz": 2, "ccz": 3, "phase": 1}
Poly = dict[int, int]
Poly8 = Poly


def _modulus(k: int) -> int:
    if type(k) is not int or k < 1:
        raise ValueError("k must be a positive integer")
    return 1 << k


def _exponent(angle: Fraction | int, k: int) -> int:
    if type(angle) not in (Fraction, int):
        raise UnsupportedOperation("phase angles must be exact Fraction or integer turns")
    scaled = angle * _modulus(k)
    if isinstance(scaled, Fraction) and scaled.denominator != 1:
        raise UnsupportedOperation("angle denominator must divide 2**k")
    return int(scaled) % (1 << k)


@dataclass(frozen=True)
class PhaseGate:
    name: str
    wires: tuple[int, ...]
    angle: Fraction | int | None = None

    def __post_init__(self) -> None:
        if self.name not in _ARITY and self.name != "mcx":
            raise UnsupportedOperation(f"unsupported gate {self.name!r}; no H/measure")
        if not isinstance(self.wires, tuple) or any(type(q) is not int or q < 0
                                                  for q in self.wires):
            raise UnsupportedOperation("gate wires must be nonnegative integers")
        required = _ARITY.get(self.name)
        if required is not None and len(self.wires) != required:
            raise UnsupportedOperation(f"{self.name} requires {required} wires")
        if self.name == "mcx" and len(self.wires) < 2:
            raise UnsupportedOperation("mcx needs at least one control and one target")
        if len(set(self.wires)) != len(self.wires):
            raise UnsupportedOperation("gate wires must be distinct")
        if self.name == "phase":
            if type(self.angle) not in (Fraction, int):
                raise UnsupportedOperation("phase requires exact rational turns")
        elif self.angle is not None:
            raise UnsupportedOperation("only phase takes an angle")


@dataclass
class PhaseProgram:
    width: int
    gates: list[PhaseGate] = field(default_factory=list)
    k: int = 3

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        guard = Guard()
        guard.check_time()
        _modulus(self.k)
        if type(self.width) is not int or self.width < 1:
            raise ValueError("positive integer width required")
        if not isinstance(self.gates, list):
            raise UnsupportedOperation("gates must be a list of PhaseGate")
        for index, gate in enumerate(self.gates):
            guard.check_time()
            if type(gate) is not PhaseGate:
                raise UnsupportedOperation(f"gate {index} malformed")
            gate.__post_init__()
            if any(q >= self.width for q in gate.wires):
                raise UnsupportedOperation(f"gate {index} out of width")
            if gate.name not in _PERMUTATIONS and gate.name != "mcx":
                _exponent(gate.angle if gate.name == "phase" else _PHASES[gate.name], self.k)

    def append(self, name: str, *wires: int, angle: Fraction | int | None = None) -> PhaseProgram:
        gate = PhaseGate(name, tuple(wires), angle)
        if any(q >= self.width for q in gate.wires):
            raise UnsupportedOperation("wire outside circuit width")
        if name not in _PERMUTATIONS and name != "mcx":
            _exponent(angle if name == "phase" else _PHASES[name], self.k)
        self.gates.append(gate)
        return self

    def x(self, t: int) -> PhaseProgram:
        return self.append("x", t)
    def cx(self, c: int, t: int) -> PhaseProgram:
        return self.append("cx", c, t)
    def ccx(self, a: int, b: int, t: int) -> PhaseProgram:
        return self.append("ccx", a, b, t)
    def mcx(self, *wires: int) -> PhaseProgram:
        return self.append("mcx", *wires)
    def t(self, q: int) -> PhaseProgram:
        return self.append("t", q)
    def tdg(self, q: int) -> PhaseProgram:
        return self.append("tdg", q)
    def s(self, q: int) -> PhaseProgram:
        return self.append("s", q)
    def sdg(self, q: int) -> PhaseProgram:
        return self.append("sdg", q)
    def z(self, q: int) -> PhaseProgram:
        return self.append("z", q)
    def cz(self, a: int, b: int) -> PhaseProgram:
        return self.append("cz", a, b)
    def ccz(self, a: int, b: int, c: int) -> PhaseProgram:
        return self.append("ccz", a, b, c)
    def phase(self, q: int, angle: Fraction | int) -> PhaseProgram:
        return self.append("phase", q, angle=angle)

    def run(self, assignment: int) -> tuple[int, int]:
        """Independent concrete integer oracle: (output, exponent modulo 2**k)."""
        self.validate()
        if type(assignment) is not int or not 0 <= assignment < 1 << self.width:
            raise ValueError("input outside width")
        state, phase = assignment, 0
        guard = Guard()
        for gate in self.gates:
            guard.check_time()
            if gate.name in _PERMUTATIONS or gate.name == "mcx":
                *controls, target = gate.wires
                if all(state >> q & 1 for q in controls):
                    state ^= 1 << target
            elif all(state >> q & 1 for q in gate.wires):
                angle = gate.angle if gate.name == "phase" else _PHASES[gate.name]
                phase = (phase + _exponent(angle, self.k)) % (1 << self.k)
        return state, phase


def _check_engine(guard: Guard) -> None:
    guard.check_time()
    if guard.budget.max_nodes is not None:
        raise ValueError("max_nodes is not supported by the explicit phase polynomial engine")


def _add(left: Poly, right: Poly, scale: int = 1, *, k: int = 3,
         guard: Guard | None = None) -> Poly:
    modulus = _modulus(k)
    out = dict(left)
    if guard is not None:
        guard.check_terms(len(out))
    for mask, coefficient in right.items():
        c = (out.get(mask, 0) + scale * coefficient) % modulus
        if c:
            out[mask] = c
        else:
            out.pop(mask, None)
        if guard is not None:
            guard.check_time()
            guard.check_terms(len(out))
    return out


def _multiply(left: Poly, right: Poly, guard: Guard | None = None, *, k: int = 3) -> Poly:
    modulus, result = _modulus(k), {}
    for a, ca in left.items():
        for b, cb in right.items():
            mask = a | b
            c = (result.get(mask, 0) + ca * cb) % modulus
            if c:
                result[mask] = c
            else:
                result.pop(mask, None)
            if guard is not None:
                guard.check_time()
                guard.check_terms(len(result))
    return result


def _boolean_product(left: ANF, right: ANF, guard: Guard) -> ANF:
    result: set[int] = set()
    for a in left.terms:
        for b in right.terms:
            m = a | b
            if m in result:
                result.remove(m)
            else:
                result.add(m)
            guard.check_time()
            guard.check_terms(len(result))
    return ANF(frozenset(result))


@session_scoped
def lift_anf(value: ANF, guard: Guard | None = None, *, k: int = 3) -> Poly:
    """Lift parity exactly: a XOR b = a + b - 2ab, including every cross term."""
    _modulus(k)
    if not isinstance(value, ANF):
        raise TypeError("ANF required")
    guard = guard if guard is not None else Guard()
    _check_engine(guard)
    guard.check_terms(len(value.terms))
    total: Poly = {}
    for mask in sorted(value.terms):
        monomial = {mask: 1}
        cross = _multiply(total, monomial, guard, k=k)
        total = _add(_add(total, monomial, k=k, guard=guard), cross, -2, k=k, guard=guard)
    return total


def eval_phase(phase: Poly, x: int, *, k: int = 3) -> int:
    return sum(c for mask, c in phase.items() if mask & x == mask) % _modulus(k)


@dataclass(frozen=True)
class SymbolicPhase:
    outputs: tuple[ANF, ...]
    phase: Poly
    k: int = 3

    def run(self, assignment: int) -> tuple[int, int]:
        if type(assignment) is not int or not 0 <= assignment < (1 << len(self.outputs)):
            raise ValueError("assignment outside symbolic width")
        output = sum(f.evaluate(assignment) << i for i, f in enumerate(self.outputs))
        return output, eval_phase(self.phase, assignment, k=self.k)


@session_scoped
def symbolic(program: PhaseProgram, budget: Budget | None = None, *,
             _guard: Guard | None = None) -> SymbolicPhase:
    guard = _guard if _guard is not None else Guard(budget)
    _check_engine(guard)
    if not isinstance(program, PhaseProgram):
        raise TypeError("PhaseProgram required")
    program.validate()
    guard.check_terms(program.width)
    state = [ANF.variable(i) for i in range(program.width)]
    phase: Poly = {}
    for gate in program.gates:
        guard.check_time()
        value = ANF.constant(1)
        wires = gate.wires[:-1] if gate.name in _PERMUTATIONS or gate.name == "mcx" \
            else gate.wires
        for q in wires:
            value = _boolean_product(value, state[q], guard)
        if gate.name in _PERMUTATIONS or gate.name == "mcx":
            state[gate.wires[-1]] = state[gate.wires[-1]] ^ value
        else:
            angle = gate.angle if gate.name == "phase" else _PHASES[gate.name]
            phase = _add(phase, lift_anf(value, guard, k=program.k),
                         _exponent(angle, program.k), k=program.k, guard=guard)
        guard.check_terms(len(phase) + sum(len(x.terms) for x in state))
    guard.check_time()
    return SymbolicPhase(tuple(state), phase, program.k)


@dataclass(frozen=True)
class PhaseVerdict:
    status: str
    global_phase_exponent: int | None = None
    witness: int | None = None
    reason: str = ""
    k: int = 3


@session_scoped
def check_equivalence(left: PhaseProgram, right: PhaseProgram, budget: Budget | None = None,
                      *, _guard: Guard | None = None, _symbolic=None) -> PhaseVerdict:
    """Classify exact, up-to-global, or different; exponent means left minus right."""
    if not isinstance(left, PhaseProgram) or not isinstance(right, PhaseProgram):
        raise TypeError("two PhaseProgram objects required")
    if left.width != right.width:
        raise ValueError("width mismatch")
    guard = _guard if _guard is not None else Guard(budget)
    _check_engine(guard)
    evaluator = symbolic if _symbolic is None else _symbolic
    a, b = evaluator(left, budget, _guard=guard), evaluator(right, budget, _guard=guard)
    k = max(a.k, b.k)
    for index, (p, q) in enumerate(zip(a.outputs, b.outputs)):
        guard.check_time()
        diff = p ^ q
        if diff.terms:
            x = min(diff.terms, key=lambda m: (m.bit_count(), m))
            if left.run(x)[0] == right.run(x)[0]:
                raise AssertionError("ANF witness failed independent integer replay")
            guard.check_time()
            return PhaseVerdict("different", witness=x, reason=f"output {index} differs", k=k)
    pa = {m: c << (k - a.k) for m, c in a.phase.items()}
    pb = {m: c << (k - b.k) for m, c in b.phase.items()}
    difference = _add(pa, pb, -1, k=k, guard=guard)
    constant = difference.get(0, 0)
    nonconstant = [m for m in difference if m]
    if nonconstant:
        x = min(nonconstant, key=lambda m: (m.bit_count(), m))
        def delta(assignment):
            return ((left.run(assignment)[1] << (k - left.k))
                    - (right.run(assignment)[1] << (k - right.k))) % (1 << k)
        if delta(0) == delta(x):
            raise AssertionError("phase witness failed independent integer replay")
        guard.check_time()
        return PhaseVerdict("different", witness=x, reason="relative phase is input-dependent", k=k)
    guard.check_time()
    return PhaseVerdict("global_phase" if constant else "equal", constant,
                        reason="same basis permutation and constant relative dyadic phase", k=k)


Gate8 = PhaseGate
Program8 = PhaseProgram
Symbolic8 = SymbolicPhase
Verdict8 = PhaseVerdict
