"""Exact full-input GF(2^24) rewriting through SymQ's pinned transcript engine.

The local theorem is *all-input, all-output* equivalence of reversible
X/CX/CCX operations. It is stronger than an unproved cut assumption: an
equal local permutation may be inserted into any identical classical
prefix/suffix. It is NOT restricted-input SAT, HMR, instrument equivalence,
phase-tolerant rewrite, or a claim about general quantum gate grammars.

An exact degree-<=2 packed ANF backend checks the ACTUAL two gate streams.
No factorization certificate, cost improvement, or saved receipt is ever
accepted as sufficient evidence on its own. Failures do not return an
applied circuit. The original and replacement are frozen before proof and
replayed under one absolute deadline before application.
"""
from __future__ import annotations

from dataclasses import dataclass

from symq.circuit import Circuit, Gate
from symq.generators.gf2n import emit, karatsuba, schoolbook
from symq.labs.classical_transcript import (
    Common,
    Program,
    Slot,
    TranscriptProof,
    digest,
    verify_transcript,
)
from symq.labs.gf24_order import reordered_gf24_circuit
from symq.labs.gf24_tower import gf24_tower_factors
from symq.resources import Budget, Guard

__all__ = [
    "GF24AppliedRewrite",
    "GF24GateWeights",
    "GF24RewriteCost",
    "apply_gf24_rewrite",
    "replay_gf24_rewrite",
]

GF24_WIDTH = 24
LOCAL_WIDTH = 3 * GF24_WIDTH
MAX_GLOBAL_WIDTH = 96
MAX_GLOBAL_GATES = 12_000
_METHODS = (
    "tower-99-pinned-order",
    "tower-99-pivot-scheduled",
    "karatsuba-pivot-scheduled",
    "schoolbook-incidence",
)


@dataclass(frozen=True)
class GF24GateWeights:
    """Explicit integer gate proxy, not T-count or official competition cost."""

    ccx: int
    cx: int

    def __post_init__(self) -> None:
        if (type(self.ccx) is not int or self.ccx < 0
                or type(self.cx) is not int or self.cx < 0
                or self.ccx + self.cx == 0):
            raise ValueError("nonnegative integer CCX/CX weights, not both zero, are required")


@dataclass(frozen=True)
class GF24RewriteCost:
    before_ccx: int
    before_cx: int
    after_ccx: int
    after_cx: int
    before_weighted: int
    after_weighted: int
    delta: int
    weights: GF24GateWeights


@dataclass(frozen=True)
class GF24AppliedRewrite:
    """Immutable, *freshly proven* frozen full-stream substitution.

    This object is a receipt, not a transferable UNSAT certificate.
    Replay against exact source contents before use in a new context.
    """

    candidate: Program
    proof: TranscriptProof
    original_sha256: str
    candidate_sha256: str
    span: tuple[int, int]
    wires: tuple[int, ...]
    preserved: tuple[int, ...]
    method: str
    cost: GF24RewriteCost
    theorem: str = "classical-total-permutation-packed-anf"

    def __post_init__(self) -> None:
        if type(self.candidate) is not Program or type(self.proof) is not TranscriptProof:
            raise TypeError("frozen candidate and exact typed proof are required")
        if self.proof.backend != "packed":
            raise ValueError("only exact packed degree-two ANF proof is admitted")
        if (digest(self.candidate) != self.candidate_sha256
                or self.proof.reference_sha256 != self.original_sha256
                or self.proof.candidate_sha256 != self.candidate_sha256):
            raise ValueError("frozen candidate and proof fingerprints disagree")


def _compiled(method: str) -> Circuit:
    if type(method) is not str or method not in _METHODS:
        raise ValueError("unknown GF24 synthesis method")
    if method == "tower-99-pinned-order":
        return reordered_gf24_circuit()
    if method == "tower-99-pivot-scheduled":
        return emit(GF24_WIDTH, list(gf24_tower_factors()),
                    strategy="pivot-scheduled").circuit
    if method == "karatsuba-pivot-scheduled":
        return emit(GF24_WIDTH, karatsuba(GF24_WIDTH),
                    strategy="pivot-scheduled").circuit
    return emit(GF24_WIDTH, schoolbook(GF24_WIDTH)).circuit


def _cost(original: tuple[Gate, ...], candidate: tuple[Gate, ...],
          weights: GF24GateWeights) -> GF24RewriteCost:
    for name, gates in (("original", original), ("candidate", candidate)):
        if any(gate.name not in {"cx", "ccx"} for gate in gates):
            raise ValueError(name + " block includes gates outside the declared CX/CCX proxy")
    a_ccx = sum(g.name == "ccx" for g in original)
    b_ccx = sum(g.name == "ccx" for g in candidate)
    a_cx = len(original) - a_ccx
    b_cx = len(candidate) - b_ccx
    old = weights.ccx * a_ccx + weights.cx * a_cx
    new = weights.ccx * b_ccx + weights.cx * b_cx
    return GF24RewriteCost(a_ccx, a_cx, b_ccx, b_cx, old, new, new - old, weights)


