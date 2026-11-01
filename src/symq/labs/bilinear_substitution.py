"""Experimental GF(4)-tower rewrite at an exact *classical* circuit cut.

This adapter composes the certified factor generator (research PR #126)
with the frozen contextual SAT proof/application (research PR #124).
It never trusts the tensor certificate as a contextual proof, never
silently assumes an ancilla is clean, and never mutates the source.

All guarantees concern reversible X/CX/CCX/MCX circuits on basis states
under the caller's proved original-input and cut-state contract. A
restricted classical predicate is NOT a coherent quantum channel theorem.
"""
from __future__ import annotations

from symq.circuit import Circuit
from symq.generators.gf2n import tower_multiplier
from symq.labs.contextual_substitution import (
    AppliedClassicalSubstitution,
    GateWeights,
    SubstitutionContract,
    apply_verified_substitution,
    check_substitution,
)
from symq.resources import Budget, Guard


def _mapped_multiplier(
    width: int, n: int, modulus: int, wires: tuple[int, ...], strategy: str
) -> Circuit:
    if (type(wires) is not tuple or len(wires) != 3 * n
            or any(type(w) is not int or w < 0 or w >= width for w in wires)
            or len(set(wires)) != len(wires)):
        raise ValueError("wires must be a distinct, in-range 3*n tuple of global wire indices")
    local = tower_multiplier(n, modulus=modulus, strategy=strategy)
    mapped = Circuit(width)
    for gate in local.gates:
        mapped.append(gate.name, *(wires[wire] for wire in gate.qubits))
    return mapped


def apply_tower_substitution(
    source: Circuit,
    span: tuple[int, int],
    *,
    n: int,
    modulus: int,
    wires: tuple[int, ...],
    contract: SubstitutionContract,
    weights: GateWeights,
    budget: Budget | None = None,
    strategy: str = "pivot-scheduled",
    require_saving: bool = True,
) -> AppliedClassicalSubstitution:
    """Prove and replay one whole-output bilinear replacement at a real cut.

    `wires` maps local (a0..a(n-1), b0.., z0..) to distinct global wires.
    Every wire not in `wires` remains untouched by the proposed replacement.
    The exact original span is never inferred from a gate pattern.

    Both passes share one absolute deadline including factor construction.
    A stale source, mismatched polynomial, unproved cut/restoration,
    wrong mapping or invalid weights fails closed: no candidate is returned.
    `require_saving` applies solely to the caller's explicit integer proxy
    weights; it never claims a physical or Kaggle scoring improvement.
    """
    if type(source) is not Circuit:
        raise TypeError("source must be a validated reversible Circuit")
    if type(contract) is not SubstitutionContract:
        raise TypeError("an explicit SubstitutionContract is required")
    if type(weights) is not GateWeights:
        raise TypeError("explicit per-gate weights are required")
    if type(require_saving) is not bool:
        raise TypeError("require_saving must be boolean")
    if budget is not None and not isinstance(budget, Budget):
        raise TypeError("budget must be Budget or None")

    requested = budget if budget is not None else Budget(max_seconds=30)
    guard = Guard(requested)
    shared_budget = Budget(
        requested.max_terms, requested.max_nodes,
        absolute_deadline=guard.deadline, max_bytes=requested.max_bytes,
    )
    source.validate()
    replacement = _mapped_multiplier(source.width, n, modulus, wires, strategy)
    guard.check_time()
    receipt = check_substitution(
        source, span, replacement, contract=contract, weights=weights,
        budget=shared_budget,
    )
    if not receipt.equivalent:
        raise ValueError(
            "contextual basis-state substitution is not proved: "
            + receipt.outcome + " (" + receipt.reason + ")"
        )
    if require_saving and receipt.cost.weighted_delta >= 0:
        raise ValueError("certified rewrite has no saving under the declared gate weights")
    applied = apply_verified_substitution(
        receipt, source, span, replacement, contract=contract, budget=shared_budget,
    )
    guard.check_time()
    return applied
