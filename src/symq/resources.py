"""Explicit resource budgets: computations stop with an error, never with an approximation."""
from __future__ import annotations

import time
from dataclasses import dataclass


class ResourceLimitExceeded(RuntimeError):
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


@dataclass(frozen=True)
class Budget:
    """Limits for one symbolic computation; ``None`` means unlimited.

    ``max_terms`` bounds explicit monomial sets (including intermediate products and
    conversions to explicit ANF), ``max_nodes`` bounds the ZDD unique table, and
    ``max_seconds`` bounds wall-clock time.
    """

    max_terms: int | None = None
    max_nodes: int | None = None
    max_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("max_terms", "max_nodes"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 1):
                raise ValueError(f"{name} must be a positive integer or None")
        if self.max_seconds is not None and not self.max_seconds > 0:
            raise ValueError("max_seconds must be positive or None")

    def start(self) -> Guard:
        return Guard(self)


class Guard:
    """A running budget; the clock starts at construction."""

    def __init__(self, budget: Budget | None = None) -> None:
        self.budget = budget if budget is not None else Budget()
        self._started = time.perf_counter()
        seconds = self.budget.max_seconds
        self._deadline = None if seconds is None else self._started + seconds

    def check_time(self) -> None:
        if self._deadline is not None:
            now = time.perf_counter()
            if now > self._deadline:
                raise ResourceLimitExceeded(
                    "seconds", self.budget.max_seconds, round(now - self._started, 6)
                )

    @property
    def started(self) -> float:
        """``time.perf_counter()`` value at which the budget started."""
        return self._started

    @property
    def deadline(self) -> float | None:
        """Absolute ``perf_counter`` deadline, or ``None`` when time is unbounded."""
        return self._deadline

    def check_terms(self, count: int) -> None:
        limit = self.budget.max_terms
        if limit is not None and count > limit:
            raise ResourceLimitExceeded("terms", limit, count)

    def check_nodes(self, count: int) -> None:
        limit = self.budget.max_nodes
        if limit is not None and count > limit:
            raise ResourceLimitExceeded("nodes", limit, count)
