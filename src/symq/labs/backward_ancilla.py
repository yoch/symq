"""Exact, bounded clean-ancilla proofs by backward propagation of one observable.

The input is a real ``HybridProgram``: arbitrary coherent data, all ancillas |0>.
The result concerns the final value of one declared ancilla, not preservation of
the data channel, a borrowed dirty wire, or permission to remove a reset.

Operators are sparse sums of real Pauli words X**x Z**z and classical parity
characters. Coefficients are exact Fractions; XZ is real and anti-Hermitian,
so no floating-point or implicit complex phase convention is used.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from fractions import Fraction

from symq.circuit import UnsupportedOperation
from symq.errors import InternalInconsistency
from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.resource_report import resource_report
from symq.resources import Budget, Guard, ResourceLimitExceeded

_VERSION = "symq-backward-clean-ancilla-v1"
_SLOT = re.compile(r"b(0|[1-9][0-9]*)\Z")
_ARITY = {"x": 1, "cx": 2, "ccx": 3, "swap": 2, "cswap": 3,
          "z": 1, "cz": 2, "ccz": 3, "neg": 0,
          "hmr": 1, "measure_z": 1, "reset": 1}
_GATES = {"x", "cx", "ccx", "mcx", "swap", "cswap", "z", "cz", "ccz", "neg"}
_KINDS = _GATES | {"hmr", "measure_z", "reset", "store", "invert", "oxor"}
# (quantum X mask, quantum Z mask, classical-character mask)
Word = tuple[int, int, int]
Observable = dict[Word, Fraction]


@dataclass(frozen=True)
class AncillaLimits:
    """Structural/work caps, additional to the explicit term/time Budget.

    ``max_products`` counts elementary Pauli products across the complete call.
    Limits apply before expansion. They do not bound process RSS or interpreter
    scheduling delay. Unsupported node/byte budgets are refused.
    """

    max_width: int = 256
    max_operations: int = 10000
    max_classical_slots: int = 256
    max_gate_qubits: int = 12
    max_products: int = 1000000

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class AncillaCertificate:
    """Portable execution receipt; only a fresh replay establishes its claim."""

    source_sha256: str
    data: int
    ancillas: int
    target: int
    operations: int
    theorem: str = _VERSION

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class AncillaWitness:
    """A computational-basis data input with strictly positive error probability."""

    assignment: int
    probability: Fraction


@dataclass(frozen=True)
class AncillaResult:
    status: str
    certificate: AncillaCertificate | None = None
    witness: AncillaWitness | None = None
    reason: str | None = None
    peak_terms: int | None = None
    pauli_products: int | None = None
    checked_operations: int | None = None
    resource: str | None = None
    """For ``inconclusive``: the limit reached, its value, the count when the engine
    stopped, which parameter controls it, and the limits of the call
    (``symq.labs.resource_report``). The counters above are then the work done so far."""
    limit: float | None = None
    observed: float | None = None
    hint: str | None = None
    limits: dict | None = None

    @property
    def clean(self) -> bool:
        return self.status == "clean"


@dataclass(frozen=True)
class _Source:
    data: int
    ancillas: int
    ops: tuple[HOp, ...]
    slots: tuple[str, ...]
    sha256: str


class _Work:
    def __init__(self, guard: Guard, limits: AncillaLimits):
        self.guard, self.limits = guard, limits
        self.peak_terms = self.products = self.operations = 0

    def size(self, count: int) -> None:
        self.guard.check_time()
        self.guard.check_terms(count)
        self.peak_terms = max(self.peak_terms, count)

    def product(self) -> None:
        self.guard.check_time()
        self.products += 1
        if self.products > self.limits.max_products:
            raise ResourceLimitExceeded("pauli_products", self.limits.max_products, self.products)


def _settings(budget: Budget | None, limits: AncillaLimits | None) -> tuple[Guard, AncillaLimits]:
    if budget is not None and type(budget) is not Budget:
        raise TypeError("Budget or None required")
    if budget is None:
        budget = Budget(max_terms=4096)
    for name in ("max_seconds", "absolute_deadline"):
        value = getattr(budget, name)
        if value is not None and type(value) not in (int, float):
            raise ValueError(f"{name} must have the exact int or float type")
    budget = Budget(**{name: getattr(budget, name) for name in Budget.__dataclass_fields__})
    guard = Guard(budget)
    if guard.budget.max_nodes is not None or guard.budget.max_bytes is not None:
        raise ValueError("node/byte budgets are unsupported by the sparse observable engine")
    if limits is None:
        limits = AncillaLimits()
    if type(limits) is not AncillaLimits:
        raise TypeError("AncillaLimits required")
    limits = AncillaLimits(**{name: getattr(limits, name) for name in AncillaLimits.__dataclass_fields__})
    return guard, limits


def _limits(guard: Guard, limits: AncillaLimits) -> dict:
    """The limits a call runs with, for its resource report."""
    return {"max_terms": guard.budget.max_terms, "max_seconds": guard.budget.max_seconds,
            "absolute_deadline": guard.budget.absolute_deadline,
            **{name: getattr(limits, name) for name in AncillaLimits.__dataclass_fields__}}


def _counted(work: object, counters: dict) -> None:
    """Copy the integer counters of ``work`` out, so that ``work`` itself can be released."""
    counters.update((name, value) for name, value in vars(work).items() if type(value) is int)


def _inconclusive(error: ResourceLimitExceeded, guard: Guard, limits: AncillaLimits) -> dict:
    """The ``reason`` and resource report of an ``inconclusive`` result."""
    return {"reason": str(error), **resource_report(error, _limits(guard, limits))}


def _cap(name: str, observed: int, limit: int) -> None:
    if observed > limit:
        raise ResourceLimitExceeded(name, limit, observed)


def _freeze(program: HybridProgram, target: int, work: _Work) -> _Source:
    """Copy primitive fields before validating; do not trust frozen dataclass labels."""
    guard, limits = work.guard, work.limits
    guard.check_time()
    if type(program) is not HybridProgram:
        raise TypeError("HybridProgram required")
    data, ancillas = program.data, program.ancillas
    if type(data) is not int or data < 1 or type(ancillas) is not int or ancillas < 0:
        raise ValueError("positive data width and nonnegative ancilla count required")
    width = data + ancillas
    _cap("width", width, limits.max_width)
    if type(target) is not int or not data <= target < width:
        raise ValueError("target must be a declared ancilla wire")
    if type(program.ops) is not list:
        raise UnsupportedOperation("ops must have the exact list type")
    _cap("operations", len(program.ops), limits.max_operations)
    copied = tuple(program.ops)
    _cap("operations", len(copied), limits.max_operations)
    ops: list[HOp] = []
    initialized: set[str] = set()
    names: set[str] = set()
    for original in copied:
        guard.check_time()
        if type(original) is not HOp:
            raise UnsupportedOperation("exact HOp instances required")
        kind, wires = original.kind, original.wires
        slot, condition, source, value = (original.slot, original.condition,
                                          original.source, original.value)
        if type(kind) is not str or kind not in _KINDS:
            raise UnsupportedOperation("operation outside the closed hybrid fragment")
        if type(wires) is not tuple or any(type(q) is not int or not 0 <= q < width
                                          for q in wires) or len(set(wires)) != len(wires):
            raise UnsupportedOperation("distinct in-range exact integer wire tuple required")
        arity = _ARITY.get(kind)
        if arity is not None and len(wires) != arity or kind == "mcx" and len(wires) < 2:
            raise UnsupportedOperation("incorrect gate arity")
        _cap("gate_qubits", len(wires), limits.max_gate_qubits)
        for token in (slot, source, condition):
            if token is not None and (type(token) is not str or len(token) > 64):
                raise UnsupportedOperation("bounded exact string slot/condition required")
        for token in (slot, source):
            if token is not None and _SLOT.fullmatch(token) is None:
                raise UnsupportedOperation("canonical b0, b1, ... slot names required")
        if value is not None and (type(value) is not int or value not in (0, 1)):
            raise UnsupportedOperation("store values must have exact bit type")
        if condition is not None:
            name = condition.removeprefix("!")
            if not _SLOT.fullmatch(name) or name not in initialized:
                raise UnsupportedOperation("condition must read an initialized slot")
        if source is not None and source not in initialized:
            raise UnsupportedOperation("source must read an initialized slot")
        if kind in _GATES | {"hmr", "measure_z", "reset"}:
            if source is not None or value is not None:
                raise UnsupportedOperation("extraneous quantum arguments")
            if kind in {"hmr", "measure_z"}:
                if slot is None or condition is not None:
                    raise UnsupportedOperation("unconditional measurement needs an output slot")
                initialized.add(slot)
            elif slot is not None or kind == "reset" and condition is not None:
                raise UnsupportedOperation("extraneous quantum slot/condition")
        else:
            if wires or slot is None or kind != "invert" and condition is not None:
                raise UnsupportedOperation("malformed classical operation")
            if kind == "store":
                if source is not None or value is None:
                    raise UnsupportedOperation("store needs exactly a constant bit")
                initialized.add(slot)
            elif kind == "invert":
                if slot not in initialized or source is not None or value is not None:
                    raise UnsupportedOperation("invert needs an initialized slot")
            elif slot not in initialized or source is None or value is not None:
                raise UnsupportedOperation("oxor needs two initialized slots")
        for name in (slot, source, condition.removeprefix("!") if condition else None):
            if name is not None:
                names.add(name)
        _cap("classical_slots", len(names), limits.max_classical_slots)
        ops.append(HOp(kind, tuple(wires), slot, condition, source, value))
    # The fresh validated snapshot has no references to the original operation objects.
    rows = [[op.kind, list(op.wires), op.slot, op.condition, op.source, op.value] for op in ops]
    raw = json.dumps({"data": data, "ancillas": ancillas, "ops": rows},
                     sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    guard.check_time()
    return _Source(data, ancillas, tuple(ops), tuple(sorted(names)), digest)


def _put(out: Observable, word: Word, coefficient: Fraction, work: _Work) -> None:
    if coefficient:
        value = out.get(word, Fraction(0)) + coefficient
        if value:
            out[word] = value
        else:
            out.pop(word, None)
    work.size(len(out))


def _mul_word(a: Word, b: Word) -> tuple[Word, int]:
    return (a[0] ^ b[0], a[1] ^ b[1], a[2] ^ b[2]), (-1 if (a[1] & b[0]).bit_count() & 1 else 1)


def _multiply(left: Observable, right: Observable, work: _Work) -> Observable:
    out: Observable = {}
    for a, ca in left.items():
        for b, cb in right.items():
            work.product()
            word, sign = _mul_word(a, b)
            _put(out, word, ca * cb * sign, work)
    return out


def _gate_operator(op: HOp, work: _Work) -> Observable:
    """Exact self-adjoint unitary expansion; all accepted gates are involutions."""
    if op.kind == "neg":
        return {(0, 0, 0): Fraction(-1)}
    if op.kind in {"swap", "cswap"}:
        a, b = op.wires[-2:]
        mask = (1 << a) | (1 << b)
        swap = {(0, 0, 0): Fraction(1, 2), (mask, 0, 0): Fraction(1, 2),
                (0, mask, 0): Fraction(1, 2), (mask, mask, 0): Fraction(-1, 2)}
        work.size(len(swap))
        if op.kind == "swap":
            return swap
        c = 1 << op.wires[0]
        projector = {(0, 0, 0): Fraction(1, 2), (0, c, 0): Fraction(-1, 2)}
        swap[(0, 0, 0)] -= 1
        out = _multiply(projector, swap, work)
        _put(out, (0, 0, 0), Fraction(1), work)
        return out
    if op.kind in {"x", "cx", "ccx", "mcx"}:
        controls, target = op.wires[:-1], 1 << op.wires[-1]
        scale, phase_gate = Fraction(1, 1 << len(controls)), False
    else:
        controls, target = op.wires, 0
        scale, phase_gate = Fraction(-2, 1 << len(controls)), True
    _cap("gate_terms", (1 << len(controls)) * (1 if phase_gate else 2),
         work.guard.budget.max_terms or (1 << (work.limits.max_gate_qubits + 1)))
    out = {(0, 0, 0): Fraction(1)}
    for subset in range(1 << len(controls)):
        work.guard.check_time()
        z = sum((1 << q) for i, q in enumerate(controls) if subset >> i & 1)
        coeff = -scale if subset.bit_count() & 1 else scale
        if phase_gate:
            _put(out, (0, z, 0), coeff, work)
        else:
            _put(out, (target, z, 0), coeff, work)
            _put(out, (0, z, 0), -coeff, work)
    return out


def _conjugate(observable: Observable, op: HOp, work: _Work) -> Observable:
    if op.kind == "neg" or not observable:
        return observable
    affected = sum(1 << q for q in op.wires)
    active = {word: c for word, c in observable.items() if (word[0] | word[1]) & affected}
    if not active:
        return observable
    idle = {word: c for word, c in observable.items() if word not in active}
    unitary = _gate_operator(op, work)
    changed = _multiply(_multiply(unitary, active, work), unitary, work)
    for word, c in idle.items():
        _put(changed, word, c, work)
    return changed


def _gate_pullback(observable: Observable, op: HOp, slots: dict[str, int],
                   work: _Work) -> Observable:
    changed = _conjugate(observable, op, work)
    if op.condition is None or changed == observable:
        return changed
    bit = slots[op.condition.removeprefix("!")]
    # A positive condition applies U on c=1: (I+Zc)O/2 + (I-Zc)U*OU/2.
    sign = -1 if op.condition.startswith("!") else 1
    out: Observable = {}
    for source, branch in ((observable, sign), (changed, -sign)):
        for (x, z, c), coefficient in source.items():
            _put(out, (x, z, c), coefficient / 2, work)
            _put(out, (x, z, c ^ bit), branch * coefficient / 2, work)
    return out


def _pullback(observable: Observable, op: HOp, slots: dict[str, int],
              work: _Work) -> Observable:
    work.guard.check_time()
    work.operations += 1
    if op.kind in _GATES:
        return _gate_pullback(observable, op, slots, work)
    out: Observable = {}
    qbit = (1 << op.wires[0]) if op.wires else 0
    cbit = slots[op.slot] if op.slot is not None else 0
    for (x, z, c), coefficient in observable.items():
        work.guard.check_time()
        if op.kind in {"hmr", "measure_z", "reset"}:
            if x & qbit:
                continue
            selected = bool(c & cbit)
            c &= ~cbit
            if op.kind in {"reset", "hmr"}:
                z &= ~qbit
            if selected:
                if op.kind == "hmr":
                    x ^= qbit
                else:  # Z measurement: output character pulls back to Z_q.
                    z ^= qbit
        elif c & cbit:
            if op.kind == "store":
                c ^= cbit
                coefficient *= -1 if op.value else 1
            elif op.kind == "invert":
                if op.condition is None:
                    coefficient = -coefficient
                else:
                    c ^= slots[op.condition.removeprefix("!")]
                    if op.condition.startswith("!"):
                        coefficient = -coefficient
            else:  # parity characters multiply, including oxor(b0, b0).
                c ^= slots[op.source]
        _put(out, (x, z, c), coefficient, work)
    return out


def _effect(source: _Source, target: int, work: _Work) -> Observable:
    observable = {(0, 0, 0): Fraction(1, 2), (0, 1 << target, 0): Fraction(-1, 2)}
    work.size(len(observable))
    slots = {name: 1 << i for i, name in enumerate(source.slots)}
    for op in reversed(source.ops):
        observable = _pullback(observable, op, slots, work)
    data_mask = (1 << source.data) - 1
    reduced: Observable = {}
    for (x, z, c), coefficient in observable.items():
        work.guard.check_time()
        if c:
            raise InternalInconsistency("backward propagation left an uninitialized classical input")
        if x & ~data_mask:
            continue  # <0|X|0> and <0|XZ|0> vanish.
        _put(reduced, (x, z & data_mask, 0), coefficient, work)
    if any((x & z).bit_count() & 1 for x, z, _ in reduced):
        raise InternalInconsistency("the final error effect is not real symmetric")
    return reduced


def _witness(effect: Observable, data: int, work: _Work) -> AncillaWitness:
    """Positive effect => positive trace => a basis witness via conditional averages."""
    diagonal = {z: coefficient for (x, z, _), coefficient in effect.items() if not x}
    average = diagonal.get(0, Fraction(0))
    if average <= 0:
        raise InternalInconsistency("a nonzero positive effect must have positive normalized trace")
    assignment = assigned = 0
    for q in range(data):
        assigned |= 1 << q
        zero = Fraction(0)
        for z, coefficient in diagonal.items():
            work.guard.check_time()
            if not z & ~assigned:
                zero += coefficient * (-1 if (z & assignment).bit_count() & 1 else 1)
        if not 0 <= zero <= 1 or not 0 <= 2 * average - zero <= 1:
            raise InternalInconsistency("conditional error probabilities lie outside [0,1]")
        if zero > 0:
            average = zero
        else:
            assignment |= 1 << q
            average = 2 * average - zero
        if average <= 0:
            raise InternalInconsistency("conditional averaging lost the positive witness")
    if average > 1:
        raise InternalInconsistency("ancilla error probability exceeds one")
    work.guard.check_time()
    return AncillaWitness(assignment, average)


def _receipt(value: AncillaCertificate | dict, guard: Guard) -> AncillaCertificate:
    guard.check_time()
    if type(value) is AncillaCertificate:
        value = {name: getattr(value, name) for name in AncillaCertificate.__dataclass_fields__}
    fields = set(AncillaCertificate.__dataclass_fields__)
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != fields:
        raise ValueError("closed versioned certificate schema required")
    for name in ("data", "ancillas", "target", "operations"):
        if type(value[name]) is not int or value[name] < 0:
            raise ValueError("certificate dimensions and counts must be exact nonnegative integers")
    if not value["data"] or not value["data"] <= value["target"] < value["data"] + value["ancillas"]:
        raise ValueError("certificate target must be a declared ancilla")
    if type(value["theorem"]) is not str or value["theorem"] != _VERSION:
        raise ValueError("unknown certificate theorem")
    digest = value["source_sha256"]
    if type(digest) is not str or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ValueError("canonical source SHA-256 required")
    return AncillaCertificate(**value)


def _calculate(program: HybridProgram, target: int, guard: Guard, limits: AncillaLimits,
               counters: dict, supplied: AncillaCertificate | None = None) -> AncillaResult:
    # Every potentially large temporary is owned here and released before the public
    # final deadline check. A result retains only a tiny receipt or one input witness;
    # ``counters`` receives the work counters, for a report on exhaustion.
    work = _Work(guard, limits)
    try:
        source = _freeze(program, target, work)
        expected = AncillaCertificate(source.sha256, source.data, source.ancillas,
                                      target, len(source.ops))
        if supplied is not None and supplied != expected:
            return AncillaResult("not_proved", reason="certificate_source_mismatch")
        effect = _effect(source, target, work)
        witness = _witness(effect, source.data, work) if effect else None
        return AncillaResult("not_clean" if effect else "clean",
                             expected if not effect else None, witness, None,
                             work.peak_terms, work.products, work.operations)
    finally:
        _counted(work, counters)


def check_clean_ancilla(program: HybridProgram, target: int, *, budget: Budget | None = None,
                        limits: AncillaLimits | None = None) -> AncillaResult:
    """Prove the target is always |0>, or exhibit a basis input with positive error.

    ``clean`` covers arbitrary coherent data and entangled reference systems.
    ``not_clean`` includes an exact positive-probability basis witness.
    Exhaustion returns ``inconclusive`` without a certificate or witness.
    Unsupported/malformed source and settings raise an explicit exception.
    """
    guard, limits = _settings(budget, limits)
    counters: dict = {}
    try:
        result = _calculate(program, target, guard, limits, counters)
        guard.check_time()
        return result
    except ResourceLimitExceeded as error:
        return _exhausted(error, guard, limits, counters)


def _exhausted(error: ResourceLimitExceeded, guard: Guard, limits: AncillaLimits,
               counters: dict) -> AncillaResult:
    return AncillaResult("inconclusive", peak_terms=counters.get("peak_terms"),
                         pauli_products=counters.get("products"),
                         checked_operations=counters.get("operations"),
                         **_inconclusive(error, guard, limits))


def replay_clean_ancilla(program: HybridProgram, certificate: AncillaCertificate | dict, *,
                         target: int | None = None,
                         budget: Budget | None = None,
                         limits: AncillaLimits | None = None) -> AncillaResult:
    """Freshly reconstruct and prove the exact source/target obligation in a receipt.

    The source hash binds the program, not the target: with ``target=None`` the
    receipt's own target is re-proved from scratch. A consumer that relies on a
    particular ancilla must pass ``target=``; a receipt naming another target is
    then refused as ``not_proved`` (``certificate_target_mismatch``).
    """
    guard, limits = _settings(budget, limits)
    counters: dict = {}
    try:
        try:
            supplied = _receipt(certificate, guard)
            if target is not None and (type(target) is not int or target < 0):
                raise TypeError("target must be an exact nonnegative integer")
        except (TypeError, ValueError):
            guard.check_time()
            return AncillaResult("not_proved", reason="malformed_certificate")
        if target is not None and supplied.target != target:
            guard.check_time()
            return AncillaResult("not_proved", reason="certificate_target_mismatch")
        result = _calculate(program, supplied.target, guard, limits, counters, supplied)
        guard.check_time()
        return result
    except ResourceLimitExceeded as error:
        return _exhausted(error, guard, limits, counters)
