"""Explicit resource budgets: computations stop with an error, never with an approximation."""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from inspect import signature
from typing import Any, TypeVar

_ACTIVE_SESSION: ContextVar[VerificationSession | None] = ContextVar(
    "symq_verification_session", default=None
)


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
    ``max_seconds`` is a relative duration when a guard starts. An inherited
    ``absolute_deadline`` carries the original same-process clock deadline;
    it must be converted to a relative duration for detached workers.
    """

    max_terms: int | None = None
    max_nodes: int | None = None
    max_seconds: float | None = None
    absolute_deadline: float | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        for name in ("max_terms", "max_nodes"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"{name} must be a positive integer or None")
        if self.max_seconds is not None and (
            isinstance(self.max_seconds, bool)
            or not isinstance(self.max_seconds, (int, float))
            or not math.isfinite(self.max_seconds)
            or self.max_seconds <= 0
        ):
            raise ValueError("max_seconds must be positive or None")
        if self.absolute_deadline is not None and (
            isinstance(self.absolute_deadline, bool)
            or not isinstance(self.absolute_deadline, (int, float))
            or not math.isfinite(self.absolute_deadline)
        ):
            raise ValueError("absolute_deadline must be finite or None")

    def start(self) -> Guard:
        return Guard(self)


class Guard:
    """A running budget; the clock starts at construction."""

    def __init__(self, budget: Budget | None = None) -> None:
        if budget is not None and not isinstance(budget, Budget):
            raise TypeError("budget must be Budget or None")
        active = _ACTIVE_SESSION.get()
        self.budget = budget if budget is not None else Budget()
        now = time.perf_counter()
        self._started = now if active is None else active.started
        seconds = self.budget.max_seconds
        deadline = None if seconds is None else now + seconds
        deadline = _least(deadline, self.budget.absolute_deadline)
        if active is not None:
            self.budget = intersect_budgets(active.budget, self.budget)
            deadline = _least(deadline, active.deadline)
        self._deadline = deadline

    def check_time(self) -> None:
        if self._deadline is not None:
            now = time.perf_counter()
            if now >= self._deadline:
                raise ResourceLimitExceeded(
                    "seconds", self._deadline - self._started, round(now - self._started, 6)
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

    def inherited_budget(self) -> Budget:
        """Same-process view: preserve the absolute deadline, never re-anchor it.

        An absolute ``perf_counter`` deadline must not be sent to a fresh
        interpreter. Use ``VerificationSession.subprocess_budget`` there.
        """
        self.check_time()
        return Budget(self.budget.max_terms, self.budget.max_nodes,
                      absolute_deadline=self.deadline)


def _least(a: Any, b: Any) -> Any:
    return b if a is None else a if b is None else min(a, b)


def intersect_budgets(left: Budget, right: Budget) -> Budget:
    """Intersect limits without restarting a clock or weakening an outer limit."""
    return Budget(
        _least(left.max_terms, right.max_terms),
        _least(left.max_nodes, right.max_nodes),
        _least(left.max_seconds, right.max_seconds),
        absolute_deadline=_least(left.absolute_deadline, right.absolute_deadline),
    )


class VerificationSession(Guard):
    """Whole-call resources shared by nested guards, engines and witness replay.

    The context is local to the execution context, never a module-global clock.
    A nested session may tighten limits but cannot restart the outer deadline.
    ``reserve`` tracks simultaneously retained resources; cumulative work is a
    separate counter. Subprocesses receive a remaining duration explicitly.
    """

    def __init__(self, budget: Budget | None = None) -> None:
        super().__init__(budget)
        parent = _ACTIVE_SESSION.get()
        self._allocations: dict[object, tuple[int, int]] = (
            {} if parent is None else parent._allocations
        )
        self.counters: dict[str, int] = {} if parent is None else parent.counters
        self.peaks: dict[str, int] = {} if parent is None else parent.peaks
        self._token = None

    @property
    def guard(self) -> Guard:
        return self

    def __enter__(self):
        if self._token is not None:
            raise RuntimeError("a VerificationSession cannot be entered twice")
        self.check_time()
        self._token = _ACTIVE_SESSION.set(self)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            if exc_type is None:
                self.check_time()
        finally:
            if self._token is not None:
                _ACTIVE_SESSION.reset(self._token)
                self._token = None

    def remaining_seconds(self) -> float | None:
        if self.deadline is None:
            return None
        now = time.perf_counter()
        if now >= self.deadline:
            raise ResourceLimitExceeded("seconds", self.deadline - self.started,
                                        round(now - self.started, 6))
        return self.deadline - now

    def remaining_budget(self) -> Budget:
        """Same-process remaining resources, carrying an absolute deadline."""
        available = self.available_nodes
        if available == 0:
            raise ResourceLimitExceeded("nodes", self.budget.max_nodes, self.budget.max_nodes + 1)
        self.check_time()
        return Budget(self.budget.max_terms, available, absolute_deadline=self.deadline)

    def subprocess_budget(self) -> Budget:
        """Detached worker duration; the parent still enforces its own deadline."""
        remaining = self.remaining_budget()
        return Budget(remaining.max_terms, remaining.max_nodes, self.remaining_seconds())

    @property
    def available_nodes(self) -> int | None:
        if self.budget.max_nodes is None:
            return None
        return max(0, self.budget.max_nodes - sum(n for n, _ in self._allocations.values()))

    def count(self, name: str, amount: int = 1) -> None:
        if type(amount) is not int or amount < 0:
            raise ValueError("work increments must be nonnegative integers")
        self.counters[name] = self.counters.get(name, 0) + amount

    def reserve(self, owner: object, *, nodes: int = 0, bytes_: int = 0) -> None:
        if any(type(v) is not int or v < 0 for v in (nodes, bytes_)):
            raise ValueError("resource reservations must be nonnegative integers")
        old = self._allocations.get(owner)
        self._allocations[owner] = (nodes, bytes_)
        resident = sum(n for n, _ in self._allocations.values())
        try:
            self.check_nodes(resident)
            self.check_time()
        except BaseException:
            if old is None:
                self._allocations.pop(owner, None)
            else:
                self._allocations[owner] = old
            raise
        self.peaks["resident_nodes"] = max(self.peaks.get("resident_nodes", 0), resident)
        self.peaks["retained_bytes"] = max(
            self.peaks.get("retained_bytes", 0),
            sum(b for _, b in self._allocations.values()),
        )

    def release(self, owner: object) -> None:
        self._allocations.pop(owner, None)

    def reservation(self, owner: object) -> tuple[int, int] | None:
        """Inspect an owner's reservation before an atomic manager transfer."""
        return self._allocations.get(owner)

    def restore_reservation(self, owner: object, previous: tuple[int, int] | None) -> None:
        """Release a temporary reservation even while unwinding a timeout.

        Decreasing retained resources cannot exceed a budget. Increases still
        use normal admission checks, so this is not an unchecked allocation API.
        """
        if previous is None:
            self.release(owner)
            return
        if (type(previous) is not tuple or len(previous) != 2
                or any(type(v) is not int or v < 0 for v in previous)):
            raise ValueError("a previous nonnegative reservation is required")
        current = self._allocations.get(owner, (0, 0))
        if previous[0] <= current[0] and previous[1] <= current[1]:
            self._allocations[owner] = previous
        else:
            self.reserve(owner, nodes=previous[0], bytes_=previous[1])


def current_session() -> VerificationSession | None:
    return _ACTIVE_SESSION.get()


_F = TypeVar("_F", bound=Callable[..., Any])


def session_scoped(function: _F) -> _F:
    """Give a legacy budgeted entry point a shared whole-call deadline."""
    parameters = tuple(signature(function).parameters)
    budget_index = parameters.index("budget") if "budget" in parameters else None

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        budget = kwargs.get("budget")
        if budget_index is not None and len(args) > budget_index:
            budget = args[budget_index]
        with VerificationSession(budget):
            return function(*args, **kwargs)

    return wrapped  # type: ignore[return-value]
