"""Exact symbolic equivalence of reversible circuits with concretely checked witnesses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .backends import Algebra, NativeZDDAlgebra, Stats, has_native, make_algebra, simulate
from .circuit import Circuit, Gate
from .resources import Budget, Guard, ResourceLimitExceeded, session_scoped


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


@session_scoped
def check_equivalence(
    left: Circuit,
    right: Circuit,
    *,
    backend: str | type[Algebra[Any]] = "sparse",
    budget: Budget | None = None,
    backend_options: dict[str, Any] | None = None,
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
    algebra = make_algebra(backend, left.width, budget, **(backend_options or {}))
    if (NativeZDDAlgebra is not None and isinstance(algebra, NativeZDDAlgebra)
            and algebra.collect_every is not None):
        # Collection remaps integer node IDs. Keep both circuits' outputs pinned
        # through the second simulation, otherwise equality can silently compare
        # stale IDs that now denote unrelated polynomials.
        outputs_left, outputs_right = algebra.simulate_pair(left, right)
    else:
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


@session_scoped
def check_equivalence_by_blocks(
    left: Circuit,
    right: Circuit,
    *,
    backend: str | type[Algebra[Any]] | None = None,
    max_block_width: int = 64,
    fallback: str | type[Algebra[Any]] | None = "zdd",
    budget: Budget | None = None,
    backend_options: dict[str, Any] | None = None,
) -> EquivalenceResult:
    """Decide equivalence block by block over the wires the two circuits never couple.

    Blocks are the connected components of the interaction graph of *both* circuits, so each
    output depends only on the inputs of its block and the circuits are equivalent iff every
    block pair is. Blocks up to ``max_block_width`` wires use ``backend`` (``zdd-native`` when
    built, else ``zdd``); wider blocks use ``fallback``, or raise ``ResourceLimitExceeded``
    when it is ``None``. ``budget.max_seconds`` bounds the whole check; ``max_terms`` and
    ``max_nodes`` apply to each block's algebra. ``backend`` of the result names every
    backend used, joined by ``+``.
    """
    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError("circuits required")
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    if not isinstance(max_block_width, int) or max_block_width < 1:
        raise ValueError("max_block_width must be a positive integer")
    if backend is None:
        backend = "zdd-native" if has_native() else "zdd"

    guard = Guard(budget)
    joint = Circuit(left.width, [*left.gates, *right.gates])
    blocks = joint.wire_blocks()
    block_of = {q: index for index, qubits in enumerate(blocks) for q in qubits}
    local = {q: position for qubits in blocks for position, q in enumerate(qubits)}

    def split(circuit: Circuit) -> list[Circuit]:
        parts = [Circuit(len(qubits)) for qubits in blocks]
        for gate in circuit.gates:
            parts[block_of[gate.qubits[0]]].gates.append(
                Gate(gate.name, tuple(local[q] for q in gate.qubits))
            )
        return parts

    total = Stats()
    used: set[str] = set()
    for qubits, left_part, right_part in zip(blocks, split(left), split(right)):
        guard.check_time()
        chosen = backend
        if len(qubits) > max_block_width:
            if fallback is None:
                raise ResourceLimitExceeded("block width", max_block_width, len(qubits))
            chosen = fallback
        result = check_equivalence(
            left_part, right_part, backend=chosen, budget=guard.inherited_budget(),
            backend_options=backend_options if chosen == backend else None,
        )
        used.add(result.backend)
        for name in (
            "gates", "products", "conversions", "conversion_terms", "conversion_seconds", "seconds"
        ):
            setattr(total, name, getattr(total, name) + getattr(result.stats, name))
        total.observe_terms(result.stats.peak_terms)
        if not result.equivalent:
            assert result.output is not None and result.witness is not None
            output = qubits[result.output]
            witness = sum(1 << q for position, q in enumerate(qubits) if result.witness >> position & 1)
            if left.run(witness) == right.run(witness):
                raise InternalInconsistency(
                    f"block verification with {result.backend!r} reported a difference on "
                    f"output {output} that concrete execution does not confirm"
                )
            return EquivalenceResult(False, "+".join(sorted(used)), total, output, witness)
    return EquivalenceResult(True, "+".join(sorted(used)), total)
