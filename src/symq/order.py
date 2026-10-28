"""Variable-order policies for the native algebra, measured before being offered.

The experiments in ``research/engineering/2026-10-28`` compared seven structural orders against
the identity order on three families. Two results decide this module:

* the *reversed* order is 3.3x faster than the identity in geometric mean on a reserved family of
  adders, controlled adders, incrementers and MCX chains (19 pairs, one regression, no wrong
  function). It was chosen on an earlier set of circuits and validated on sizes and topologies
  that appeared in neither selection campaign;
* the classic heuristics -- min-degree, min-fill, DFS and BFS over the interaction graph -- are
  **worse** than the reversed order on every family measured (min-fill is 2.9x slower than the
  identity on the small circuits). They are not offered.

So this module exposes exactly one policy, ``reversed``, plus the identity default, and does not
pretend to choose per circuit. A policy that must pick a winner by trying several orders is a
benchmark, not an algorithm.
"""
from __future__ import annotations

from symq.circuit import Circuit

POLICIES = ("identity", "reversed")


def order_for(circuit: Circuit, policy: str = "identity") -> tuple[int, ...]:
    """The wire order to hand to ``NativeZDDAlgebra(order=...)``.

    ``identity`` (default) keeps the engine's historic order, which is what every sealed
    benchmark used. ``reversed`` is the measured policy: it puts the highest-numbered wire at the
    root, which is what the archived reference implementation did and what makes the Cuccaro
    carry chain -- laid out as ``c0, b[..], a[..], z`` -- descend monotonically.
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown order policy {policy!r}; choose from {list(POLICIES)}")
    if not isinstance(circuit, Circuit):
        raise TypeError("a Circuit is required")
    circuit.validate()
    order = tuple(range(circuit.width))
    return order if policy == "identity" else tuple(reversed(order))


def algebra_order(width: int, policy: str = "identity") -> tuple[int, ...]:
    """Same, from a width alone (for callers that build the algebra before the circuit)."""
    if policy not in POLICIES:
        raise ValueError(f"unknown order policy {policy!r}; choose from {list(POLICIES)}")
    if not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive integer")
    order = tuple(range(width))
    return order if policy == "identity" else tuple(reversed(order))
