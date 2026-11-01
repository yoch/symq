"""Explicit, local gate-weight proxy selection among three GF(2^24) circuits.

This is not a T-count, physical-volume or Kaggle competition scorer.
Every option implements the same *complete* classical multiplication
permutation with the pinned modulus 0x100001B. The tower tensor is
certified separately; this selection never establishes a contextual
cut-precondition or permits rewriting arbitrary quantum programs.
"""
from __future__ import annotations

from dataclasses import dataclass

from symq.circuit import Circuit
from symq.generators.gf2n import emit, karatsuba, schoolbook
from symq.labs.gf24_schedule import pinned_gf24_emitted
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

    alternatives = (
        ("schoolbook-incidence", emit(24, schoolbook(24))),
        ("karatsuba-pivot-scheduled",
         emit(24, karatsuba(24), strategy="pivot-scheduled")),
        ("tower-99-pinned-order", pinned_gf24_emitted()),
    )
    estimates = tuple(
        GF24Cost(name, c.ccx, c.cx, c.ccx * ccx_weight + c.cx * cx_weight)
        for name, c in alternatives
    )
    chosen_idx = min(
        range(len(estimates)),
        key=lambda i: (
            estimates[i].weighted, estimates[i].ccx, estimates[i].cx, estimates[i].name,
        ),
    )
    choice = estimates[chosen_idx]
    return GF24Selection(choice.name, alternatives[chosen_idx][1].circuit,
                         choice, estimates)
