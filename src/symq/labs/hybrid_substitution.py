"""Bounded, coherent hybrid substitutions at an exact global instruction span.

Research-only convenience adapter around the established exact local transcript
theorem. Local leaf comparison includes all coherent |x><y| matrix units, not
just basis-state behavior. This is NOT a general quantum circuit compiler.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from symq.circuit import UnsupportedOperation
from symq.experimental.hybrid import HOp, HybridProgram
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import (
    ChannelSlot,
    FrozenHybridProgram,
    HybridCommon,
    HybridFragment,
    TranscriptMismatch,
    UnprovedSubstitution,
    hybrid_digest,
    verify_channel_transcript,
)
from symq.labs.rewrite import (
    CostReport,
    VerdictFields,
    Weights,
    _proved,
    call_budget,
    check_receipt,
    check_span,
    cost_report,
    gate_key,
)
from symq.resources import Budget, ResourceLimitExceeded, VerificationSession

__all__ = ["LIMIT_CAPS", "HybridSubstitutionResult", "check_hybrid_substitution",
           "replay_hybrid_substitution"]

_SLOT = re.compile(r"b(0|[1-9][0-9]*)\Z")
LIMIT_CAPS = {"max_local_width": 8, "max_events": 12, "max_branches": 4096}
"""Hard ceilings on the bounded local coherent oracle, whatever the caller requests: its cost
grows with 4**width coherences times the measurement branches."""


def _classical_names(ops: tuple[HOp, ...]) -> set[str]:
    return {
        name for op in ops
        for name in (
            op.slot,
            op.source,
            op.condition.removeprefix("!") if op.condition is not None else None,
        )
        if name is not None
    }


def _localize(op: HOp, inverse: dict[int, int]) -> HOp:
    if any(q not in inverse for q in op.wires):
        raise ValueError("the selected span touches a wire outside the declared local frame")
    return HOp(
        op.kind, tuple(inverse[q] for q in op.wires),
        op.slot, op.condition, op.source, op.value,
    )


def _globalize(op: HOp, wires: tuple[int, ...]) -> HOp:
    return HOp(
        op.kind, tuple(wires[q] for q in op.wires),
        op.slot, op.condition, op.source, op.value,
    )


@dataclass(frozen=True)
class HybridSubstitutionResult(VerdictFields):
    """Outcome of one coherent substitution; ``candidate`` only when proved in this call.

    ``theorem`` is the comparison actually run: ``local_coherent_channel`` when every local
    measurement record is forgotten, ``local_coherent_instrument`` when a later operation reads
    one (``instrument_slots``), which is the stronger obligation.
    """

    outcome: str
    reason: str
    reference_sha256: str
    candidate_sha256: str
    contract_sha256: str
    span: tuple[int, int]
    local_to_global_wires: tuple[int, ...]
    cost: CostReport
    checked_pairs: int = 0
    theorem: str = "local_coherent_channel"
    instrument_slots: tuple[str, ...] = ()
    candidate: FrozenHybridProgram | None = field(default=None, compare=False, repr=False)
    _token: Any = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        self._check_fields()

    def _candidate_digest(self, candidate: Any) -> str:
        if type(candidate) is not FrozenHybridProgram:
            raise TypeError("the candidate must be a FrozenHybridProgram")
        return hybrid_digest(candidate)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 2, "kind": "symq_hybrid_substitution",
                "outcome": self.outcome, "reason": self.reason, "theorem": self.theorem,
                "instrument_slots": list(self.instrument_slots),
                "reference_sha256": self.reference_sha256,
                "candidate_sha256": self.candidate_sha256,
                "contract_sha256": self.contract_sha256, "span": list(self.span),
                "local_to_global_wires": list(self.local_to_global_wires),
                "checked_pairs": self.checked_pairs, "cost": self.cost.to_dict()}


def _priced(ops: tuple[HOp, ...]) -> list[str]:
    return [gate_key(op.kind, len(op.wires)) for op in ops]


def check_hybrid_substitution(
    source: HybridProgram,
    span: tuple[int, int],
    replacement: HybridFragment,
    *,
    wires: tuple[int, ...],
    clean: tuple[int, ...] = (),
    preserved: tuple[int, ...] = (),
    discarded: tuple[int, ...] = (),
    observed_slots: tuple[str, ...] = (),
    discarded_global: tuple[int, ...] = (),
    weights: Weights | None = None,
    budget: Budget | None = None,
    max_local_width: int = 6,
    max_events: int = 8,
    max_branches: int = 256,
) -> HybridSubstitutionResult:
    """Check one replacement using complete, frozen global operation streams.

    The replacement uses local wires 0..len(wires)-1. Existing classical names
    must be spelled *identically* on both sides; new names may be introduced
    but are not silently renamed. Incoming classical bits are explicitly named
    by replacement.classical_inputs and universally quantified.

    The prefix must prove every clean cut wire zero. Arbitrary preserved dirty
    wires must have the identity channel, including off-diagonal correlations.
    A live classical slot in the suffix triggers instrument comparison.
    The quantum input frame is source.data arbitrary coherent wires and
    source.ancillas explicitly zero-prepared qubits. No classical input-domain
    shortcut is applied to a quantum theorem. Optional integer operation
    weights are an explicit cost proxy only; they never change proof decisions.
    """
    # The whole-call deadline starts before freezing, localizing and hashing.
    budget = call_budget(budget)
    if type(source) is not HybridProgram or type(replacement) is not HybridFragment:
        raise TypeError("HybridProgram source and immutable HybridFragment replacement required")
    frozen = FrozenHybridProgram.freeze(source)
    check_span(span, len(frozen.ops))
    if (type(wires) is not tuple or len(wires) != replacement.width
            or any(type(w) is not int or not 0 <= w < frozen.width for w in wires)
            or len(set(wires)) != len(wires)):
        raise ValueError("wires must injectively map the entire local frame to global wires")
    if budget.max_nodes is not None or budget.max_bytes is not None:
        raise ValueError("hybrid exact oracle cannot enforce node/byte budgets")
    weights = Weights() if weights is None else weights
    if type(weights) is not Weights:
        raise TypeError("weights must be symq.labs.rewrite.Weights")
    for name, value in (("max_local_width", max_local_width), ("max_events", max_events),
                        ("max_branches", max_branches)):
        if type(value) is not int or not 1 <= value <= LIMIT_CAPS[name]:
            raise ValueError(f"{name} must be an integer in 1..{LIMIT_CAPS[name]}")
    if (type(observed_slots) is not tuple
            or any(type(s) is not str or not _SLOT.fullmatch(s) for s in observed_slots)):
        raise ValueError("observed_slots must be a tuple of classical slot names b<N>")

    start, stop = span
    inverse = {q: i for i, q in enumerate(wires)}
    local_reference = HybridFragment(
        replacement.width,
        tuple(_localize(op, inverse) for op in frozen.ops[start:stop]),
        replacement.classical_inputs,
    )
    # The interface is intentionally identity-only in this first version.
    # Every slot mentioned on either side is in the total classical mapping.
    names = _classical_names(local_reference.ops) | _classical_names(replacement.ops)
    names |= set(replacement.classical_inputs)
    classical_map = tuple((name, name) for name in sorted(names))
    slot = ChannelSlot(
        local_reference, replacement, wires, classical_map,
        clean=clean, preserved=preserved, discarded=discarded,
    )
    candidate_ops = (
        frozen.ops[:start]
        + tuple(_globalize(op, wires) for op in replacement.ops)
        + frozen.ops[stop:]
    )
    global_reference = frozen.to_program()
    global_candidate = HybridProgram(frozen.data, frozen.ancillas, list(candidate_ops))
    ref_hash, cand_hash = hybrid_digest(frozen), hybrid_digest(global_candidate)
    contract_hash = canonical_sha256({
        "schema_version": 1, "kind": "hybrid_contextual_substitution",
        "span": list(span), "wires": list(wires),
        # Sets of wires and slots: hashed in a canonical order, as the classical contract is.
        "clean": sorted(clean), "preserved": sorted(preserved), "discarded": sorted(discarded),
        "observed_slots": sorted(observed_slots), "discarded_global": sorted(discarded_global),
        "classical_inputs": list(replacement.classical_inputs),
        "max_local_width": max_local_width, "max_events": max_events,
        "max_branches": max_branches,
    })
    cost = cost_report(_priced(frozen.ops), _priced(candidate_ops), weights)

    def result(outcome: str, reason: str,
               instrument: tuple[str, ...] = ()) -> HybridSubstitutionResult:
        return HybridSubstitutionResult(
            outcome, reason, ref_hash, cand_hash, contract_hash, span, wires, cost,
            theorem="local_coherent_instrument" if instrument else "local_coherent_channel",
            instrument_slots=instrument)

    steps = (
        HybridCommon(frozen.ops[:start]),
        slot,
        HybridCommon(frozen.ops[stop:]),
    )
    try:
        with VerificationSession(budget) as session:
            proof = verify_channel_transcript(
                global_reference, global_candidate, steps,
                reference_sha256=ref_hash, candidate_sha256=cand_hash,
                observed_slots=observed_slots, discarded_global=discarded_global,
                budget=session.remaining_budget(), max_local_width=max_local_width,
                max_events=max_events, max_branches=max_branches,
            )
            session.check_time()
            instrument = proof.instrument_slots
            return _proved(
                HybridSubstitutionResult,
                FrozenHybridProgram(frozen.data, frozen.ancillas, candidate_ops),
                reason="the actual transcript and every local coherent obligation passed",
                reference_sha256=ref_hash, candidate_sha256=cand_hash,
                contract_sha256=contract_hash, span=span, local_to_global_wires=wires,
                cost=cost, checked_pairs=proof.checked_pairs,
                theorem=("local_coherent_instrument" if instrument
                         else "local_coherent_channel"),
                instrument_slots=instrument)
    except TranscriptMismatch as exc:
        return result("precondition_failed", str(exc))
    except UnprovedSubstitution as exc:
        return result("not_proved", str(exc), exc.instrument_slots)
    except ResourceLimitExceeded as exc:
        return result("inconclusive", str(exc))
    except UnsupportedOperation as exc:
        return result("unsupported", str(exc))


def replay_hybrid_substitution(
    receipt: HybridSubstitutionResult,
    source: HybridProgram,
    span: tuple[int, int],
    replacement: HybridFragment,
    *,
    wires: tuple[int, ...],
    clean: tuple[int, ...] = (),
    preserved: tuple[int, ...] = (),
    discarded: tuple[int, ...] = (),
    observed_slots: tuple[str, ...] = (),
    discarded_global: tuple[int, ...] = (),
    budget: Budget | None = None,
    max_local_width: int = 6,
    max_events: int = 8,
    max_branches: int = 256,
) -> HybridSubstitutionResult:
    """Rerun the coherent proof from exact inputs and bind it to a typed receipt.

    A stored receipt, its status and its hashes are not an independent certificate. The
    full local channel/instrument obligation is recomputed with the receipt's weights;
    :class:`symq.labs.rewrite.ReceiptMismatch` is raised when the streams, contract, mapping or
    costs differ. Only the fresh result can be acted on, and only it carries the candidate.
    """
    if type(receipt) is not HybridSubstitutionResult:
        raise TypeError("a typed HybridSubstitutionResult receipt is required")
    fresh = check_hybrid_substitution(
        source, span, replacement, wires=wires, clean=clean,
        preserved=preserved, discarded=discarded,
        observed_slots=observed_slots, discarded_global=discarded_global,
        weights=receipt.cost.weights, budget=budget,
        max_local_width=max_local_width, max_events=max_events,
        max_branches=max_branches,
    )
    check_receipt(receipt, fresh, ("reference_sha256", "candidate_sha256", "contract_sha256",
                                   "span", "local_to_global_wires", "cost"))
    return fresh
