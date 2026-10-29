"""Bounded exact channel reference over Q(zeta_(2**k)); experimental.

Kraus amplitudes, including H and X-basis measurement/reset, are summed exactly.
The only event-elimination shortcut is the proved affine-event product formula.
No Boolean-kernel criterion is extended to non-real phases.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from symq.circuit import UnsupportedOperation
from symq.resources import Budget, Guard, ResourceLimitExceeded, session_scoped

from .phase import _PERMUTATIONS, _PHASES, PhaseGate, PhaseProgram, _exponent, _modulus


@dataclass(frozen=True)
class Cyclotomic:
    """Sparse canonical Q[z]/(z**(2**(k-1))+1), z=exp(2*pi*i/2**k)."""
    k: int
    terms: tuple[tuple[int, Fraction], ...] = ()

    def __post_init__(self) -> None:
        if type(self.k) is not int or self.k < 2:
            raise ValueError("cyclotomic field k must be an integer >= 2")
        degree = 1 << (self.k - 1)
        result: dict[int, Fraction] = {}
        for power, coefficient in self.terms:
            if type(power) is not int or type(coefficient) not in (int, Fraction):
                raise ValueError("exact rational cyclotomic coefficients required")
            power %= 2 * degree
            coefficient = Fraction(coefficient)
            if power >= degree:
                power -= degree
                coefficient = -coefficient
            result[power] = result.get(power, Fraction()) + coefficient
        object.__setattr__(self, "terms", tuple(sorted((p, c) for p, c in result.items() if c)))

    @classmethod
    def root(cls, k: int, exponent: int = 0) -> Cyclotomic:
        return cls(k, ((exponent, Fraction(1)),))

    def _same(self, other: Cyclotomic) -> None:
        if not isinstance(other, Cyclotomic) or self.k != other.k:
            raise ValueError("coefficients must belong to the same cyclotomic field")

    def __bool__(self) -> bool:
        return bool(self.terms)

    def __add__(self, other: Cyclotomic) -> Cyclotomic:
        self._same(other)
        return Cyclotomic(self.k, self.terms + other.terms)

    def __neg__(self) -> Cyclotomic:
        return Cyclotomic(self.k, tuple((p, -c) for p, c in self.terms))

    def __sub__(self, other: Cyclotomic) -> Cyclotomic:
        return self + (-other)

    def __mul__(self, other: Cyclotomic) -> Cyclotomic:
        self._same(other)
        return Cyclotomic(self.k, tuple((p + q, a * b) for p, a in self.terms
                                       for q, b in other.terms))

    def scale(self, value: Fraction | int) -> Cyclotomic:
        if type(value) not in (int, Fraction):
            raise ValueError("exact rational scale required")
        return Cyclotomic(self.k, tuple((p, c * value) for p, c in self.terms))

    def conjugate(self) -> Cyclotomic:
        return Cyclotomic(self.k, tuple((-p, c) for p, c in self.terms))

    def approximate(self) -> complex:
        """Display helper only; neither proofs nor reference comparisons use floats."""
        import cmath
        return sum(float(c) * cmath.exp(2j * cmath.pi * p / (1 << self.k))
                   for p, c in self.terms)


@dataclass(frozen=True)
class QuantumGate:
    name: str
    wires: tuple[int, ...]
    angle: Fraction | int | None = None
    outcome: int | None = None


@dataclass
class CyclotomicProgram(PhaseProgram):
    """All wires are inputs/outputs; HMR outcomes are internal and discarded.

    phase_if is the sole classical feed-forward operation and requires an earlier
    outcome. There are no initialized/hidden ancillas or general reset semantics.
    """
    def validate(self) -> None:
        guard = Guard()
        guard.check_time()
        _modulus(self.k)
        if type(self.width) is not int or self.width < 1:
            raise ValueError("positive integer width required")
        if not isinstance(self.gates, list):
            raise UnsupportedOperation("gates must be a list of QuantumGate")
        events = 0
        for gate in self.gates:
            guard.check_time()
            if type(gate) is not QuantumGate:
                raise UnsupportedOperation("expected QuantumGate")
            if not isinstance(gate.wires, tuple) or any(type(q) is not int or
                                                       not 0 <= q < self.width
                                                       for q in gate.wires):
                raise UnsupportedOperation("gate wires outside width")
            if gate.name in {"h", "hmr", "phase_if"}:
                if len(gate.wires) != 1:
                    raise UnsupportedOperation(f"{gate.name} requires one wire")
                if gate.name == "hmr":
                    if type(gate.outcome) is not int or gate.outcome != events:
                        raise UnsupportedOperation("HMR outcome indices must be sequential")
                    events += 1
                elif gate.name == "phase_if":
                    if type(gate.outcome) is not int or not 0 <= gate.outcome < events:
                        raise UnsupportedOperation("feed-forward requires an earlier outcome")
                    _exponent(gate.angle, self.k)
                elif gate.outcome is not None:
                    raise UnsupportedOperation("H takes no outcome")
                if gate.name != "phase_if" and gate.angle is not None:
                    raise UnsupportedOperation("H/HMR take no angle")
            else:
                PhaseGate(gate.name, gate.wires, gate.angle)
                if gate.outcome is not None:
                    raise UnsupportedOperation("unitary phase/permutation takes no outcome")
                if gate.name not in _PERMUTATIONS and gate.name != "mcx":
                    _exponent(gate.angle if gate.name == "phase" else _PHASES[gate.name], self.k)

    def append(self, name: str, *wires: int, angle=None, outcome=None) -> CyclotomicProgram:
        gate = QuantumGate(name, tuple(wires), angle, outcome)
        self.gates.append(gate)
        try:
            self.validate()
        except Exception:
            self.gates.pop()
            raise
        return self

    def h(self, q: int) -> CyclotomicProgram:
        return self.append("h", q)

    def hmr(self, q: int) -> int:
        outcome = sum(g.name == "hmr" for g in self.gates)
        self.append("hmr", q, outcome=outcome)
        return outcome

    def phase_if(self, outcome: int, q: int, angle: Fraction | int) -> CyclotomicProgram:
        return self.append("phase_if", q, angle=angle, outcome=outcome)

    def run(self, assignment: int):
        raise UnsupportedOperation("H/HMR has no single basis-state action; use channel_semantics")


# An explicit alias also makes the supported QCEC grammar convenient to discover.
UnitaryProgram = CyclotomicProgram


@dataclass(frozen=True)
class ReferenceLimits:
    max_width: int = 4
    max_hadamards: int = 12
    max_measurements: int = 8
    max_k: int = 8
    max_entries: int = 65_536

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 1 for v in vars(self).values()):
            raise ValueError("reference limits must be positive integers")


def _guarded(guard: Guard) -> None:
    guard.check_time()
    if guard.budget.max_nodes is not None:
        raise ValueError("max_nodes is unsupported by the cyclotomic reference")


def _limit(resource: str, observed: int, limit: int) -> None:
    if observed > limit:
        raise ResourceLimitExceeded(resource, limit, observed)


def _coefficient_guard(value: Cyclotomic, guard: Guard) -> Cyclotomic:
    guard.check_time()
    guard.check_terms(len(value.terms))
    return value


def _product(a: Cyclotomic, b: Cyclotomic, guard: Guard) -> Cyclotomic:
    # Reduce each product as it is formed: no unchecked quadratic temporary tuple.
    degree = 1 << (a.k - 1)
    a._same(b)
    terms: dict[int, Fraction] = {}
    for p, x in a.terms:
        for q, y in b.terms:
            exponent = (p + q) % (2 * degree)
            sign = -1 if exponent >= degree else 1
            exponent %= degree
            terms[exponent] = terms.get(exponent, Fraction()) + sign * x * y
            if not terms[exponent]:
                del terms[exponent]
            guard.check_time()
            guard.check_terms(len(terms))
    return Cyclotomic(a.k, tuple(terms.items()))


def _sum(a: Cyclotomic, b: Cyclotomic, guard: Guard) -> Cyclotomic:
    a._same(b)
    terms = dict(a.terms)
    guard.check_terms(len(terms))
    for power, value in b.terms:
        terms[power] = terms.get(power, Fraction()) + value
        if not terms[power]:
            del terms[power]
        guard.check_time()
        guard.check_terms(len(terms))
    return Cyclotomic(a.k, tuple(terms.items()))


def _accumulate(target, key, value: Cyclotomic, guard: Guard, limits: ReferenceLimits) -> None:
    total = _sum(target.get(key, Cyclotomic(value.k)), value, guard)
    _coefficient_guard(total, guard)
    if total:
        target[key] = total
    else:
        target.pop(key, None)
    _limit("reference entries", len(target), limits.max_entries)
    guard.check_terms(sum(len(v.terms) for v in target.values()))
    guard.check_time()


def _amplitudes(program: CyclotomicProgram, x: int, field_k: int,
                guard: Guard, limits: ReferenceLimits):
    state = {(0, x): Cyclotomic.root(field_k)}
    step = 1 << (field_k - 3)
    inv_sqrt2 = (Cyclotomic.root(field_k, step)
                 - Cyclotomic.root(field_k, 3 * step)).scale(Fraction(1, 2))
    event_index = 0
    for gate in program.gates:
        next_state = {}
        for (events, basis), amplitude in state.items():
            guard.check_time()
            if gate.name in _PERMUTATIONS or gate.name == "mcx":
                *controls, target = gate.wires
                out = basis ^ (1 << target) if all(basis >> q & 1 for q in controls) else basis
                _accumulate(next_state, (events, out), amplitude, guard, limits)
            elif gate.name in {"h", "hmr"}:
                q = gate.wires[0]
                bit = basis >> q & 1
                scaled = _product(amplitude, inv_sqrt2, guard)
                for outcome in (0, 1):
                    value = -scaled if bit and outcome else scaled
                    out = basis & ~(1 << q)
                    if gate.name == "h":
                        out |= outcome << q
                        e = events
                    else:
                        e = events | (outcome << event_index)
                    _accumulate(next_state, (e, out), value, guard, limits)
            else:
                enabled = all(basis >> q & 1 for q in gate.wires)
                if gate.name == "phase_if":
                    enabled = enabled and bool(events >> gate.outcome & 1)
                angle = gate.angle if gate.name in {"phase", "phase_if"} else _PHASES[gate.name]
                exponent = _exponent(angle, program.k) << (field_k - program.k)
                value = _product(amplitude, Cyclotomic.root(field_k, exponent), guard) \
                    if enabled else amplitude
                _accumulate(next_state, (events, basis), value, guard, limits)
        state = next_state
        if gate.name == "hmr":
            event_index += 1
    return state


@dataclass(frozen=True)
class CyclotomicChannel:
    width: int
    k: int
    coefficients: dict[tuple[int, int, int, int], Cyclotomic]

    def coefficient(self, x: int, xp: int, y: int, yp: int) -> Cyclotomic:
        if any(type(v) is not int or not 0 <= v < 1 << self.width for v in (x, xp, y, yp)):
            raise ValueError("channel index outside width")
        return self.coefficients.get((x, xp, y, yp), Cyclotomic(self.k))


@session_scoped
def channel_semantics(program: CyclotomicProgram, budget: Budget | None = None, *,
                      limits: ReferenceLimits | None = None, _guard: Guard | None = None,
                      _field_k: int | None = None) -> CyclotomicChannel:
    """E(|x><x'|)[y,y'] = sum_m K_m[y,x] conjugate(K_m[y',x'])."""
    guard = _guard if _guard is not None else Guard(budget)
    _guarded(guard)
    if type(program) is not CyclotomicProgram:
        raise TypeError("CyclotomicProgram required")
    program.validate()
    limits = limits or ReferenceLimits()
    field_k = max(3, program.k, _field_k or 3)
    _limit("reference width", program.width, limits.max_width)
    _limit("reference k", field_k, limits.max_k)
    _limit("reference Hadamards", sum(g.name == "h" for g in program.gates),
           limits.max_hadamards)
    _limit("reference measurements", sum(g.name == "hmr" for g in program.gates),
           limits.max_measurements)
    columns = []
    for x in range(1 << program.width):
        columns.append(_amplitudes(program, x, field_k, guard, limits))
        guard.check_terms(sum(len(v.terms) for column in columns for v in column.values()))
    coefficients = {}
    for x, a in enumerate(columns):
        for xp, b in enumerate(columns):
            for (event, y), av in a.items():
                for (eventp, yp), bv in b.items():
                    guard.check_time()
                    if event == eventp:
                        value = _product(av, bv.conjugate(), guard)
                        _accumulate(coefficients, (x, xp, y, yp), value, guard, limits)
    guard.check_time()
    return CyclotomicChannel(program.width, field_k, coefficients)


@dataclass(frozen=True)
class ChannelVerdict:
    equivalent: bool
    witness: tuple[int, int, int, int] | None = None
    relation: str = "discarded-outcome quantum channel"


@session_scoped
def check_channel_equivalence(left: CyclotomicProgram, right: CyclotomicProgram,
                              budget: Budget | None = None, *, limits=None,
                              _guard: Guard | None = None) -> ChannelVerdict:
    if type(left) is not CyclotomicProgram or type(right) is not CyclotomicProgram:
        raise TypeError("two CyclotomicProgram objects required")
    if left.width != right.width:
        raise ValueError("width mismatch")
    guard = _guard if _guard is not None else Guard(budget)
    field_k = max(3, left.k, right.k)
    a = channel_semantics(left, budget, limits=limits, _guard=guard, _field_k=field_k)
    b = channel_semantics(right, budget, limits=limits, _guard=guard, _field_k=field_k)
    for key in a.coefficients.keys() | b.coefficients.keys():
        guard.check_time()
        if a.coefficient(*key) != b.coefficient(*key):
            return ChannelVerdict(False, key)
    guard.check_time()
    return ChannelVerdict(True)


@session_scoped
def affine_event_factor(phase: dict[int, int], event_variables: tuple[int, ...],
                        assignment: int = 0, *, k: int = 3, normalize: bool = True,
                        budget: Budget | None = None, _guard: Guard | None = None) -> Cyclotomic:
    """Exact sum/average of zeta**phi for phi affine in event bits.

    phi=a0(x)+sum_j aj(x)mj implies sum_m zeta**phi =
    zeta**a0 product_j(1+zeta**aj). Nonlinear event monomials are refused,
    even if a particular data assignment would annihilate them.
    """
    modulus = _modulus(k)
    guard = _guard if _guard is not None else Guard(budget)
    _guarded(guard)
    if (not isinstance(event_variables, tuple)
            or any(type(v) is not int or v < 0 for v in event_variables)
            or len(set(event_variables)) != len(event_variables)):
        raise ValueError("event variables must be distinct nonnegative indices")
    event_mask = sum(1 << v for v in event_variables)
    if type(assignment) is not int or assignment < 0 or assignment & event_mask:
        raise ValueError("assignment must contain only fixed data bits")
    if type(normalize) is not bool:
        raise ValueError("normalize must be Boolean")
    if not isinstance(phase, dict):
        raise TypeError("sparse phase dictionary required")
    guard.check_terms(len(phase) + len(event_variables))
    coefficients = {1 << v: 0 for v in event_variables}
    constant = 0
    for mask, coefficient in phase.items():
        guard.check_time()
        if type(mask) is not int or mask < 0 or type(coefficient) is not int:
            raise ValueError("phase masks and coefficients must be integers")
        coefficient %= modulus
        if not coefficient:
            continue
        event = mask & event_mask
        if event.bit_count() > 1:
            raise UnsupportedOperation("phase is nonlinear in events; affine factor unavailable")
        data = mask & ~event_mask
        if data & assignment == data:
            if event:
                coefficients[event] = (coefficients[event] + coefficient) % modulus
            else:
                constant = (constant + coefficient) % modulus
    field_k = max(3, k)
    one = Cyclotomic.root(field_k)
    result = Cyclotomic.root(field_k, constant << (field_k - k))
    for coefficient in coefficients.values():
        factor = _sum(one, Cyclotomic.root(field_k, coefficient << (field_k - k)), guard)
        result = _product(result, factor, guard)
        if normalize:
            result = result.scale(Fraction(1, 2))
    return _coefficient_guard(result, guard)
