"""Experimental exact Z/8 phase polynomial checker without Hadamards or measurements.

For basis-permuting reversible gates and diagonal roots of unity, every program acts as
    U|x> = omega**p(x) |F(x)>,  omega = exp(i*pi/4).
F is a tuple of canonical GF(2) ANFs. p has a UNIQUE multilinear polynomial
representation over the Boolean cube with coefficients in Z/8.

IMPORTANT: casting a Boolean ANF (XOR of monomials) coefficientwise into Z/8 is wrong:
    lift(a XOR b) = lift(a) + lift(b) - 2*lift(a)*lift(b).
Keeping the -2ab term is mandatory (e.g., T after CX).
This module is research-only and does NOT accept H, HMR, measure, reset or feed-forward.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from symq.anf import ANF
from symq.circuit import UnsupportedOperation
from symq.resources import Budget, Guard

_PERMUTATIONS = {"x": 1, "cx": 2, "ccx": 3}
_PHASES = {"t": 1, "tdg": 7, "s": 2, "sdg": 6, "z": 4, "cz": 4, "ccz": 4}
_ARITY = {**_PERMUTATIONS, "t": 1, "tdg": 1, "s": 1, "sdg": 1,
          "z": 1, "cz": 2, "ccz": 3}
_MOD = 8


@dataclass(frozen=True)
class Gate8:
    name: str
    wires: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.name not in _ARITY and self.name != "mcx":
            raise UnsupportedOperation(f"unsupported gate {self.name!r}; no H/measure")
        if not isinstance(self.wires, tuple) or any(type(q) is not int or q < 0 for q in self.wires):
            raise UnsupportedOperation("gate wires must be nonnegative integers")
        required = _ARITY.get(self.name)
        if required is not None and len(self.wires) != required:
            raise UnsupportedOperation(f"{self.name} requires {required} wires")
        if self.name == "mcx" and len(self.wires) < 2:
            raise UnsupportedOperation("mcx needs at least one control and one target")
        if len(set(self.wires)) != len(self.wires):
            raise UnsupportedOperation("gate wires must be distinct")


@dataclass
class Program8:
    width: int
    gates: list[Gate8] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if type(self.width) is not int or self.width < 1:
            raise ValueError("positive integer width required")
        if not isinstance(self.gates, list):
            raise UnsupportedOperation("gates must be a list of Gate8")
        for index, gate in enumerate(self.gates):
            if type(gate) is not Gate8 or any(q >= self.width for q in gate.wires):
                raise UnsupportedOperation(f"gate {index} malformed or out of width")
            gate.__post_init__()

    def append(self, name: str, *wires: int) -> Program8:
        gate = Gate8(name, tuple(wires))
        if any(q >= self.width for q in gate.wires):
            raise UnsupportedOperation("wire outside circuit width")
        self.gates.append(gate)
        return self

    def x(self, t: int) -> Program8:
        return self.append("x", t)
    def cx(self, c: int, t: int) -> Program8:
        return self.append("cx", c, t)
    def ccx(self, a: int, b: int, t: int) -> Program8:
        return self.append("ccx", a, b, t)
    def mcx(self, *wires: int) -> Program8:
        return self.append("mcx", *wires)
    def t(self, q: int) -> Program8:
        return self.append("t", q)
    def tdg(self, q: int) -> Program8:
        return self.append("tdg", q)
    def s(self, q: int) -> Program8:
        return self.append("s", q)
    def sdg(self, q: int) -> Program8:
        return self.append("sdg", q)
    def z(self, q: int) -> Program8:
        return self.append("z", q)
    def cz(self, a: int, b: int) -> Program8:
        return self.append("cz", a, b)
    def ccz(self, a: int, b: int, c: int) -> Program8:
        return self.append("ccz", a, b, c)

    def run(self, assignment: int) -> tuple[int, int]:
        """Independent integer basis-state oracle: returns (output, phase exponent mod 8)."""
        self.validate()
        if type(assignment) is not int or not 0 <= assignment < 1 << self.width:
            raise ValueError("input outside width")
        state = assignment
        phase = 0
        for gate in self.gates:
            name, wires = gate.name, gate.wires
            if name in _PERMUTATIONS or name == "mcx":
                *controls, target = wires
                if all(state >> q & 1 for q in controls):
                    state ^= 1 << target
            else:
                if all(state >> q & 1 for q in wires):
                    phase = (phase + _PHASES[name]) % _MOD
        return state, phase


# Z8 polynomials map a monomial bitmask -> coefficient 1..7, modulo 8.
# The multilinear representation is canonical on the Boolean cube.
Poly8 = dict[int, int]


def _add(left: Poly8, right: Poly8, scale: int = 1) -> Poly8:
    out = dict(left)
    for mask, coefficient in right.items():
        c = (out.get(mask, 0) + scale * coefficient) % _MOD
        if c:
            out[mask] = c
        else:
            out.pop(mask, None)
    return out


def _multiply(left: Poly8, right: Poly8, guard: Guard | None = None) -> Poly8:
    """Exact integer-valued Boolean multiplication with *intermediate* resource checks."""
    result: Poly8 = {}
    for a, ca in left.items():
        if guard is not None:
            guard.check_time()
        for b, cb in right.items():
            mask = a | b   # x_i**2 = x_i as an integer-valued Boolean function
            c = (result.get(mask, 0) + ca * cb) % _MOD
            if c:
                result[mask] = c
            else:
                result.pop(mask, None)
            if guard is not None:
                guard.check_terms(len(result))
    return result


def lift_anf(value: ANF, guard: Guard | None = None) -> Poly8:
    """Boolean XOR -> Z8 function, preserving all integer parity cross terms."""
    total: Poly8 = {}
    for mask in sorted(value.terms):
        monomial = {mask: 1}
        # parity(a,b) = a + b - 2*a*b on {0,1}; repeated exactly modulo 8.
        total = _add(_add(total, monomial), _multiply(total, monomial, guard), -2)
        if guard is not None:
            guard.check_time()
            guard.check_terms(len(total))
    return total


def eval_phase(phase: Poly8, x: int) -> int:
    return sum(c for mask, c in phase.items() if mask & x == mask) % _MOD


@dataclass(frozen=True)
class Symbolic8:
    outputs: tuple[ANF, ...]
    phase: Poly8

    def run(self, assignment: int) -> tuple[int, int]:
        output = sum(f.evaluate(assignment) << i for i, f in enumerate(self.outputs))
        return output, eval_phase(self.phase, assignment)


def symbolic(
    program: Program8, budget: Budget | None = None, *, _guard: Guard | None = None,
) -> Symbolic8:
    """Exact all-input symbolic action; no exponential basis-state enumeration."""
    guard = _guard if _guard is not None else Guard(budget)
    guard.check_time()
    if not isinstance(program, Program8):
        raise TypeError("Program8 required")
    program.validate()
    state = [ANF.variable(i) for i in range(program.width)]
    phase: Poly8 = {}
    for gate in program.gates:
        guard.check_time()
        if gate.name in _PERMUTATIONS or gate.name == "mcx":
            *controls, target = gate.wires
            control = ANF.constant(1)
            for q in controls:
                control = control * state[q]
                guard.check_terms(len(control.terms))
            state[target] = state[target] ^ control
        else:
            value = ANF.constant(1)
            for q in gate.wires:
                value = value * state[q]
                guard.check_terms(len(value.terms))
            phase = _add(phase, lift_anf(value, guard), _PHASES[gate.name])
        guard.check_terms(len(phase) + sum(len(x.terms) for x in state))
    return Symbolic8(tuple(state), phase)


@dataclass(frozen=True)
class Verdict8:
    status: str  # equal | global_phase | different
    global_phase_exponent: int | None = None
    witness: int | None = None
    reason: str = ""


def check_equivalence(left: Program8, right: Program8, budget: Budget | None = None) -> Verdict8:
    """Proof of exact or up-to-global eighth-root phase equivalence."""
    if not isinstance(left, Program8) or not isinstance(right, Program8):
        raise TypeError("two Program8 objects required")
    if left.width != right.width:
        raise ValueError("width mismatch")
    guard = Guard(budget)
    guard.check_time()
    a, b = symbolic(left, budget, _guard=guard), symbolic(right, budget, _guard=guard)
    guard.check_time()
    for index, (p, q) in enumerate(zip(a.outputs, b.outputs)):
        diff = p ^ q
        if diff.terms:
            x = min(diff.terms, key=lambda m: (m.bit_count(), m))
            if left.run(x)[0] == right.run(x)[0]:
                raise AssertionError("ANF witness failed independent integer replay")
            guard.check_time()
            return Verdict8("different", witness=x, reason=f"output {index} differs")
    difference = _add(a.phase, b.phase, -1)
    constant = difference.get(0, 0)
    nonconstant = [m for m, coefficient in difference.items() if m and coefficient]
    if nonconstant:
        guard.check_time()
        x = min(nonconstant, key=lambda m: (m.bit_count(), m))
        d0 = (left.run(0)[1] - right.run(0)[1]) % _MOD
        dx = (left.run(x)[1] - right.run(x)[1]) % _MOD
        if d0 == dx:
            raise AssertionError("phase witness failed independent integer replay")
        guard.check_time()
        return Verdict8("different", witness=x, reason="relative phase is input-dependent")
    guard.check_time()
    if constant:
        return Verdict8("global_phase", global_phase_exponent=constant,
                        reason="same unitary up to global eighth-root phase")
    return Verdict8("equal", global_phase_exponent=0, reason="identical basis permutation and phase")
