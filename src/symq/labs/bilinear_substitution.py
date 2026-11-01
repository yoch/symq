"""GF(2^n) multiplier rewrites at an exact span of a classical circuit (research API).

* :func:`apply_tower_substitution` replaces a GF(16)/GF(64) multiplier block by the certified
  tower multiplier and proves it with the contextual SAT theorem under the caller's contract.
* :func:`gf24_rewrite` replaces a GF(2^24) multiplier block by the circuit
  :func:`symq.labs.gf24_choice.choose_gf24` selects (or a named one) and proves the *total*
  theorem with the exact packed degree-two engine: the block and its replacement agree on every
  input, so no contract is involved.

A factor certificate is never taken as a proof of the insertion: every replacement is proved in
place, once, and the source is never mutated. All guarantees concern reversible X/CX/CCX
circuits on basis states.
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

__all__ = ["apply_tower_substitution", "gf24_rewrite", "mapped_circuit", "mapped_tower_multiplier"]


def mapped_circuit(local: Circuit, width: int, wires: tuple[int, ...]) -> Circuit:
    """``local`` on ``width`` wires, local wire ``i`` becoming global wire ``wires[i]``."""
    if (type(wires) is not tuple or len(wires) != local.width
            or any(type(w) is not int or not 0 <= w < width for w in wires)
            or len(set(wires)) != len(wires)):
        raise ValueError(f"wires must be {local.width} distinct, in-range global wire indices")
    mapped = Circuit(width)
    for gate in local.gates:
        mapped.append(gate.name, *(wires[wire] for wire in gate.qubits))
    return mapped


def mapped_tower_multiplier(width: int, n: int, modulus: int, wires: tuple[int, ...],
                            strategy: str = "pivot-scheduled") -> Circuit:
    """The tower multiplier on ``width`` wires; local ``(a, b, z)`` bits go to ``wires``."""
    return mapped_circuit(tower_multiplier(n, modulus=modulus, strategy=strategy), width, wires)


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


GF24_METHODS = ("schoolbook-incidence", "karatsuba-pivot-scheduled", "tower-99-pinned-order")


def gf24_rewrite(
    source: Circuit,
    span: tuple[int, int],
    *,
    wires: tuple[int, ...],
    weights: Weights,
    method: str | None = None,
    budget: Budget | None = None,
    require_saving: bool = True,
) -> tuple[str, SubstitutionResult]:
    """Replace ``source[span]`` by a GF(2^24) multiplier on ``wires`` and prove it exactly.

    ``wires`` maps the 72 local ``(a, b, z)`` bits to global wires. ``method`` names one of
    :data:`GF24_METHODS`; by default the cheapest under ``weights`` (priced ``ccx`` and ``cx``)
    is chosen. The proof is the total theorem with the ``packed`` engine, so an original block
    of degree above two is ``unsupported`` rather than guessed.
    """
    from symq.labs.gf24_choice import choose_gf24
    from symq.labs.gf24_order import pinned_gf24_circuit

    if type(weights) is not Weights:
        raise TypeError("explicit symq.labs.rewrite.Weights are required")
    if method is None:
        choice = choose_gf24(ccx_weight=weights.weight("ccx"), cx_weight=weights.weight("cx"))
        method, local = choice.method, choice.circuit
    elif method == "tower-99-pinned-order":
        local = pinned_gf24_circuit()
    elif method == "karatsuba-pivot-scheduled":
        from symq.generators.gf2n import emit, karatsuba

        local = emit(24, karatsuba(24), strategy="pivot-scheduled").circuit
    elif method == "schoolbook-incidence":
        from symq.generators.gf2n import emit, schoolbook

        local = emit(24, schoolbook(24)).circuit
    else:
        raise ValueError(f"method must be one of {GF24_METHODS}")
    replacement = mapped_circuit(local, source.width, wires)
    result = check_substitution(source, span, replacement, contract=SubstitutionContract(),
                                weights=weights, budget=budget, engine="packed")
    if result.candidate is not None and require_saving and result.cost.weighted_delta >= 0:
        result = replace(result, candidate=None, _token=None,
                         reason=result.reason + "; not applied: no saving under the declared weights")
    return method, result
