"""Solving under a wall-clock deadline, shared by the miter and the composition engine.

``pysat`` exposes ``interrupt()`` rather than a deadline, so the only honest way to enforce seconds
is to call it from another thread. A conflict ceiling counts conflicts, not seconds; it only stops
a solver that would otherwise never return.
"""
from __future__ import annotations

import threading
import time

CONFLICT_CEILING = 50_000_000
"""Conflicts after which a deadline-bound solve gives up (reported as no answer)."""


class _Watchdog:
    """Interrupt a solver that outlives its wall-clock budget.

    The fired flag is explicit so the caller can tell a real timeout from a solver that answered
    ``None`` for another reason.
    """

    def __init__(self, seconds: float, interrupt) -> None:
        self._seconds = float(seconds)
        self._interrupt = interrupt
        self._timer: threading.Timer | None = None
        self.fired = False

    def _fire(self) -> None:
        self.fired = True
        self._interrupt()

    def start(self) -> None:
        self._timer = threading.Timer(self._seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def stop(self) -> bool:
        if self._timer is not None:
            self._timer.cancel()
            self._timer.join(timeout=1.0)
        return self.fired


def solve_with_deadline(solver, deadline: float | None) -> tuple[bool | None, bool]:
    """Run ``solver`` until ``deadline`` (a ``time.perf_counter`` value); ``None`` means no limit.

    Returns ``(answer, timed_out)``. ``timed_out`` is true when the deadline had passed before
    solving, the watchdog fired, or the deadline passed while solving: an answer arriving late is
    discarded, because certifying it would report work the budget did not cover. ``answer`` is
    ``None`` when the solver gave no answer (timeout or conflict ceiling).
    """
    if deadline is None:
        return solver.solve(), False
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        return None, True
    watchdog = _Watchdog(remaining, solver.interrupt)
    watchdog.start()
    try:
        if hasattr(solver, "conf_budget"):
            solver.conf_budget(CONFLICT_CEILING)
        answer = solver.solve_limited(expect_interrupt=True)
    finally:
        fired = watchdog.stop()
    if fired or time.perf_counter() >= deadline:
        return None, True
    return answer, False
