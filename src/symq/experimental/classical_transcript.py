"""Experimental exact temporal substitution of fully pinned reversible streams.

This proves total classical permutation equivalence, NOT phase/HMR/channel
equivalence nor correctness of the alleged reference algorithm.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from symq.backends import make_algebra, simulate
from symq.circuit import Circuit, Gate, UnsupportedOperation
from symq.equivalence import check_equivalence
from symq.resources import Budget, Guard, ResourceLimitExceeded, session_scoped


class TranscriptMismatch(ValueError):
    """The transcript or the separately trusted source hashes do not match."""


class UnprovedSubstitution(ValueError):
    """An exact local all-input, all-output or restoration obligation failed."""

    def __init__(self, slot: int, reason: str, witness: int | None = None):
        self.slot = slot
        self.witness = witness
        super().__init__(f"slot {slot}: {reason}")


@dataclass(frozen=True)
class Program:
    width: int
    gates: tuple[Gate, ...]

    def __post_init__(self) -> None:
        if type(self.width) is not int or self.width < 1:
            raise ValueError("positive program width required")
        if type(self.gates) is not tuple:
            raise TypeError("immutable gate tuple required")
        # Circuit.validate independently rejects injected or malformed gate objects.
        Circuit(self.width, list(self.gates))

    @classmethod
    def freeze(cls, source: Circuit) -> Program:
        if type(source) is not Circuit:
            raise TypeError("a validated Circuit is required")
        source.validate()
        return cls(source.width, tuple(source.gates))

    def circuit(self) -> Circuit:
        return Circuit(self.width, list(self.gates))


def digest(program: Program) -> str:
    """Canonical exact stream fingerprint, independent of a branch name."""
    data = {
        "kind": "classical_reversible",
        "width": program.width,
        "gates": [[gate.name, list(gate.qubits)] for gate in program.gates],
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Common:
    """Globally numbered, byte/IR-identical operations on both sides."""
    gates: tuple[Gate, ...]

    def __post_init__(self) -> None:
        if type(self.gates) is not tuple or any(type(g) is not Gate for g in self.gates):
            raise TypeError("common gates must be a tuple of validated Gate objects")


@dataclass(frozen=True)
class Slot:
    reference: Program
    candidate: Program
    wires: tuple[int, ...]
    preserved: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.reference) is not Program or type(self.candidate) is not Program:
            raise TypeError("frozen local programs required")
        if self.reference.width != self.candidate.width:
            raise ValueError("local widths differ")
        if type(self.wires) is not tuple or len(self.wires) != self.reference.width:
            raise ValueError("local-to-global map must cover every local wire")
        if any(type(w) is not int or w < 0 for w in self.wires):
            raise ValueError("invalid global wire")
        if len(set(self.wires)) != len(self.wires):
            raise ValueError("non-injective local-to-global map")
        if type(self.preserved) is not tuple:
            raise ValueError("preserved local wires must be a tuple")
        if len(set(self.preserved)) != len(self.preserved) or any(
            type(w) is not int or w < 0 or w >= self.reference.width for w in self.preserved
        ):
            raise ValueError("invalid or repeated preserved wire")


@dataclass(frozen=True)
class TranscriptProof:
    reference_sha256: str
    candidate_sha256: str
    backend: str
    global_width: int
    slots: int
    unique_lemmas: int
    reference_gates: int
    candidate_gates: int

    @property
    def equivalent(self) -> bool:
        # This record is only constructed after every mandatory obligation passes.
        return True


def _unfold(
    width: int, steps: Sequence[Common | Slot], max_gates: int
) -> tuple[tuple[Gate, ...], tuple[Gate, ...], tuple[Slot, ...]]:
    left: list[Gate] = []
    right: list[Gate] = []
    slots: list[Slot] = []
    for index, item in enumerate(steps):
        if type(item) is Common:
            Circuit(width, list(item.gates)).validate()
            a = b = item.gates
        elif type(item) is Slot:
            if any(w >= width for w in item.wires):
                raise TranscriptMismatch(f"step {index}: local map outside global width")
            a = tuple(Gate(g.name, tuple(item.wires[q] for q in g.qubits))
                      for g in item.reference.gates)
            b = tuple(Gate(g.name, tuple(item.wires[q] for q in g.qubits))
                      for g in item.candidate.gates)
            slots.append(item)
        else:
            raise UnsupportedOperation(f"step {index}: only Common or Slot accepted")
        if len(left) + len(a) > max_gates or len(right) + len(b) > max_gates:
            raise ResourceLimitExceeded("transcript gates", max_gates,
                                        max(len(left) + len(a), len(right) + len(b)))
        left.extend(a)
        right.extend(b)
    return tuple(left), tuple(right), tuple(slots)


def _budget_left(budget: Budget | None, guard: Guard) -> Budget | None:
    """Keep the shared absolute deadline for same-process local obligations."""
    guard.check_time()
    return guard.inherited_budget()


def _restores(program: Program, wires: tuple[int, ...], *, backend: str,
              budget: Budget | None, guard: Guard) -> bool:
    if not wires:
        return True
    # A separate exact symbolic check, not equality of the two dirty outputs.
    algebra = make_algebra(backend, program.width, _budget_left(budget, guard))
    outputs = simulate(program.circuit(), algebra)
    guard.check_time()
    restored = all(algebra.equal(outputs[q], algebra.variable(q)) for q in wires)
    guard.check_time()
    return restored


@session_scoped
def verify_transcript(
    reference: Circuit,
    candidate: Circuit,
    steps: Sequence[Common | Slot],
    *,
    reference_sha256: str,
    candidate_sha256: str,
    backend: str = "sparse",
    budget: Budget | None = None,
    max_expanded_gates: int = 200_000,
) -> TranscriptProof:
    """Prove complete global classical equality via full-stream local lemmas.

    All local input bits are free, including dirty scratch/accumulators.
    Source fingerprints must be pinned independently by the caller. No saved
    proof JSON is accepted as authority and no fallback backend is selected.
    """
    guard = Guard(budget)
    if type(max_expanded_gates) is not int or max_expanded_gates < 1:
        raise ValueError("positive max_expanded_gates required")
    if not isinstance(steps, (tuple, list)) or not steps:
        raise TranscriptMismatch("nonempty ordered transcript required")
    if type(reference_sha256) is not str or type(candidate_sha256) is not str or any(
        len(s) != 64 or any(c not in "0123456789abcdef" for c in s)
        for s in (reference_sha256, candidate_sha256)
    ):
        raise ValueError("complete lowercase SHA-256 pins required")
    original = Program.freeze(reference)
    proposed = Program.freeze(candidate)
    if original.width != proposed.width:
        raise TranscriptMismatch("global widths differ")
    if digest(original) != reference_sha256 or digest(proposed) != candidate_sha256:
        raise TranscriptMismatch("globally supplied trusted source hash mismatch")
    expanded_a, expanded_b, slots = _unfold(
        original.width, steps, max_expanded_gates
    )
    if expanded_a != original.gates or expanded_b != proposed.gates:
        raise TranscriptMismatch("ordered transcript does not cover both complete streams")
    guard.check_time()

    # Keys contain *complete immutable local streams*, preserved-wire contract,
    # chosen engine and budgets. Cache lives only inside this verification call.
    checked: set[tuple[Program, Program, tuple[int, ...], str, Budget | None]] = set()
    for index, slot in enumerate(slots):
        guard.check_time()
        key = (slot.reference, slot.candidate, slot.preserved, backend, budget)
        if key in checked:
            continue
        result = check_equivalence(
            slot.reference.circuit(), slot.candidate.circuit(), backend=backend,
            budget=_budget_left(budget, guard),
        )
        guard.check_time()
        if not result.equivalent:
            raise UnprovedSubstitution(
                index, f"local output {result.output} differs", result.witness
            )
        for side, local in (("reference", slot.reference), ("candidate", slot.candidate)):
            if not _restores(local, slot.preserved, backend=backend,
                             budget=budget, guard=guard):
                raise UnprovedSubstitution(index, f"{side} does not restore its preserved wires")
        checked.add(key)
    guard.check_time()
    return TranscriptProof(
        reference_sha256, candidate_sha256, backend, original.width, len(slots),
        len(checked), len(original.gates), len(proposed.gates)
    )
