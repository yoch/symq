"""Exact symbolic equivalence of reversible circuits with concretely checked witnesses."""
from __future__ import annotations

from dataclasses import dataclass

from .backends import Stats, make_algebra, simulate
from .circuit import Circuit
from .resources import Budget


class InternalInconsistency(RuntimeError):
    """A backend produced a verdict that failed independent concrete validation."""


@dataclass(frozen=True)
class EquivalenceResult:
    equivalent: bool
    backend: str
    stats: Stats
    output: int | None = None
    """First output wire whose polynomials differ."""
    witness: int | None = None
    """Input assignment (LSB-first bitmask) on which the circuits produce different outputs."""


def check_equivalence(
    left: Circuit, right: Circuit, *, backend: str = "sparse", budget: Budget | None = None
) -> EquivalenceResult:
    """Decide functional equality of two X/CX/CCX/MCX circuits of equal width.

    ANFs are canonical, so the circuits are equivalent iff every output polynomial is
    identical. Otherwise a minimum-degree monomial ``m`` of the difference of output ``i``
    is an assignment where that difference evaluates to 1 (no other monomial of the
    difference divides ``m``); it is re-checked by concrete execution before returning.
    """
    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError("circuits required")
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    algebra = make_algebra(backend, left.width, budget)
    outputs_left = simulate(left, algebra)
    outputs_right = simulate(right, algebra)
    for index, (a, b) in enumerate(zip(outputs_left, outputs_right)):
        if algebra.equal(a, b):
            continue
        witness = algebra.min_monomial(algebra.xor(a, b))
        if witness is None or left.run(witness) == right.run(witness):
            raise InternalInconsistency(
                f"backend {backend!r} reported a difference on output {index} "
                "that concrete execution does not confirm"
            )
        return EquivalenceResult(False, backend, algebra.stats, index, witness)
    return EquivalenceResult(True, backend, algebra.stats)
