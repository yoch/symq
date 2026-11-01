"""Exception hierarchy shared by every SymQ engine.

Every SymQ-specific error derives from :class:`SymqError`, so callers can catch the library's
failures in one clause. Each class also keeps the built-in base it had before this module existed
(``ValueError`` for invalid input, ``RuntimeError`` for runtime conditions), so existing
``except ValueError`` / ``except RuntimeError`` handlers keep working.

None of these errors is a verdict. A ``ResourceLimitExceeded`` or ``SatUnavailable`` means *no
answer*, never "different"; an ``InternalInconsistency`` means a bug was caught before a wrong
answer could be returned.
"""
from __future__ import annotations

__all__ = [
    "InternalInconsistency",
    "QasmSyntaxError",
    "ResourceLimitExceeded",
    "SatUnavailable",
    "SymqError",
    "UnsupportedOperation",
]


class SymqError(Exception):
    """Base class of every SymQ-specific exception."""


class ResourceLimitExceeded(SymqError, RuntimeError):
    """A budgeted computation was abandoned; no partial or approximate result exists."""

    def __init__(
        self, resource: str, limit: float, observed: float, hint: str | None = None
    ) -> None:
        message = f"{resource} limit exceeded: observed {observed}, limit {limit}"
        if hint:
            message += f" ({hint})"
        super().__init__(message)
        self.resource = resource
        self.limit = limit
        self.observed = observed
        self.hint = hint


class InternalInconsistency(SymqError, RuntimeError):
    """An engine produced a verdict that failed independent concrete validation."""


class UnsupportedOperation(SymqError, ValueError):
    """Instruction outside the explicitly supported subset; nothing is approximated."""


class QasmSyntaxError(SymqError, ValueError):
    """Malformed input inside the accepted OpenQASM subset."""


class SatUnavailable(SymqError, RuntimeError):
    """No SAT solver is installed; the caller must fall back or fail, never guess."""
