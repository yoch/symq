"""Exact symbolic equivalence of reversible circuits with concretely checked witnesses."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from .backends import (
    BACKENDS,
    Algebra,
    NativeZDDAlgebra,
    Stats,
    has_native,
    make_algebra,
    simulate,
)
from .circuit import Circuit, Gate
from .errors import InternalInconsistency
from .resources import Budget, Guard, ResourceLimitExceeded, session_scoped


@dataclass(frozen=True)
class EquivalenceResult:
    equivalent: bool
    backend: str
    stats: Stats
    output: int | None = None
    """First output wire whose polynomials differ."""
    witness: int | None = None
    """Input assignment (LSB-first bitmask) on which the circuits produce different outputs."""


OrderSpec = str | Sequence[int]
"""``"auto"``, a policy name from ``symq.POLICIES``, or an explicit permutation of the wires."""


def _backend_name(backend: str | type[Algebra[Any]] | None) -> str | None:
    return backend if isinstance(backend, str) else getattr(backend, "name", None)


def order_option(backend: str | type[Algebra[Any]] | None) -> str | None:
    """The constructor option through which ``backend`` takes a variable order, or ``None``.

    Read from the backend class (``Algebra.order_option``), so registered and directly passed
    backends are treated alike.
    """
    cls = BACKENDS.get(backend) if isinstance(backend, str) else backend
    return getattr(cls, "order_option", None) if cls is not None else None


def _with_order(backend: str | type[Algebra[Any]], order: OrderSpec | None, left: Circuit,
                right: Circuit, options: dict[str, Any] | None) -> dict[str, Any]:
    """Backend options with the variable order resolved on the reference circuit ``left``.

    The rule reads the shape of one circuit: on the concatenated gate list the second circuit
    touches every wire near the end, which hides the staging that ``last_use`` exploits.
    """
    options = dict(options or {})
    if order is None:
        return options
    key = order_option(backend)
    if key is None:
        takes = sorted(name for name in BACKENDS if order_option(name))
        raise ValueError(f"backend {_backend_name(backend)!r} takes no variable order; "
                         f"order= applies to {takes}")
    if key in options:
        raise ValueError(f"give the variable order once (order= or backend_options[{key!r}])")
    if isinstance(order, str):
        from .order import order_for

        policy = order
        if order == "auto":
            from .strategy import choose_order, features

            policy = choose_order(features(left))[0]
        options[key] = list(order_for(left, policy))
    else:
        options[key] = list(order)
    return options


@session_scoped
def check_equivalence(
    left: Circuit,
    right: Circuit,
    *,
    backend: str | type[Algebra[Any]] = "sparse",
    budget: Budget | None = None,
    backend_options: dict[str, Any] | None = None,
    order: OrderSpec | None = None,
) -> EquivalenceResult:
    """Decide functional equality of two X/CX/CCX/MCX circuits of equal width.

    ANFs are canonical, so the circuits are equivalent iff every output polynomial is
    identical. Otherwise a minimum-degree monomial ``m`` of the difference of output ``i``
    is an assignment where that difference evaluates to 1 (no other monomial of the
    difference divides ``m``); it is re-checked by concrete execution before returning.

    ``order`` sets the variable order of a ZDD backend: ``"auto"`` applies the structural rule
    of ``symq.strategy.choose_order`` to ``left``, a policy name from
    ``symq.POLICIES`` is applied directly, and a sequence is used as given. The order changes
    the cost, never the verdict or the witness.
    """
    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError("circuits required")
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    options = _with_order(backend, order, left, right, backend_options)
    algebra = make_algebra(backend, left.width, budget, **options)
    if (NativeZDDAlgebra is not None and isinstance(algebra, NativeZDDAlgebra)
            and algebra.collect_every is not None):
        # Collection remaps integer node IDs. Keep both circuits' outputs pinned
        # through the second simulation, otherwise equality can silently compare
        # stale IDs that now denote unrelated polynomials.
        outputs_left, outputs_right = algebra.simulate_pair(left, right)
    else:
        outputs_left = simulate(left, algebra)
        outputs_right = simulate(right, algebra)
    return _compare(algebra, left, right, outputs_left, outputs_right, algebra.stats)


def _compare(algebra: Algebra[Any], left: Circuit, right: Circuit, outputs_left: Sequence[Any],
             outputs_right: Sequence[Any], stats: Stats) -> EquivalenceResult:
    """Verdict from two output tuples of one algebra, with the witness replayed concretely."""
    for index, (a, b) in enumerate(zip(outputs_left, outputs_right)):
        if algebra.equal(a, b):
            continue
        witness = algebra.min_monomial(algebra.xor(a, b))
        if witness is None or left.run(witness) == right.run(witness):
            raise InternalInconsistency(
                f"backend {algebra.name!r} reported a difference on output {index} "
                "that concrete execution does not confirm"
            )
        return EquivalenceResult(False, algebra.name, stats, index, witness)
    return EquivalenceResult(True, algebra.name, stats)


class ReferenceChecker:
    """Check many candidate circuits against one fixed reference, reusing one algebra.

    The reference is simulated once; each candidate is simulated in the same algebra, so a
    hash-consing backend shares every sub-diagram the candidates have in common with the reference
    and with each other. This is the shape of a search loop that tries many rewrites of one
    circuit. Verdicts and witnesses are those of :func:`check_equivalence`.

    ``budget`` applies to *each* :meth:`check` (time from the start of the call; ``max_nodes``
    bounds the shared table, which keeps growing across checks). Collection
    (``collect_every``) is refused: it would invalidate the stored reference handles.
    """

    def __init__(self, reference: Circuit, *, backend: str | type[Algebra[Any]] = "zdd",
                 order: OrderSpec | None = None, budget: Budget | None = None,
                 backend_options: dict[str, Any] | None = None) -> None:
        if not isinstance(reference, Circuit):
            raise TypeError("a reference Circuit is required")
        options = _with_order(backend, order, reference, reference, backend_options)
        if options.get("collect_every") is not None:
            raise ValueError("collection would invalidate the stored reference outputs")
        self.reference = Circuit(reference.width, list(reference.gates))
        self.budget = budget
        self.algebra = make_algebra(backend, reference.width, budget, **options)
        self._outputs = simulate(self.reference, self.algebra)
        self.checks = 0

    def check(self, candidate: Circuit) -> EquivalenceResult:
        if not isinstance(candidate, Circuit):
            raise TypeError("a candidate Circuit is required")
        if candidate.width != self.reference.width:
            raise ValueError("candidate and reference widths differ")
        # Rebinds the algebra and every algebra it wraps, so composite backends get the new
        # deadline too.
        self.algebra.bind_guard((self.budget or Budget()).start())
        before = replace(self.algebra.stats)
        outputs = simulate(candidate, self.algebra)
        self.checks += 1
        stats = replace(self.algebra.stats)
        for name in Stats.COUNTERS:
            setattr(stats, name, getattr(stats, name) - getattr(before, name))
        return _compare(self.algebra, self.reference, candidate, self._outputs, outputs, stats)


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
    order: str | None = None,
) -> EquivalenceResult:
    """Decide equivalence block by block over the wires the two circuits never couple.

    Blocks are the connected components of the interaction graph of *both* circuits, so each
    output depends only on the inputs of its block and the circuits are equivalent iff every
    block pair is. Blocks up to ``max_block_width`` wires use ``backend`` (``zdd-native`` when
    built, else ``zdd``); wider blocks use ``fallback``, or raise ``ResourceLimitExceeded``
    when it is ``None``. ``budget.max_seconds`` bounds the whole check; ``max_terms`` and
    ``max_nodes`` apply to each block's algebra. ``backend`` of the result names every
    backend used, joined by ``+``. ``order`` (``"auto"`` or a policy name) is resolved per
    block for every backend that takes a variable order.
    """
    if not isinstance(left, Circuit) or not isinstance(right, Circuit):
        raise TypeError("circuits required")
    if left.width != right.width:
        raise ValueError("circuits must have the same width")
    if not isinstance(max_block_width, int) or max_block_width < 1:
        raise ValueError("max_block_width must be a positive integer")
    if backend is None:
        backend = "zdd-native" if has_native() else "zdd"
    if order is not None and not isinstance(order, str):
        raise ValueError("block verification takes an order policy name, not a permutation")

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
            order=order if order_option(chosen) else None,
        )
        used.add(result.backend)
        total.merge(result.stats)
        if not result.equivalent:
            if result.output is None or result.witness is None:
                raise InternalInconsistency(
                    f"block verification with {result.backend!r} reported a difference without a witness")
            output = qubits[result.output]
            witness = sum(1 << q for position, q in enumerate(qubits) if result.witness >> position & 1)
            if left.run(witness) == right.run(witness):
                raise InternalInconsistency(
                    f"block verification with {result.backend!r} reported a difference on "
                    f"output {output} that concrete execution does not confirm"
                )
            return EquivalenceResult(False, "+".join(sorted(used)), total, output, witness)
    return EquivalenceResult(True, "+".join(sorted(used)), total)
