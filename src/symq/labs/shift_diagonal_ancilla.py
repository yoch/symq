"""Exact Boolean-first / shift-diagonal clean-ancilla research prototype.

Pinned dependency: backward_ancilla at 539cf60f7f1add1cc478358a77d73ad2b243d6c4
(PR #145, re-pinned for its resource reports; see the research guide).
No published checker is modified. This prototype shares strict source freezing
and input caps with that checker, but does not share its observable algebra.

O|u,b> = sum_s f_s(u,b)|u xor s,b>. The f_s are canonical multilinear rational
polynomials in Boolean bits. Before a relevant HMR, a Boolean diagonal effect
is kept in ANF instead. No term is truncated, and all conversions are budgeted.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from symq.errors import InternalInconsistency
from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs import backward_ancilla as baseline
from symq.resources import Budget, Guard, ResourceLimitExceeded

Poly = dict[int, Fraction]
Shifts = dict[int, Poly]


@dataclass(frozen=True)
class ShiftDiagonalResult:
    status: str
    source_sha256: str | None = None
    assignment: int | None = None
    probability: Fraction | None = None
    reason: str | None = None
    mode: str | None = None
    peak_terms: int | None = None
    peak_shifts: int | None = None
    products: int | None = None
    promotions: int | None = None
    checked_operations: int | None = None
    resource: str | None = None
    """For ``inconclusive``: as in ``backward_ancilla.AncillaResult``; the counters above
    are then the work done so far."""
    limit: float | None = None
    observed: float | None = None
    hint: str | None = None
    limits: dict | None = None


class Work:
    def __init__(self, guard: Guard, limits: baseline.AncillaLimits):
        self.guard, self.limits = guard, limits
        self.peak_terms = self.peak_shifts = self.products = self.promotions = self.operations = 0

    def size(self, count: int) -> None:
        self.guard.check_time()
        self.guard.check_terms(count)
        self.peak_terms = max(self.peak_terms, count)

    def shifts(self, value: Shifts) -> None:
        self.size(sum(len(p) for p in value.values()))
        self.peak_shifts = max(self.peak_shifts, len(value))

    def product(self) -> None:
        self.guard.check_time()
        self.products += 1
        if self.products > self.limits.max_products:
            raise ResourceLimitExceeded("polynomial_products", self.limits.max_products,
                                        self.products)


def _toggle(out: set[int], term: int, work: Work) -> None:
    if term in out:
        out.remove(term)
    else:
        out.add(term)
    work.size(len(out))


def _anf_substitute(poly: set[int], bit: int, replacement: set[int], work: Work) -> set[int]:
    out: set[int] = set()
    for term in poly:
        work.guard.check_time()
        if term & bit:
            for mask in replacement:
                work.product()
                _toggle(out, (term ^ bit) | mask, work)
        else:
            _toggle(out, term, work)
    return out


def _put(out: Poly, term: int, coefficient: Fraction, work: Work) -> None:
    if coefficient:
        value = out.get(term, Fraction(0)) + coefficient
        if value:
            out[term] = value
        else:
            out.pop(term, None)
    work.size(len(out))


def _add(a: Poly, b: Poly, work: Work, scale: Fraction | int = 1) -> Poly:
    out = dict(a)
    work.size(len(out))
    for term, coefficient in b.items():
        _put(out, term, coefficient * scale, work)
    return out


def _scale(a: Poly, scale: Fraction | int, work: Work) -> Poly:
    out: Poly = {}
    for term, coefficient in a.items():
        _put(out, term, coefficient * scale, work)
    return out


def _multiply(a: Poly, b: Poly, work: Work) -> Poly:
    out: Poly = {}
    for term, coefficient in a.items():
        for mask, value in b.items():
            work.product()
            _put(out, term | mask, coefficient * value, work)
    return out


def _lift(anf: set[int], work: Work) -> Poly:
    """Exact parity lift; its possible exponential cost is deliberately visible."""
    result: Poly = {}
    for term in sorted(anf):
        monomial = {term: Fraction(1)}
        cross = _multiply(result, monomial, work)
        result = _add(_add(result, monomial, work), cross, work, -2)
    return result


def _substitute(poly: Poly, bit: int, replacement: Poly, work: Work) -> Poly:
    free: Poly = {}
    factor: Poly = {}
    for term, coefficient in poly.items():
        if term & bit:
            _put(factor, term ^ bit, coefficient, work)
        else:
            _put(free, term, coefficient, work)
    return _add(free, _multiply(factor, replacement, work), work)


def _shift_argument(poly: Poly, mask: int, work: Work) -> Poly:
    out = poly
    while mask:
        bit = mask & -mask
        out = _substitute(out, bit, {0: Fraction(1), bit: Fraction(-1)}, work)
        mask ^= bit
    return out


def _accumulate(out: Shifts, shift: int, poly: Poly, work: Work) -> None:
    if poly:
        merged = _add(out.get(shift, {}), poly, work)
        if merged:
            out[shift] = merged
        else:
            out.pop(shift, None)
    work.shifts(out)


def _xor_poly(a: Poly, b: Poly, work: Work) -> Poly:
    return _add(_add(a, b, work), _multiply(a, b, work), work, -2)


def _classical_anf(op: HOp, bit: int, slots: dict[str, int]) -> set[int]:
    if op.kind == "store":
        return {0} if op.value else set()
    if op.kind == "oxor":
        return {bit} ^ {slots[op.source]}
    if op.condition is None:
        return {0, bit}
    result = {bit} ^ {slots[op.condition.removeprefix("!")]}
    return result ^ {0} if op.condition.startswith("!") else result


def _boolean_step(anf: set[int], op: HOp, slots: dict[str, int],
                  work: Work) -> set[int] | Shifts:
    if op.kind in {"z", "cz", "ccz", "neg"}:
        return anf
    if op.kind in {"x", "cx", "ccx", "mcx"}:
        controls = sum(1 << q for q in op.wires[:-1])
        toggle = {controls}
        if op.condition is not None:
            bit = slots[op.condition.removeprefix("!")]
            toggle = {controls | bit}
            if op.condition.startswith("!"):
                toggle ^= {controls}
        target = 1 << op.wires[-1]
        return _anf_substitute(anf, target, {target} ^ toggle, work)
    if op.kind in {"store", "invert", "oxor"}:
        bit = slots[op.slot]
        return _anf_substitute(anf, bit, _classical_anf(op, bit, slots), work)
    qbit = 1 << op.wires[0]
    if op.kind == "reset":
        return _anf_substitute(anf, qbit, set(), work)
    slot = slots[op.slot]
    if op.kind == "measure_z":
        return _anf_substitute(anf, slot, {qbit}, work)
    if op.kind != "hmr":
        raise InternalInconsistency("unexpected primitive in Boolean mode")
    after_reset = _anf_substitute(anf, qbit, set(), work)
    low = _anf_substitute(after_reset, slot, set(), work)
    high = _anf_substitute(after_reset, slot, {0}, work)
    if low == high:
        return low
    work.promotions += 1
    f0, f1 = _lift(low, work), _lift(high, work)
    out: Shifts = {}
    _accumulate(out, 0, _scale(_add(f0, f1, work), Fraction(1, 2), work), work)
    _accumulate(out, qbit, _scale(_add(f0, f1, work, -1), Fraction(1, 2), work), work)
    return out


def _unitary(observable: Shifts, op: HOp, work: Work) -> Shifts:
    if op.kind == "neg":
        return observable
    out: Shifts = {}
    if op.kind in {"x", "cx", "ccx", "mcx"}:
        controls = sum(1 << q for q in op.wires[:-1])
        target = 1 << op.wires[-1]
        replacement = _xor_poly({target: Fraction(1)}, {controls: Fraction(1)}, work)
        for shift, coefficient in observable.items():
            composed = _substitute(coefficient, target, replacement, work)
            if not shift & controls:
                _accumulate(out, shift, composed, work)
                continue
            # At least one control flips: C(u) and C(u xor shift) are disjoint.
            shifted_control = _shift_argument({controls: Fraction(1)}, shift & controls, work)
            delta = _add({controls: Fraction(1)}, shifted_control, work)
            switched = _multiply(composed, delta, work)
            _accumulate(out, shift, _add(composed, switched, work, -1), work)
            _accumulate(out, shift ^ target, switched, work)
        return out
    if op.kind in {"z", "cz", "ccz"}:
        controls = sum(1 << q for q in op.wires)
        for shift, coefficient in observable.items():
            if not shift & controls:
                _accumulate(out, shift, coefficient, work)
                continue
            other = _shift_argument({controls: Fraction(1)}, shift & controls, work)
            delta = _add({controls: Fraction(1)}, other, work)
            changed = _add(coefficient, _multiply(coefficient, delta, work), work, -2)
            _accumulate(out, shift, changed, work)
        return out
    raise InternalInconsistency("unexpected unitary primitive")


def _polynomial_step(observable: Shifts, op: HOp, slots: dict[str, int],
                     work: Work) -> Shifts:
    if op.kind in {"x", "cx", "ccx", "mcx", "z", "cz", "ccz", "neg"}:
        changed = _unitary(observable, op, work)
        if op.condition is None or changed == observable:
            return changed
        bit = slots[op.condition.removeprefix("!")]
        left, right = (changed, observable) if op.condition.startswith("!") else (observable, changed)
        out: Shifts = {}
        for shift in left.keys() | right.keys():
            a, b = left.get(shift, {}), right.get(shift, {})
            result = _add(a, _multiply(_add(b, a, work, -1), {bit: Fraction(1)}, work), work)
            _accumulate(out, shift, result, work)
        return out
    out = {}
    if op.kind in {"store", "invert", "oxor"}:
        bit = slots[op.slot]
        replacement = _lift(_classical_anf(op, bit, slots), work)
        for shift, coefficient in observable.items():
            _accumulate(out, shift, _substitute(coefficient, bit, replacement, work), work)
        return out
    qbit = 1 << op.wires[0]
    for shift, coefficient in observable.items():
        if shift & qbit:
            continue
        if op.kind == "reset":
            _accumulate(out, shift, _substitute(coefficient, qbit, {}, work), work)
        elif op.kind == "measure_z":
            _accumulate(out, shift, _substitute(coefficient, slots[op.slot],
                                               {qbit: Fraction(1)}, work), work)
        elif op.kind == "hmr":
            reset = _substitute(coefficient, qbit, {}, work)
            low = _substitute(reset, slots[op.slot], {}, work)
            high = _substitute(reset, slots[op.slot], {0: Fraction(1)}, work)
            _accumulate(out, shift, _scale(_add(low, high, work), Fraction(1, 2), work), work)
            _accumulate(out, shift ^ qbit,
                        _scale(_add(low, high, work, -1), Fraction(1, 2), work), work)
        else:
            raise InternalInconsistency("unexpected nonunitary primitive")
    return out


def _primitives(op: HOp) -> tuple[HOp, ...]:
    """Exact local lowering; no inverse-pair or whole-source peephole optimization."""
    if op.kind not in {"swap", "cswap"}:
        return (op,)
    a, b = op.wires[-2:]
    center = HOp("cx", (b, a), condition=op.condition) if op.kind == "swap" else HOp(
        "ccx", (op.wires[0], b, a), condition=op.condition)
    outer = HOp("cx", (a, b), condition=op.condition)
    return outer, center, outer


def _effect(source: baseline._Source, target: int, work: Work) -> set[int] | Shifts:
    width = source.data + source.ancillas
    slots = {name: 1 << (width + i) for i, name in enumerate(source.slots)}
    effect: set[int] | Shifts = {1 << target}
    work.size(1)
    for op in reversed(source.ops):
        work.guard.check_time()
        work.operations += 1
        for primitive in reversed(_primitives(op)):
            effect = (_boolean_step(effect, primitive, slots, work) if type(effect) is set else
                      _polynomial_step(effect, primitive, slots, work))
    data_mask = (1 << source.data) - 1
    ancilla_mask = ((1 << width) - 1) ^ data_mask
    if type(effect) is set:
        out_anf = set()
        for term in effect:
            work.guard.check_time()
            if term >> width:
                raise InternalInconsistency("uninitialized classical input in Boolean effect")
            if not term & ancilla_mask:
                _toggle(out_anf, term, work)
        return out_anf
    projected: Shifts = {}
    for shift, poly in effect.items():
        if any(term >> width for term in poly):
            raise InternalInconsistency("uninitialized classical input in polynomial effect")
        if shift & ancilla_mask:
            continue
        reduced = {term: c for term, c in poly.items() if not term & ancilla_mask}
        _accumulate(projected, shift, reduced, work)
    for shift, poly in projected.items():
        # Real symmetry: f_s(u)=f_s(u xor s), with its own bounded conversion cost.
        if _shift_argument(poly, shift, work) != poly:
            raise InternalInconsistency("shift-polynomial effect is not symmetric")
    return projected


def _mean(poly: Poly, work: Work) -> Fraction:
    result = Fraction(0)
    for term, coefficient in poly.items():
        work.guard.check_time()
        result += coefficient / (1 << term.bit_count())
    return result


def _witness(effect: set[int] | Shifts, data: int, work: Work) -> tuple[int, Fraction]:
    if type(effect) is set:
        # A minimum-degree monomial has no other present monomial as a proper subset.
        return min(effect, key=int.bit_count), Fraction(1)
    poly = effect.get(0, {})
    average = _mean(poly, work)
    if not 0 < average <= 1:
        raise InternalInconsistency("nonzero positive effect needs positive normalized trace")
    assignment = 0
    for q in range(data):
        bit = 1 << q
        zero = _substitute(poly, bit, {}, work)
        zero_mean = _mean(zero, work)
        one_mean = 2 * average - zero_mean
        if not 0 <= zero_mean <= 1 or not 0 <= one_mean <= 1:
            raise InternalInconsistency("conditional error probability outside [0,1]")
        if zero_mean > 0:
            poly, average = zero, zero_mean
        else:
            assignment |= bit
            poly, average = _substitute(poly, bit, {0: Fraction(1)}, work), one_mean
        if average <= 0:
            raise InternalInconsistency("positive basis witness was lost")
    return assignment, average


def _run(program: HybridProgram, target: int, guard: Guard,
         limits: baseline.AncillaLimits, counters: dict) -> ShiftDiagonalResult:
    work = Work(guard, limits)
    try:
        source = baseline._freeze(program, target, work)
        effect = _effect(source, target, work)
        assignment, probability = _witness(effect, source.data, work) if effect else (None, None)
        return ShiftDiagonalResult("not_clean" if effect else "clean", source.sha256, assignment,
                                   probability,
                                   mode="boolean" if type(effect) is set else "shift_polynomial",
                                   peak_terms=work.peak_terms, peak_shifts=work.peak_shifts,
                                   products=work.products, promotions=work.promotions,
                                   checked_operations=work.operations)
    finally:
        baseline._counted(work, counters)


def check_shift_diagonal(program: HybridProgram, target: int, *, budget: Budget | None = None,
                         limits: baseline.AncillaLimits | None = None) -> ShiftDiagonalResult:
    """Research result only: no certificate/rewrite authorization or default integration."""
    guard, limits = baseline._settings(budget, limits)
    counters: dict = {}
    try:
        result = _run(program, target, guard, limits, counters)
        guard.check_time()  # _run's source, effects and work have been destroyed.
        return result
    except ResourceLimitExceeded as error:
        return ShiftDiagonalResult("inconclusive", peak_terms=counters.get("peak_terms"),
                                   peak_shifts=counters.get("peak_shifts"),
                                   products=counters.get("products"),
                                   promotions=counters.get("promotions"),
                                   checked_operations=counters.get("operations"),
                                   **baseline._inconclusive(error, guard, limits))
