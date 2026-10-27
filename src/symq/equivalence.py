"""Exact symbolic equivalence of reversible circuits with concretely checked witnesses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .backends import Algebra, Stats, make_algebra, simulate
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
    left: Circuit,
    right: Circuit,
    *,
    backend: str | type[Algebra[Any]] = "sparse",
    budget: Budget | None = None,
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
                f"backend {algebra.name!r} reported a difference on output {index} "
                "that concrete execution does not confirm"
            )
        return EquivalenceResult(False, algebra.name, algebra.stats, index, witness)
    return EquivalenceResult(True, algebra.name, algebra.stats)


def check_equivalence_by_blocks(
    left: Circuit,
    right: Circuit,
    *,
    backend: str | type[Algebra[Any]] = "zdd-native",
    max_block_width: int = 64,
    budget: Budget | None = None,
) -> EquivalenceResult:
    """Check circuit equivalence, partitioning large circuits into independent wire blocks.

    Enables native verification on circuits wider than the 64-qubit native limit whenever
    the circuits' interaction graphs decompose into subcircuits of width <= ``max_block_width``.
    If an individual block exceeds ``max_block_width``, it falls back to the pure-Python ``zdd``
    backend for that block.
    """
    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError("circuits required")
    if left.width != right.width:
        raise ValueError("circuits must have the same width")

    if left.width <= max_block_width:
        return check_equivalence(left, right, backend=backend, budget=budget)

    # Combine gates to find connected components across both circuits
    joint = Circuit(left.width, list(left.gates) + list(right.gates))
    components = joint.connected_components()

    total_stats = Stats()
    chosen_backend_name = (
        backend if isinstance(backend, str) else getattr(backend, "name", str(backend))
    )

    for qubits, _ in components:
        left_sub = left.subcircuit(qubits)
        right_sub = right.subcircuit(qubits)

        block_backend = backend if len(qubits) <= max_block_width else "zdd"
        res = check_equivalence(left_sub, right_sub, backend=block_backend, budget=budget)

        total_stats.gates += res.stats.gates
        total_stats.products += res.stats.products
        total_stats.seconds += res.stats.seconds
        total_stats.observe_terms(res.stats.peak_terms)

        if not res.equivalent:
            assert res.output is not None and res.witness is not None
            orig_output = qubits[res.output]
            full_witness = 0
            for local_idx, orig_idx in enumerate(qubits):
                if res.witness & (1 << local_idx):
                    full_witness |= 1 << orig_idx

            if left.run(full_witness) == right.run(full_witness):
                raise InternalInconsistency(
                    f"blocked verification with {res.backend!r} reported a difference on output {orig_output} "
                    "that concrete execution does not confirm"
                )
            return EquivalenceResult(False, res.backend, total_stats, orig_output, full_witness)

    return EquivalenceResult(True, chosen_backend_name, total_stats)
