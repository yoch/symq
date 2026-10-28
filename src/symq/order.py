"""Variable-order policies, chosen by measurement on corrected circuits.

The first version of this module offered only ``identity`` and ``reversed``, on the strength of a
campaign whose arithmetic circuits were **not adders**: the generator had ``maj`` and ``uma`` in
the same direction, so the "3.3x on unseen adders" was measured on circuits that computed
something else. The audit found both defects.

Re-run on the corrected Cuccaro adders (verified exhaustively for 1-4 bits by
``tests/test_adders.py``) with SHA-256 function fingerprints instead of colliding summaries, the
ranking changes:

| order | selection circuits (8) | holdout (16) | adders | MCX chains |
|---|---:|---:|---:|---:|
| ``last_use`` | **0.084** | **0.104** | 0.017 (58x faster) | **1.577 (58 % slower)** |
| ``reversed`` | 0.665 | -- | -- | -- |
| ``bfs`` | 0.301 | -- | -- | -- |
| ``min_fill`` | 0.248 | -- | -- | -- |
| ``identity`` | 1.000 | 1.000 | 1.000 | 1.000 |

So the policy offered here is ``last_use``, and it comes with the honest caveat that it is **not**
universal: it wins enormously on arithmetic and loses on circuits whose wires are used in a single
long cascade. ``identity`` remains the default, exactly as before.
"""
from __future__ import annotations

from symq.circuit import Circuit

POLICIES = ("identity", "reversed", "last_use")
"""``identity`` is the historic default; ``last_use`` is the measured winner on arithmetic."""


def _permutation(order) -> tuple[int, ...]:
    values = tuple(order)
    if sorted(values) != list(range(len(values))):
        raise AssertionError("an order policy must return a permutation")
    return values


def last_use_order(circuit: Circuit) -> tuple[int, ...]:
    """Wires whose final use comes last, first.

    The intuition is the one behind elimination orderings: a wire that is finished early can be
    dropped from the diagram early, so it belongs near the leaf, and a wire still needed at the
    end belongs near the root. On the Cuccaro adder the carry chain gives exactly that shape.
    """
    circuit.validate()
    last = [0] * circuit.width
    for position, gate in enumerate(circuit.gates):
        for qubit in gate.qubits:
            last[qubit] = position
    return _permutation(sorted(range(circuit.width), key=lambda wire: (-last[wire], wire)))


def order_for(circuit: Circuit, policy: str = "identity") -> tuple[int, ...]:
    """The wire order to hand to ``NativeZDDAlgebra(order=...)``."""
    if policy not in POLICIES:
        raise ValueError(f"unknown order policy {policy!r}; choose from {list(POLICIES)}")
    if not isinstance(circuit, Circuit):
        raise TypeError("a Circuit is required")
    circuit.validate()
    if policy == "identity":
        return tuple(range(circuit.width))
    if policy == "reversed":
        return _permutation(reversed(range(circuit.width)))
    return last_use_order(circuit)


def algebra_order(width: int, policy: str = "identity") -> tuple[int, ...]:
    """Same, from a width alone.

    ``last_use`` needs the gates, so it is rejected here rather than silently degraded to the
    identity: a caller that asks for a policy must get it or an error.
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown order policy {policy!r}; choose from {list(POLICIES)}")
    if not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive integer")
    if policy == "last_use":
        raise ValueError("the last_use policy needs the circuit, not only its width; "
                         "use symq.order_for(circuit, 'last_use')")
    order = tuple(range(width))
    return order if policy == "identity" else _permutation(reversed(order))
