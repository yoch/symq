"""Bounded, coherent hybrid substitutions at an exact global instruction span.

Research-only convenience adapter around the established exact local transcript
theorem. Local leaf comparison includes all coherent |x><y| matrix units, not
just basis-state behavior. This is NOT a general quantum circuit compiler.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from symq.circuit import UnsupportedOperation
from symq.errors import SymqError
from symq.experimental.hybrid import HOp, HybridProgram
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import (
    ChannelSlot,
    FrozenHybridProgram,
    HybridCommon,
    HybridFragment,
    UnprovedSubstitution,
    hybrid_digest,
    verify_channel_transcript,
)
from symq.resources import Budget, ResourceLimitExceeded, VerificationSession

_SLOT = re.compile(r"b(0|[1-9][0-9]*)\Z")


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
class HybridCostReport:
    """Raw operation counts, never an asserted fault-tolerant or hardware cost."""

    reference_ops: int
    candidate_ops: int
    delta_ops: int
    reference_counts: tuple[tuple[str, int], ...]
    candidate_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class HybridSubstitutionResult:
    outcome: str
    reason: str
    reference_sha256: str
    candidate_sha256: str
    contract_sha256: str
    span: tuple[int, int]
    local_to_global_wires: tuple[int, ...]
    cost: HybridCostReport
    checked_pairs: int = 0
    theorem: str = "local_coherent_channel_or_instrument"

    @property
    def equivalent(self) -> bool:
        return self.outcome == "equivalent"

    @property
    def certified(self) -> bool:
        return self.equivalent

    @property
    def different(self) -> bool:
        # Local counterexamples may be unreachable from the global prefix.
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, **asdict(self)}


def _cost(before: tuple[HOp, ...], after: tuple[HOp, ...]) -> HybridCostReport:
    a, b = Counter(op.kind for op in before), Counter(op.kind for op in after)
    return HybridCostReport(
        len(before), len(after), len(after)-len(before),
        tuple(sorted(a.items())), tuple(sorted(b.items())),
    )


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
    shortcut is applied to a quantum theorem.
    """
    if type(source) is not HybridProgram or type(replacement) is not HybridFragment:
        raise TypeError("HybridProgram source and immutable HybridFragment replacement required")
    frozen = FrozenHybridProgram.freeze(source)
    if (type(span) is not tuple or len(span) != 2
            or any(type(v) is not int for v in span)
            or not 0 <= span[0] <= span[1] <= len(frozen.ops)):
        raise ValueError("span must be a valid [start, stop) global operation interval")
    if (type(wires) is not tuple or len(wires) != replacement.width
            or any(type(w) is not int or not 0 <= w < frozen.width for w in wires)
            or len(set(wires)) != len(wires)):
        raise ValueError("wires must injectively map the entire local frame to global wires")
    if budget is not None and not isinstance(budget, Budget):
        raise TypeError("budget must be Budget or None")
    if budget is not None and (budget.max_nodes is not None or budget.max_bytes is not None):
        raise ValueError("hybrid exact oracle cannot enforce node/byte budgets")
    if any(type(s) is not str or not _SLOT.fullmatch(s) for s in observed_slots):
        raise ValueError("invalid observed classical slot")

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
        "clean": list(clean), "preserved": list(preserved), "discarded": list(discarded),
        "observed_slots": list(observed_slots), "discarded_global": list(discarded_global),
        "classical_inputs": list(replacement.classical_inputs),
        "max_local_width": max_local_width, "max_events": max_events,
        "max_branches": max_branches,
    })
    cost = _cost(frozen.ops, candidate_ops)

    def result(outcome: str, reason: str, checked: int = 0) -> HybridSubstitutionResult:
        return HybridSubstitutionResult(
            outcome, reason, ref_hash, cand_hash, contract_hash, span,
            wires, cost, checked,
        )

    steps = (
        HybridCommon(frozen.ops[:start]),
        slot,
        HybridCommon(frozen.ops[stop:]),
    )
    try:
        with VerificationSession(budget or Budget(max_seconds=30)) as session:
            proof = verify_channel_transcript(
                global_reference, global_candidate, steps,
                reference_sha256=ref_hash, candidate_sha256=cand_hash,
                observed_slots=observed_slots, discarded_global=discarded_global,
                budget=session.remaining_budget(), max_local_width=max_local_width,
                max_events=max_events, max_branches=max_branches,
            )
            session.check_time()
            return result("equivalent",
                          "the actual transcript and every local coherent obligation passed",
                          proof.checked_pairs)
    except UnprovedSubstitution as exc:
        return result("not_proved", str(exc))
    except ResourceLimitExceeded as exc:
        return result("inconclusive", str(exc))
    except UnsupportedOperation as exc:
        return result("unsupported", str(exc))
