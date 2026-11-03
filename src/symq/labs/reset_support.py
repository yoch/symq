"""Research-only coherent reset cleanliness on an affine computational-basis span.

This checks a *restricted theorem*, not hybrid-channel equivalence. A prefix of
basis permutations and diagonal phases maps every legal computational basis
input to one basis output times a sign. If the reset target is identically zero
for the entire legal affine span, the output factors as |0> on that wire for
every superposition and every external reference. Reset is then the identity.

Only X/CX/CCX/MCX/SWAP/CSWAP, diagonal Z/CZ/CCZ/NEG, and RESET are supported.
Measurement, HMR, feed-forward and other nonunitary operations fail closed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from symq.errors import ResourceLimitExceeded
from symq.experimental.hybrid import HybridProgram
from symq.resources import Budget, Guard, intersect_budgets

Poly = frozenset[int]
ZERO: Poly = frozenset()
ONE: Poly = frozenset({0})
_PHASES = frozenset({"z", "cz", "ccz", "neg"})
_PERMUTATIONS = frozenset({"x", "cx", "ccx", "mcx", "swap", "cswap"})
_SUPPORTED = _PHASES | _PERMUTATIONS | {"reset"}


@dataclass(frozen=True)
class AffineSupport:
    """Coherent span of |offset XOR sum(u_j * column_j)>.

    Columns must be linearly independent. The *span* comprises arbitrary
    coherent superpositions of these basis states, not an incoherent mixture.
    Ancilla-zero restrictions are validated against HybridProgram.
    """

    width: int
    offset: int
    columns: tuple[int, ...]

    def validate(self, *, max_rank: int = 64) -> None:
        if type(self.width) is not int or not 1 <= self.width <= 256:
            raise ValueError("support width must be an integer from 1 to 256")
        if type(self.offset) is not int or not 0 <= self.offset < (1 << self.width):
            raise ValueError("invalid affine offset")
        if type(self.columns) is not tuple or len(self.columns) > max_rank:
            raise ValueError("affine columns must be a bounded tuple")
        pivots: dict[int, int] = {}
        for value in self.columns:
            if type(value) is not int or not 0 < value < (1 << self.width):
                raise ValueError("affine columns must be nonzero in-range bitsets")
            x = value
            while x:
                bit = x.bit_length() - 1
                if bit not in pivots:
                    pivots[bit] = x
                    break
                x ^= pivots[bit]
            if x == 0:
                raise ValueError("affine columns must be linearly independent")

    def input_at(self, parameter: int) -> int:
        if type(parameter) is not int or not 0 <= parameter < 1 << len(self.columns):
            raise ValueError("parameter outside affine coordinate range")
        value = self.offset
        for j, column in enumerate(self.columns):
            if (parameter >> j) & 1:
                value ^= column
        return value


def _pin(document: dict) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        .encode("utf-8")
    ).hexdigest()


class _Algebra:
    def __init__(self, guard: Guard, max_products: int):
        self.guard = guard
        self.max_products = max_products
        self.products = 0
        self.peak_terms = 0

    def check(self, values) -> None:
        self.guard.check_time()
        size = sum(map(len, values))
        self.guard.check_terms(size)
        self.peak_terms = max(size, self.peak_terms)

    @staticmethod
    def xor(left: Poly, right: Poly) -> Poly:
        return left ^ right

    def mul(self, left: Poly, right: Poly) -> Poly:
        if not left or not right:
            return ZERO
        result: set[int] = set()
        for a in left:
            for b in right:
                self.products += 1
                if self.products > self.max_products:
                    raise ResourceLimitExceeded(
                        "products", self.max_products, self.products
                    )
                term = a | b
                if term in result:
                    result.remove(term)
                else:
                    result.add(term)
                self.guard.check_terms(len(result))
                if self.products % 128 == 0:
                    self.guard.check_time()
        return frozenset(result)

    def product(self, terms) -> Poly:
        result = ONE
        for term in terms:
            result = self.mul(result, term)
        return result


def _witness(poly: Poly) -> int:
    # The smallest-degree monomial has no proper monomial subset in ANF.
    # Setting precisely those variables to 1 evaluates the polynomial to 1.
    return min(poly, key=lambda m: (m.bit_count(), m))


def prove_clean_resets(
    program: HybridProgram,
    support: AffineSupport,
    *,
    budget: Budget | None = None,
    max_terms: int = 100_000,
    max_products: int = 1_000_000,
    max_seconds: float = 10.0,
    max_operations: int = 100_000,
) -> dict:
    """Check that every encountered reset is identity on the coherent legal span.

    'proved_clean' means each reset target is exactly |0> for all admitted
    input superpositions, so deleting just those reset operations is sound.
    'not_proved' contains a concrete basis input whose target is 1.
    'unsupported' and 'inconclusive' carry *no* positive theorem.

    This is an in-process research decision, not an independently checked
    portable certificate. Source/support hashes identify bytes only; a caller
    must independently authenticate its own input objects.
    """
    if type(program) is not HybridProgram or type(support) is not AffineSupport:
        raise TypeError("exact HybridProgram and AffineSupport required")
    # Snapshot mutable input once; validate and prove exactly the pinned operations.
    frozen = HybridProgram(program.data, program.ancillas, list(program.ops))
    frozen.validate()
    ops = tuple(frozen.ops)
    support.validate()
    if frozen.width != support.width:
        raise ValueError("support and program widths differ")
    if type(max_operations) is not int or max_operations < 1:
        raise ValueError("max_operations must be a positive integer")
    if type(max_products) is not int or max_products < 1:
        raise ValueError("max_products must be a positive integer")
    if type(max_terms) is not int or max_terms < 1:
        raise ValueError("max_terms must be a positive integer")
    if budget is not None and (
        type(budget) is not Budget or budget.max_nodes is not None
        or budget.max_bytes is not None
    ):
        raise ValueError("this ANF engine cannot account for node/byte budgets")
    clean_mask = ((1 << frozen.ancillas) - 1) << frozen.data
    if (support.offset & clean_mask) or any(c & clean_mask for c in support.columns):
        raise ValueError("hybrid ancillas must be zero for every legal input")

    source = {
        "data": frozen.data, "ancillas": frozen.ancillas,
        "ops": [asdict(op) for op in ops],
    }
    legal = asdict(support)
    report = {
        "schema_version": 1,
        "proof_kind": "affine_anf_reversible_prefix_reset_identity",
        "portable_certificate": False,
        "source_sha256": _pin(source),
        "support_sha256": _pin(legal),
        "status": "inconclusive",
        "resets": [],
    }
    local = Budget(max_terms=max_terms, max_seconds=max_seconds)
    guard = Guard(intersect_budgets(budget, local) if budget is not None else local)
    work = _Algebra(guard, max_products)
    try:
        if len(ops) > max_operations:
            raise ResourceLimitExceeded("operations", max_operations, len(ops))
        states: list[Poly] = []
        for wire in range(frozen.width):
            terms = ({0} if support.offset >> wire & 1 else set())
            terms.update(1 << j for j, col in enumerate(support.columns) if col >> wire & 1)
            states.append(frozenset(terms))
        work.check(states)
        for index, op in enumerate(ops):
            guard.check_time()
            if op.kind not in _SUPPORTED or op.condition is not None:
                report.update(status="unsupported", reason=f"op {index}: {op.kind} or condition")
                break
            wires = op.wires
            if op.kind == "reset":
                target = wires[0]
                value = states[target]
                if value:
                    parameter = _witness(value)
                    report["resets"].append({
                        "index": index, "wire": target, "status": "proved_nonclean",
                        "input": support.input_at(parameter), "parameter": parameter,
                    })
                    report.update(status="not_proved", obligation="nonclean_reset")
                    break
                report["resets"].append({
                    "index": index, "wire": target, "status": "proved_clean",
                })
            elif op.kind == "x":
                states[wires[0]] = work.xor(states[wires[0]], ONE)
            elif op.kind in ("cx", "ccx", "mcx"):
                *controls, target = wires
                change = work.product(states[q] for q in controls)
                states[target] = work.xor(states[target], change)
            elif op.kind == "swap":
                a, b = wires
                states[a], states[b] = states[b], states[a]
            elif op.kind == "cswap":
                control, a, b = wires
                delta = work.mul(states[control], work.xor(states[a], states[b]))
                states[a] = work.xor(states[a], delta)
                states[b] = work.xor(states[b], delta)
            # Diagonal phase gates do not alter computational-basis support.
            work.check(states)
        else:
            report["status"] = "proved_clean" if report["resets"] else "unsupported"
            if not report["resets"]:
                report["reason"] = "no reset obligations"
        guard.check_time()
    except ResourceLimitExceeded as error:
        report.update(status="inconclusive", reason=str(error))
    report.update(
        peak_terms=work.peak_terms, products=work.products,
        checked_resets=len(report["resets"]),
    )
    return report
