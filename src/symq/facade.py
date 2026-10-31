"""One entry point for every theorem SymQ can establish.

``verify(left, right, theorem=..., engine=...)`` routes the request to the engine that owns the
theorem; it never chooses a theorem or an engine for the caller and never falls back to a weaker
statement:

* ``classical_full``, ``classical_contract``, ``sign_phase_exact``, ``sign_phase_up_to_global``
  go to :func:`symq.verification.verify_explicit` and return a ``VerificationRecord``;
* ``full_channel``, ``reduced_channel``, ``instrument`` go to :func:`symq.experimental.verify`
  with a ``VerificationContract`` and return its ``VerificationResult``.

Both result types satisfy the :class:`Verdict` protocol.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .resources import Budget

__all__ = ["BRANCH_THEOREMS", "CHANNEL_THEOREMS", "THEOREMS", "Verdict", "verify"]

BRANCH_THEOREMS = frozenset({
    "classical_full", "classical_contract", "sign_phase_exact", "sign_phase_up_to_global",
})
"""Theorems about classical circuits and strict sign/HMR branches."""

CHANNEL_THEOREMS = frozenset({"full_channel", "reduced_channel", "instrument"})
"""Experimental coherent-channel theorems (see ``docs/guide/experimental.md``)."""

THEOREMS = BRANCH_THEOREMS | CHANNEL_THEOREMS


@runtime_checkable
class Verdict(Protocol):
    """What every verification result exposes, whatever engine produced it."""

    @property
    def outcome(self) -> str:
        """``equivalent``, ``different``, ``inconclusive``, ``unsupported`` or
        ``precondition_failed``."""

    @property
    def theorem(self) -> str: ...

    @property
    def reason(self) -> str: ...

    @property
    def witness(self) -> Any: ...

    @property
    def witness_kind(self) -> str | None: ...

    @property
    def equivalent(self) -> bool: ...

    @property
    def certified(self) -> bool: ...


def verify(left: Any, right: Any, *, theorem: str, engine: str, contract: Any = None,
           budget: Budget | None = None) -> Verdict:
    """Establish exactly ``theorem`` with ``engine``.

    ``contract`` is a ``symq.sat.Contract`` for ``classical_contract`` and an optional
    ``symq.experimental.VerificationContract`` for the channel theorems (its theorem and backend
    must then match the arguments). Invalid combinations raise; exhausted resources give an
    ``inconclusive`` verdict.
    """
    if type(theorem) is not str or theorem not in THEOREMS:
        raise ValueError(f"unknown theorem {theorem!r}; choose from {sorted(THEOREMS)}")
    if theorem in CHANNEL_THEOREMS:
        from .experimental import verify as verify_channel
        from .experimental.contracts import VerificationContract

        if contract is None:
            contract = VerificationContract(theorem=theorem, backend=engine)
        elif not isinstance(contract, VerificationContract):
            raise TypeError(f"{theorem} takes a VerificationContract")
        elif (contract.theorem, contract.backend) != (theorem, engine):
            raise ValueError("the VerificationContract names a different theorem or backend")
        return verify_channel(left, right, contract, budget=budget)
    from .verification import verify_explicit

    return verify_explicit(left, right, theorem=theorem, engine=engine, contract=contract,
                           budget=budget)
