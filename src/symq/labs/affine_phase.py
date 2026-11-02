"""Source-bound dyadic phase proofs on affine dephasing fibres.

The compared channels are (U_left tensor I_anc) o D and
(U_right tensor I_anc) o D on an explicitly declared affine input support.
D is an actual sign/HMR PhaseProgram, not a supplied signature projection.
All quantum outputs are retained and all measurement outcomes are forgotten.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction

from symq.circuit import UnsupportedOperation
from symq.errors import InternalInconsistency, ResourceLimitExceeded
from symq.labs.dyadic_phase import DyadicGate, DyadicPhaseProgram
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, Guard

BoolPoly = frozenset[int]
PhasePoly = dict[int, int]
_ZERO: BoolPoly = frozenset()
_ONE: BoolPoly = frozenset((0,))
_PERMUTATIONS = {"x", "cx", "ccx", "mcx"}
_ANGLES = {"t": Fraction(1, 8), "tdg": Fraction(-1, 8),
           "s": Fraction(1, 4), "sdg": Fraction(-1, 4),
           "z": Fraction(1, 2), "cz": Fraction(1, 2), "ccz": Fraction(1, 2)}


@dataclass(frozen=True)
class AffineSupport:
    """The coherent span of |offset XOR sum(columns[j] * z_j)>.

    Columns must be linearly independent. The empty tuple denotes a singleton,
    not an empty domain. This declares an input contract, not a preparation proof.
    """

    width: int
    offset: int
    columns: tuple[int, ...]

    @classmethod
    def full(cls, width: int) -> AffineSupport:
        if type(width) is not int or not 1 <= width <= 256:
            raise ValueError("full support width must be an integer in 1..256")
        return cls(width, 0, tuple(1 << i for i in range(width)))


@dataclass(frozen=True)
class DerivativeLimits:
    max_width: int = 256
    max_gates: int = 20_000
    max_measurements: int = 256
    max_receipt_items: int = 20_000

    def __post_init__(self) -> None:
        for name in ("max_width", "max_gates", "max_measurements", "max_receipt_items"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_width > 256:
            raise ValueError("max_width cannot exceed 256")


@dataclass(frozen=True)
class AffinePhaseReceipt:
    source_sha256: str
    phase_sha256: str
    parameter_dimension: int
    k: int
    signature_rows: tuple[int, ...]
    signature_constants: tuple[int, ...]
    kernel_basis: tuple[int, ...]

    def to_dict(self) -> dict:
        return {"schema": "symq.affine-phase/v1", "source_sha256": self.source_sha256,
                "phase_sha256": self.phase_sha256,
                "parameter_dimension": self.parameter_dimension, "k": self.k,
                "signature_rows": list(self.signature_rows),
                "signature_constants": list(self.signature_constants),
                "kernel_basis": list(self.kernel_basis)}


@dataclass(frozen=True)
class AffinePhaseResult:
    status: str
    reason: str
    receipt: AffinePhaseReceipt | None = None
    witness: tuple[int, int] | None = None
    metrics: dict[str, int] = field(default_factory=dict)

    @property
    def equivalent(self) -> bool:
        return self.status == "equivalent"

    @property
    def different(self) -> bool:
        return False


@dataclass(frozen=True)
class _Dyadic:
    width: int
    k: int
    gates: tuple[DyadicGate, ...]


class _Work:
    def __init__(self, guard: Guard):
        self.guard = guard
        self.peak = 0
        self.derivative_terms = 0
        self.skipped_invariant = 0

    def check(self, count: int = 0) -> None:
        self.guard.check_time()
        self.guard.check_terms(count)
        self.peak = max(self.peak, count)


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _cap(name: str, count: int, maximum: int) -> None:
    if count > maximum:
        raise ResourceLimitExceeded(name, maximum, count)


def _limits(value: DerivativeLimits | None) -> DerivativeLimits:
    if value is None:
        return DerivativeLimits()
    if type(value) is not DerivativeLimits:
        raise TypeError("DerivativeLimits required")
    return DerivativeLimits(value.max_width, value.max_gates, value.max_measurements,
                            value.max_receipt_items)


def _guard(value: Budget | None) -> Guard:
    if value is None:
        value = Budget(max_terms=100_000, max_seconds=10.0)
    elif type(value) is not Budget:
        raise TypeError("Budget required")
    else:
        for field_name in ("max_seconds", "absolute_deadline"):
            field_value = getattr(value, field_name)
            if field_value is not None and type(field_value) not in (int, float):
                raise ValueError(f"{field_name} must be an exact int or float")
        value = Budget(value.max_terms, value.max_nodes, value.max_seconds,
                       absolute_deadline=value.absolute_deadline, max_bytes=value.max_bytes)
    guard = Guard(value)
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError("affine phase proofs support term/time budgets, not node/byte budgets")
    return guard


def _freeze_angle(angle: object, work: _Work) -> Fraction | int | None:
    if angle is None:
        return None
    if type(angle) is int:
        _cap("angle_bits", angle.bit_length(), 4096)
        return angle
    if type(angle) is not Fraction:
        raise UnsupportedOperation("exact Fraction/integer phase angle required")
    numerator, denominator = angle.numerator, angle.denominator
    if type(numerator) is not int or type(denominator) is not int or denominator < 1:
        raise UnsupportedOperation("Fraction internals must be exact integers with positive denominator")
    _cap("angle_bits", max(numerator.bit_length(), denominator.bit_length()), 4096)
    frozen = Fraction(numerator, denominator)
    if frozen.numerator != numerator or frozen.denominator != denominator:
        raise UnsupportedOperation("Fraction must have its canonical reduced representation")
    work.check()
    return frozen


def _freeze_dyadic(program: DyadicPhaseProgram, limits: DerivativeLimits, work: _Work) -> _Dyadic:
    if type(program) is not DyadicPhaseProgram:
        raise TypeError("an exact DyadicPhaseProgram is required")
    width, k = program.width, program.k
    if type(width) is not int or width < 1 or type(k) is not int or not 1 <= k <= 64:
        raise ValueError("positive width and k in 1..64 required")
    _cap("width", width, limits.max_width)
    if type(program.gates) is not list:
        raise UnsupportedOperation("gates must be an exact list")
    _cap("gates", len(program.gates), limits.max_gates)
    gates = []
    for gate in program.gates:
        work.check()
        if (type(gate) is not DyadicGate or type(gate.name) is not str
                or type(gate.wires) is not tuple
                or any(type(q) is not int for q in gate.wires)):
            raise UnsupportedOperation("malformed dyadic gate fields")
        fresh = DyadicGate(gate.name, tuple(gate.wires), _freeze_angle(gate.angle, work))
        if any(q >= width for q in fresh.wires):
            raise UnsupportedOperation("dyadic gate wire outside width")
        if fresh.name not in _PERMUTATIONS:
            _exponent(fresh, k)
        gates.append(fresh)
    work.check()
    return _Dyadic(width, k, tuple(gates))


def _freeze_dephaser(program: PhaseProgram, limits: DerivativeLimits,
                     work: _Work) -> tuple[int, int, tuple[Op, ...]]:
    if type(program) is not PhaseProgram:
        raise TypeError("an exact PhaseProgram dephaser is required")
    data, ancillas = program.data, program.ancillas
    if type(data) is not int or data < 1 or type(ancillas) is not int or ancillas < 0:
        raise ValueError("invalid dephaser dimensions")
    _cap("width", data + ancillas, limits.max_width)
    if type(program.ops) is not list:
        raise UnsupportedOperation("dephaser ops must be an exact list")
    _cap("gates", len(program.ops), limits.max_gates)
    ops, events = [], 0
    for op in program.ops:
        work.check()
        if (type(op) is not Op or type(op.kind) is not str or type(op.qubits) is not tuple
                or any(type(q) is not int for q in op.qubits)
                or op.outcome is not None and type(op.outcome) is not int):
            raise UnsupportedOperation("malformed dephaser operation fields")
        if op.kind == "hmr":
            events += 1
            _cap("measurements", events, limits.max_measurements)
        ops.append(Op(op.kind, tuple(op.qubits), op.outcome))
    fresh = PhaseProgram(data, ancillas, ops)
    fresh.validate()
    work.check()
    return data, ancillas, tuple(ops)


def _kernel(rows: tuple[int, ...], width: int, work: _Work) -> tuple[int, ...]:
    pivots: dict[int, int] = {}
    for row in rows:
        work.check()
        reduced = row
        for pivot in sorted(pivots, reverse=True):
            if reduced >> pivot & 1:
                reduced ^= pivots[pivot]
        if reduced:
            pivot = reduced.bit_length() - 1
            for old in tuple(pivots):
                if pivots[old] >> pivot & 1:
                    pivots[old] ^= reduced
            pivots[pivot] = reduced
    basis = []
    for free in range(width):
        if free not in pivots:
            vector = 1 << free
            for pivot, row in pivots.items():
                if row >> free & 1:
                    vector |= 1 << pivot
            basis.append(vector)
        work.check()
    return tuple(basis)


def _freeze_support(value: AffineSupport | None, width: int, work: _Work) -> AffineSupport:
    if value is None:
        value = AffineSupport.full(width)
    if type(value) is not AffineSupport:
        raise TypeError("AffineSupport required")
    if (type(value.width) is not int or value.width != width
            or type(value.offset) is not int or not 0 <= value.offset < (1 << width)
            or type(value.columns) is not tuple or len(value.columns) > width
            or any(type(c) is not int or not 0 < c < (1 << width) for c in value.columns)):
        raise ValueError("invalid affine support dimensions, offset or columns")
    columns = tuple(value.columns)
    # Column independence is checked as row independence after transposition.
    rows = tuple(sum(((c >> q) & 1) << j for j, c in enumerate(columns))
                 for q in range(width))
    if _kernel(rows, len(columns), work):
        raise ValueError("affine support columns must be linearly independent")
    return AffineSupport(width, value.offset, columns)


def _inputs(support: AffineSupport) -> list[BoolPoly]:
    return [frozenset(([0] if support.offset >> q & 1 else [])
                      + [1 << j for j, c in enumerate(support.columns) if c >> q & 1])
            for q in range(support.width)]


def _xor(left: BoolPoly, right: BoolPoly, work: _Work) -> BoolPoly:
    result = left ^ right
    work.check(len(result))
    return result


def _product(values: list[BoolPoly], work: _Work) -> BoolPoly:
    value = _ONE
    for right in values:
        result: set[int] = set()
        for a in value:
            for b in right:
                mask = a | b
                if mask in result:
                    result.remove(mask)
                else:
                    result.add(mask)
                work.check(len(result))
        value = frozenset(result)
    return value


def _add_term(out: PhasePoly, mask: int, coefficient: int, modulus: int, work: _Work) -> None:
    value = (out.get(mask, 0) + coefficient) % modulus
    if value:
        out[mask] = value
    else:
        out.pop(mask, None)
    work.check(len(out))


def _lift(value: BoolPoly, coefficient: int, modulus: int, work: _Work) -> PhasePoly:
    """Lift coefficient * parity, eliminating modular zeros during expansion."""
    result: PhasePoly = {}
    for mask in sorted(value):
        old = tuple(result.items())
        _add_term(result, mask, coefficient, modulus, work)
        for other, previous in old:
            _add_term(result, mask | other, -2 * previous, modulus, work)
    return result


def _exponent(gate: DyadicGate, k: int) -> int:
    angle = gate.angle if gate.name == "phase" else _ANGLES[gate.name]
    if type(angle) not in (int, Fraction):
        raise UnsupportedOperation("exact Fraction/integer phase angle required")
    scaled = angle * (1 << k)
    if type(scaled) is Fraction and scaled.denominator != 1:
        raise UnsupportedOperation("angle denominator must divide 2**k")
    return int(scaled) % (1 << k)


def _dyadic_semantics(program: _Dyadic, initial: list[BoolPoly], k: int, work: _Work,
                      need_phase: bool) -> tuple[list[BoolPoly], dict[BoolPoly, int]]:
    state, phase, modulus = list(initial), {}, 1 << k
    for gate in program.gates:
        work.check()
        if not need_phase and gate.name not in _PERMUTATIONS:
            continue
        wires = gate.wires[:-1] if gate.name in _PERMUTATIONS else gate.wires
        value = _product([state[q] for q in wires], work)
        if gate.name in _PERMUTATIONS:
            target = gate.wires[-1]
            state[target] = _xor(state[target], value, work)
        else:
            coefficient = (phase.get(value, 0) + _exponent(gate, k)) % modulus
            if coefficient and value:
                phase[value] = coefficient
            else:
                phase.pop(value, None)
        work.check(sum(map(len, phase)) + sum(map(len, state)))
    return state, phase


def _dephasing_semantics(source: tuple[int, int, tuple[Op, ...]], initial: list[BoolPoly],
                         work: _Work) -> tuple[list[BoolPoly], list[BoolPoly]]:
    _, ancillas, ops = source
    state, signature = list(initial) + [_ZERO] * ancillas, []
    for op in ops:
        work.check()
        if op.kind == "mcx":
            target = op.qubits[-1]
            value = _product([state[q] for q in op.qubits[:-1]], work)
            state[target] = _xor(state[target], value, work)
        elif op.kind == "hmr":
            signature.append(state[op.qubits[0]])
            state[op.qubits[0]] = _ZERO
        elif op.kind == "mcz_if":
            assert op.outcome is not None  # validated on a fresh source snapshot
            value = _product([state[q] for q in op.qubits], work)
            signature[op.outcome] = _xor(signature[op.outcome], value, work)
        # Unconditional sign phases are common to both compared channels and cancel.
        work.check(sum(map(len, state)) + sum(map(len, signature)))
    return state, signature


def _translate(value: BoolPoly, direction: int, work: _Work) -> BoolPoly:
    """Substitute z XOR direction in a Boolean ANF without modular lifting."""
    out: set[int] = set()
    for mask in value:
        changed = mask & direction
        fixed, subset = mask ^ changed, changed
        while True:
            term = fixed | subset
            if term in out:
                out.remove(term)
            else:
                out.add(term)
            work.check(len(out))
            work.derivative_terms += 1
            if not subset:
                break
            subset = (subset - 1) & changed
    return frozenset(out)


def _derivative(phase: dict[BoolPoly, int], direction: int, k: int,
                work: _Work) -> PhasePoly:
    """Directional derivative; invariant gate predicates never enter a modular lift."""
    out, modulus = {}, 1 << k
    for value, coefficient in phase.items():
        translated = _translate(value, direction, work)
        if translated == value:
            work.skipped_invariant += 1
            continue
        for mask, term in _lift(translated, coefficient, modulus, work).items():
            _add_term(out, mask, term, modulus, work)
        for mask, term in _lift(value, -coefficient, modulus, work).items():
            _add_term(out, mask, term, modulus, work)
    return out


def _ambient(support: AffineSupport, z: int) -> int:
    value = support.offset
    for j, column in enumerate(support.columns):
        if z >> j & 1:
            value ^= column
    return value


def _run(program: _Dyadic, assignment: int, k: int) -> tuple[int, int]:
    """Concrete replay, using integer gates rather than symbolic polynomials."""
    state, phase = assignment, 0
    for gate in program.gates:
        if gate.name in _PERMUTATIONS:
            if all(state >> q & 1 for q in gate.wires[:-1]):
                state ^= 1 << gate.wires[-1]
        elif all(state >> q & 1 for q in gate.wires):
            phase += _exponent(gate, k)
    return state, phase % (1 << k)


def _source_document(program: _Dyadic) -> dict:
    return {"width": program.width, "k": program.k,
            "gates": [[g.name, list(g.wires), None if g.angle is None else
                       [Fraction(g.angle).numerator, Fraction(g.angle).denominator]]
                      for g in program.gates]}


def _check(left: DyadicPhaseProgram, right: DyadicPhaseProgram, dephaser: PhaseProgram,
           support: AffineSupport | None, limits: DerivativeLimits | None,
           guard: Guard) -> AffinePhaseResult:
    limits, work = _limits(limits), _Work(guard)
    a, b = _freeze_dyadic(left, limits, work), _freeze_dyadic(right, limits, work)
    source = _freeze_dephaser(dephaser, limits, work)
    if a.width != b.width or a.width != source[0]:
        raise ValueError("dyadic widths must equal the dephaser data width")
    domain = _freeze_support(support, a.width, work)
    initial = _inputs(domain)
    work.check(sum(map(len, initial)))
    dephased, signatures = _dephasing_semantics(source, initial, work)
    if dephased != initial + [_ZERO] * source[1]:
        return AffinePhaseResult("not_proved", "dephaser must restore (input data, zero ancillas)")
    if any(mask.bit_count() > 1 for value in signatures for mask in value):
        return AffinePhaseResult("not_proved", "dephaser signature is not affine on this support")
    rows = tuple(sum(mask for mask in value if mask) for value in signatures)
    constants = tuple(int(0 in value) for value in signatures)
    dimension, k = len(domain.columns), max(a.k, b.k)
    basis = _kernel(rows, dimension, work)
    out_a, phase_a = _dyadic_semantics(a, initial, k, work, bool(basis))
    out_b, phase_b = _dyadic_semantics(b, initial, k, work, bool(basis))
    metrics = {"parameter_dimension": dimension, "signature_rows": len(rows),
               "signature_rank": dimension - len(basis), "kernel_dimension": len(basis),
               "source_gates": len(a.gates) + len(b.gates) + len(source[2]),
               "singleton_fibres": int(not basis)}
    for x, y in zip(out_a, out_b):
        if x != y:
            z = min(x ^ y, key=lambda mask: (mask.bit_count(), mask))
            witness = _ambient(domain, z)
            if _run(a, witness, k)[0] == _run(b, witness, k)[0]:
                raise InternalInconsistency("output counterexample failed concrete replay")
            return AffinePhaseResult("not_proved", "output functions differ on the support",
                                     witness=(witness, witness), metrics=metrics)
    delta = dict(phase_a)
    for value, coefficient in phase_b.items():
        new = (delta.get(value, 0) - coefficient) % (1 << k)
        if new:
            delta[value] = new
        else:
            delta.pop(value, None)
        work.check(sum(map(len, delta)))
    metrics["phase_predicates"] = len(delta)
    for direction in basis:
        derivative = _derivative(delta, direction, k, work)
        if derivative:
            z = min(derivative, key=lambda mask: (mask.bit_count(), mask))
            x, y = _ambient(domain, z), _ambient(domain, z ^ direction)
            dx = (_run(a, x, k)[1] - _run(b, x, k)[1]) % (1 << k)
            dy = (_run(a, y, k)[1] - _run(b, y, k)[1]) % (1 << k)
            if dx == dy:
                raise InternalInconsistency("phase counterexample failed concrete replay")
            metrics.update(peak_terms=work.peak, derivative_terms=work.derivative_terms,
                           skipped_invariant_contributions=work.skipped_invariant)
            return AffinePhaseResult("not_proved", "relative phase varies on a coherence fibre",
                                     witness=(x, y), metrics=metrics)
    identity = {"left": _source_document(a), "right": _source_document(b),
                "dephaser": [source[0], source[1],
                             [[op.kind, list(op.qubits), op.outcome] for op in source[2]]],
                "support": [domain.width, domain.offset, list(domain.columns)]}
    phase_document = {"singleton_fibres": not basis,
                      "weighted_predicates": sorted((sorted(value), c) for value, c in delta.items())}
    receipt = AffinePhaseReceipt(_hash(identity), _hash(phase_document), dimension, k,
                                rows, constants, basis)
    _validate_document(receipt.to_dict(), limits, work)
    metrics.update(peak_terms=work.peak, derivative_terms=work.derivative_terms,
                   skipped_invariant_contributions=work.skipped_invariant)
    return AffinePhaseResult("equivalent", "all kernel-basis phase derivatives vanish",
                             receipt, metrics=metrics)


def _validate_document(document: object, limits: DerivativeLimits, work: _Work) -> None:
    count = 0

    def visit(value: object, depth: int) -> None:
        nonlocal count
        count += 1
        work.check()
        _cap("receipt_items", count, limits.max_receipt_items)
        if depth > 8:
            raise ValueError("receipt nesting is too deep")
        if type(value) is int:
            if value < 0 or value.bit_length() > 256:
                raise ValueError("receipt integer outside supported range")
        elif type(value) is str:
            if len(value) > 128:
                raise ValueError("receipt string is too long")
        elif type(value) is list:
            _cap("receipt_items", len(value), limits.max_receipt_items)
            for item in value:
                visit(item, depth + 1)
        elif type(value) is dict:
            _cap("receipt_items", len(value), limits.max_receipt_items)
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("receipt keys must be exact strings")
                visit(key, depth + 1)
                visit(item, depth + 1)
        else:
            raise ValueError("receipt values must be plain JSON integers, strings, lists or objects")

    if type(document) is not dict:
        raise ValueError("receipt must be a plain JSON object")
    visit(document, 0)


def check_affine_phase(left: DyadicPhaseProgram, right: DyadicPhaseProgram,
                       dephaser: PhaseProgram, *, support: AffineSupport | None = None,
                       budget: Budget | None = None,
                       limits: DerivativeLimits | None = None) -> AffinePhaseResult:
    """Prove channel equality after an actual affine dephaser on declared support.

    U programs act on D.data wires, extended by identity on D's retained ancillas.
    Source/setting errors raise; unsupported semantic obligations return not_proved.
    Resource exhaustion returns inconclusive, never a receipt or a difference claim.
    """
    guard = _guard(budget)
    try:
        guard.check_time()
        result = _check(left, right, dephaser, support, limits, guard)
        # _check owns and releases all large symbolic/source temporaries before this check.
        guard.check_time()
        return result
    except ResourceLimitExceeded as error:
        return AffinePhaseResult("inconclusive", str(error))


def replay_affine_phase(left: DyadicPhaseProgram, right: DyadicPhaseProgram,
                        dephaser: PhaseProgram, document: object, *,
                        support: AffineSupport | None = None, budget: Budget | None = None,
                        limits: DerivativeLimits | None = None) -> AffinePhaseResult:
    """Recompute from current sources and compare the complete canonical JSON receipt."""
    guard = _guard(budget)
    try:
        frozen_limits = _limits(limits)
        work = _Work(guard)
        try:
            _validate_document(document, frozen_limits, work)
        except ValueError as error:
            return AffinePhaseResult("not_proved", f"invalid receipt: {error}")
        # Only plain, bounded JSON remains; copying detaches the caller's mutable document.
        detached = json.loads(json.dumps(document))
        try:
            _validate_document(detached, frozen_limits, work)
        except ValueError as error:
            return AffinePhaseResult("not_proved", f"invalid detached receipt: {error}")
        result = _check(left, right, dephaser, support, frozen_limits, guard)
        if result.receipt is None or result.receipt.to_dict() != detached:
            result = AffinePhaseResult("not_proved", "receipt does not match a fresh source proof")
        guard.check_time()
        return result
    except ResourceLimitExceeded as error:
        return AffinePhaseResult("inconclusive", str(error))
