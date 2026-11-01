"""GF(4)-tower multiplier replacement at an exact *classical* circuit cut (research API).

Composes the certified tower factors (:func:`symq.generators.gf2n.tower_multiplier`) with the
contextual SAT theorem (:func:`symq.labs.contextual_substitution.check_substitution`). The
factor certificate is never taken as a cut proof: the replacement is proved in place, once,
under the caller's input/cut contract, and the source is never mutated.

All guarantees concern reversible X/CX/CCX/MCX circuits on basis states. A restricted classical
predicate is not a coherent quantum channel theorem.
"""
from __future__ import annotations

from dataclasses import replace

from symq.circuit import Circuit
from symq.generators.gf2n import tower_multiplier
from symq.labs.contextual_substitution import (
    SubstitutionContract,
    SubstitutionResult,
    check_substitution,
)
from symq.labs.rewrite import Weights
from symq.resources import Budget

__all__ = ["apply_tower_substitution", "mapped_tower_multiplier"]


def mapped_tower_multiplier(width: int, n: int, modulus: int, wires: tuple[int, ...],
                            strategy: str = "pivot-scheduled") -> Circuit:
    """The tower multiplier on ``width`` wires; local ``(a, b, z)`` bits go to ``wires``."""
    if (type(wires) is not tuple or len(wires) != 3 * n
            or any(type(w) is not int or not 0 <= w < width for w in wires)
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
    weights: Weights,
    budget: Budget | None = None,
    strategy: str = "pivot-scheduled",
    require_saving: bool = True,
) -> SubstitutionResult:
    """Replace ``source[span]`` by a tower multiplier on ``wires`` and prove it in place.

    The result carries the candidate only when the rewrite is proved and, if
    ``require_saving``, strictly cheaper under the declared ``weights``. A stale source, wrong
    polynomial or mapping, unproved cut or restoration returns no candidate.
    """
    if type(source) is not Circuit:
        raise TypeError("source must be a reversible Circuit")
    if type(weights) is not Weights:
        raise TypeError("explicit symq.labs.rewrite.Weights are required")
    if type(require_saving) is not bool:
        raise TypeError("require_saving must be a Boolean")
    replacement = mapped_tower_multiplier(source.width, n, modulus, wires, strategy)
    result = check_substitution(source, span, replacement, contract=contract, weights=weights,
                                budget=budget)
    if result.candidate is not None and require_saving and result.cost.weighted_delta >= 0:
        return replace(result, candidate=None, _token=None,
                       reason=result.reason + "; not applied: no saving under the declared weights")
    return result
