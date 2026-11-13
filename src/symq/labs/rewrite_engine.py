"""Conservative, explainable backend advice for *classical* contextual rewrites.

This policy never guesses or weakens a precondition. A nonempty input-domain,
clean-cut, restored-wire or cut-assumption contract requires the SAT contextual
theorem. For the empty contract we may prove the strictly STRONGER total
permutation theorem via a deterministic symbolic engine.

Linear (X/CX) and packed (provably degree <=2) selection is based on the real
SOURCE interval and replacement gate stream. The quadratic test is an upper
bound by abstract interpretation, not a factor certificate or equivalence
claim: the selected backend still verifies the actual gates.
"""
from __future__ import annotations

from dataclasses import dataclass

from symq.circuit import Circuit
from symq.labs.contextual_substitution import SubstitutionContract

__all__ = ["EngineAdvice", "is_unconditional", "quadratic_bounded",
           "recommend_rewrite_engine"]


@dataclass(frozen=True)
class EngineAdvice:
    engine: str
    theorem: str
    reason: str
    proof: str = "advice_only_not_a_verdict"

    def to_dict(self) -> dict[str, str]:
        return {
            "engine": self.engine, "theorem": self.theorem,
            "reason": self.reason, "proof": self.proof,
        }


def quadratic_bounded(circuit: Circuit) -> bool:
    """Conservative bound on all ANF degrees, including intermediate states.

    An X toggles a constant; CX applies a degree-1 product; CCX multiplies
    both controls. If the sum of the controls' upper degree bounds is <= 2,
    every intermediate and final polynomial is representable by 'packed'.
    Conservative false negatives only choose a more general verifier.
    """
    if type(circuit) is not Circuit:
        raise TypeError("a reversible Circuit is required")
    circuit.validate()
    degree = [1] * circuit.width
    for gate in circuit.gates:
        *controls, target = gate.qubits
        bound = sum(degree[q] for q in controls)
        if bound > 2:
            return False
        degree[target] = max(degree[target], bound)
    return True


def is_unconditional(contract: SubstitutionContract) -> bool:
    """Every contract field is empty: complete-block equality is then the whole obligation.

    An empty set of predicate variables is not enough (``Const(False)`` still needs a domain
    obligation) and restoration is independent of the predicates, so only exact emptiness counts.
    """
    return contract == SubstitutionContract()


def recommend_rewrite_engine(
    source: Circuit, span: tuple[int, int],
    replacement: Circuit, contract: SubstitutionContract,
) -> EngineAdvice:
    """Suggest a safe verifier, never an implicit proof or contract relaxation."""
    if type(source) is not Circuit or type(replacement) is not Circuit:
        raise TypeError("source and replacement must be Circuits")
    source.validate()
    replacement.validate()
    if source.width != replacement.width:
        raise ValueError("replacement must use the full source width")
    if (type(span) is not tuple or len(span) != 2
            or any(type(x) is not int for x in span)
            or not 0 <= span[0] <= span[1] <= len(source.gates)):
        raise ValueError("invalid [start, stop) instruction span")
    if type(contract) is not SubstitutionContract:
        raise TypeError("explicit SubstitutionContract required")
    contract.validate(source.width)
    if not is_unconditional(contract):
        return EngineAdvice(
            "sat", "classical_contextual_full",
            "nonempty input/cut/restoration contract: must prove its real prefix and obligations",
        )

    block = Circuit(source.width, list(source.gates[span[0]:span[1]]))
    gates = [*block.gates, *replacement.gates]
    if all(g.name in ("x", "cx") for g in gates):
        return EngineAdvice(
            "linear", "classical_total",
            "both blocks are affine X/CX: exact linear symbolic permutation theorem",
        )
    if quadratic_bounded(block) and quadratic_bounded(replacement):
        return EngineAdvice(
            "packed", "classical_total",
            "both blocks have a conservative degree-two upper bound: exact packed ANF",
        )
    if source.width > 256:
        return EngineAdvice(
            "sat", "classical_contextual_full",
            "no bounded symbolic engine covers this higher-degree width; "
            "SAT with the empty contract remains sound",
        )
    # The Python ZDD works without optional compiled dependencies. It may be
    # slower on some circuits but never silently replaces the theorem.
    return EngineAdvice(
        "zdd", "classical_total",
        "unrestricted input domain and higher-degree blocks: exact ZDD symbolic theorem",
    )