def _verify(
    source: Program, candidate: Program, reference: Program, replacement: Program,
    span: tuple[int, int], preserved: tuple[int, ...], budget: Budget,
) -> TranscriptProof:
    """Build a strict complete transcript; no unproved cuts or assumed interface."""
    start, stop = span
    steps = (
        Common(source.gates[:start]),
        Slot(reference, replacement, tuple(range(source.width)), preserved=preserved),
        Common(source.gates[stop:]),
    )
    return verify_transcript(
        source.circuit(),
        candidate.circuit(),
        steps,
        reference_sha256=digest(source),
        candidate_sha256=digest(candidate),
        backend="packed",
        budget=budget,
        max_expanded_gates=MAX_GLOBAL_GATES,
    )


def apply_gf24_rewrite(
    source: Circuit,
    span: tuple[int, int],
    *,
    wires: tuple[int, ...],
    weights: GF24GateWeights,
    preserved: tuple[int, ...] = (),
    method: str = "tower-99-pinned-order",
    require_saving: bool = True,
    budget: Budget | None = None,
) -> GF24AppliedRewrite:
    """Apply only after exact degree-two *all-input* verification and replay.

    The 72 local (a,b,z) wires map injectively into the original circuit.
    No ancillas, clean-wire assertions, input predicates or basis restrictions
    are inferred. Every other wire and the complete global suffix/prefix are
    part of the pinned original/candidate streams. A wrong local operation,
    unsupported polynomial degree, timeout or stale source fails closed.
    """
    if type(weights) is not GF24GateWeights:
        raise TypeError("GF24GateWeights are required")
    if type(require_saving) is not bool:
        raise TypeError("require_saving must be boolean")
    if budget is not None and type(budget) is not Budget:
        raise TypeError("budget must be Budget or None")
    requested = budget if budget is not None else Budget(max_seconds=30, max_terms=4000)
    if requested.max_nodes is not None or requested.max_bytes is not None:
        raise ValueError("packed ANF cannot enforce node/byte resource limits")
    guard = Guard(requested)
    shared = Budget(requested.max_terms, absolute_deadline=guard.deadline)
    original = Program.freeze(source)
    if (original.width > MAX_GLOBAL_WIDTH or len(original.gates) > MAX_GLOBAL_GATES):
        raise ValueError("GF24 contextual experiment exceeds pinned width/gate limits")
    if (type(span) is not tuple or len(span) != 2
            or any(type(x) is not int for x in span)
            or not 0 <= span[0] <= span[1] <= len(original.gates)):
        raise ValueError("invalid source [start,stop) span")
    if (type(wires) is not tuple or len(wires) != LOCAL_WIDTH
            or any(type(x) is not int or x < 0 or x >= original.width for x in wires)
            or len(set(wires)) != LOCAL_WIDTH):
        raise ValueError("72 unique in-range global wires are required")
    if (type(preserved) is not tuple
            or any(type(x) is not int or x < 0 or x >= original.width for x in preserved)
            or len(set(preserved)) != len(preserved)):
        raise ValueError("preserved wire list must be a unique in-range tuple")

    local = _compiled(method)
    mapped = tuple(
        Gate(g.name, tuple(wires[q] for q in g.qubits)) for g in local.gates
    )
    start, stop = span
    cut = Program(original.width, original.gates[start:stop])
    replacement = Program(original.width, mapped)
    candidate = Program(
        original.width, original.gates[:start] + mapped + original.gates[stop:]
    )
    report = _cost(cut.gates, mapped, weights)
    guard.check_time()
    # Cost policy is independent of proof and cannot justify a substitution.
    if require_saving and report.delta >= 0:
        raise ValueError("no strict reduction under the declared GF24 gate-weight proxy")

    proof = _verify(original, candidate, cut, replacement, span, preserved, shared)
    guard.check_time()
    # Replay against the SAME frozen source/candidate; neither the stored
    # result nor the caller's mutable gate list is reopened as authority.
    replayed = _verify(original, candidate, cut, replacement, span, preserved, shared)
    guard.check_time()
    if (proof.reference_sha256 != replayed.reference_sha256
            or proof.candidate_sha256 != replayed.candidate_sha256
            or replayed.backend != "packed"):
        raise ValueError("GF24 replay differs from the original pinned theorem")
    applied = GF24AppliedRewrite(
        candidate, replayed, digest(original), digest(candidate),
        span, wires, preserved, method, report,
    )
    guard.check_time()
    return applied


def replay_gf24_rewrite(
    receipt: GF24AppliedRewrite, source: Circuit, *, budget: Budget | None = None,
) -> GF24AppliedRewrite:
    """Recompute from caller source, reject forged/stale cost or witness claims."""
    if type(receipt) is not GF24AppliedRewrite:
        raise TypeError("a typed GF24 application receipt is required")
    fresh = apply_gf24_rewrite(
        source, receipt.span, wires=receipt.wires, weights=receipt.cost.weights,
        preserved=receipt.preserved, method=receipt.method,
        require_saving=False, budget=budget,
    )
    if (fresh.original_sha256, fresh.candidate_sha256, fresh.cost, fresh.theorem) != (
        receipt.original_sha256, receipt.candidate_sha256, receipt.cost, receipt.theorem
    ):
        raise ValueError("GF24 receipt differs from source, candidate, theorem or costs")
    return fresh
