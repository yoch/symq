"""Choose among three GF(2^24) multiplier circuits under a declared CX/CCX gate weight.

The three circuits (schoolbook, scheduled Karatsuba, pinned 99-product tower) compute the same
map ``(a, b, z) -> (a, b, z XOR a*b)`` modulo ``0x100001B``; ``tests/test_gf24_rewrite.py``
proves each one exactly against the schoolbook circuit with the packed degree-two engine. The
weights are a declared proxy, not a T-count or a hardware cost, and choosing a circuit proves
nothing about the place it is inserted: use :func:`symq.labs.bilinear_substitution.gf24_rewrite`.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from symq.circuit import Circuit, Gate
from symq.generators.gf2n import emit, karatsuba, schoolbook
from symq.labs.gf24_order import pinned_gf24_circuit
from symq.labs.gf24_tower import GF24_MODULUS


@dataclass(frozen=True)
class GF24Cost:
    name: str
    ccx: int
    cx: int
    weighted: int


@dataclass(frozen=True)
class GF24Selection:
    """Chosen circuit is intentionally mutable; this is not a proof receipt."""

    method: str
    circuit: Circuit
    cost: GF24Cost
    alternatives: tuple[GF24Cost, ...]
    modulus: int = GF24_MODULUS


@lru_cache(maxsize=1)
def _alternative_gates() -> tuple[tuple[str, tuple[Gate, ...]], ...]:
    """The three circuits' gates, synthesized once per process (gates are immutable)."""
    return (
        ("schoolbook-incidence", tuple(emit(24, schoolbook(24)).circuit.gates)),
        ("karatsuba-pivot-scheduled",
         tuple(emit(24, karatsuba(24), strategy="pivot-scheduled").circuit.gates)),
        ("tower-99-pinned-order", tuple(pinned_gf24_circuit().gates)),
    )


def choose_gf24(*, ccx_weight: int, cx_weight: int) -> GF24Selection:
    """Choose the cheapest of three *declared* alternatives by exact gate count.

    The unweighted tie break is deterministic. Both weights must be explicit
    nonnegative plain integers and at least one must be strictly positive.
    This function does not claim globally optimal bilinear rank, CX schedule
    or superiority to methods not included here.
    """
    if (type(ccx_weight) is not int or ccx_weight < 0
            or type(cx_weight) is not int or cx_weight < 0
            or ccx_weight + cx_weight == 0):
        raise ValueError("explicit nonnegative gate weights are required, not both zero")

    # Each call gets fresh circuits built from the cached, immutable gate tuples.
    alternatives = tuple((name, Circuit(72, list(gates))) for name, gates in _alternative_gates())

    def cost(name: str, circuit: Circuit) -> GF24Cost:
        # Counted from the emitted gates themselves, not from the emitter's bookkeeping.
        ccx = sum(gate.name == "ccx" for gate in circuit.gates)
        cx = sum(gate.name == "cx" for gate in circuit.gates)
        if ccx + cx != len(circuit.gates):
            raise ValueError(f"{name}: gates outside the declared CX/CCX proxy")
        return GF24Cost(name, ccx, cx, ccx * ccx_weight + cx * cx_weight)

    estimates = tuple(cost(name, circuit) for name, circuit in alternatives)
    chosen_idx = min(
        range(len(estimates)),
        key=lambda i: (
            estimates[i].weighted, estimates[i].ccx, estimates[i].cx, estimates[i].name,
        ),
    )
    choice = estimates[chosen_idx]
    return GF24Selection(choice.name, alternatives[chosen_idx][1], choice, estimates)
