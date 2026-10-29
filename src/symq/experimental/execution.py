"""Hard subprocess limits, distinct from cooperative engine budgets.

Workers are spawned: no native manager or node identifier is shared with the
caller. The parent's wall deadline includes interpreter startup and cleanup.
"""
from __future__ import annotations

import math
import multiprocessing
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from symq.resources import ResourceLimitExceeded, VerificationSession, current_session

_SPAWN_LOCK = RLock()
_PACKAGE_ROOT = str(Path(__file__).resolve().parents[2])


@dataclass(frozen=True)
class HardLimits:
    wall_seconds: float = 60.0
    memory_bytes: int | None = 2 * 1024**3
    cpu_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("wall_seconds", "cpu_seconds"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) or value <= 0
            ):
                raise ValueError(f"{name} must be finite and positive")
        if self.wall_seconds is None:
            raise ValueError("a hard wall deadline is required")
        if self.memory_bytes is not None and (
            type(self.memory_bytes) is not int or self.memory_bytes < 1
        ):
            raise ValueError("memory_bytes must be a positive integer or None")


@dataclass(frozen=True)
class IsolatedResult:
    status: str  # completed | inconclusive | unsupported | error
    reason: str
    value: Any = None
    wall_seconds: float = 0.0
    cpu_seconds: float | None = None
    peak_rss_bytes: int | None = None
    exitcode: int | None = None


def verification_job(reference, candidate, contract, budget, profiled=False):
    """Importable worker entry point, including when the CLI runs with ``-m``.

    Spawn cannot resolve a callable defined in an executable __main__ module.
    Keep its implementation in the installed package instead.
    """
    if profiled:
        from .profiling import profile
        return profile(reference, candidate, contract, budget=budget).to_dict()
    from .api import verify
    return {"result": verify(reference, candidate, contract, budget=budget).to_dict()}


def _worker(connection: Any, function: Callable[..., Any], args: tuple,
            kwargs: dict, limits: HardLimits) -> None:
    try:
        if limits.memory_bytes is not None or limits.cpu_seconds is not None:
            try:
                import resource
            except ImportError:
                connection.send(("unsupported", "hard memory/CPU limits require resource", None,
                                 None, None))
                return
            if limits.memory_bytes is not None:
                resource.setrlimit(resource.RLIMIT_AS,
                                   (limits.memory_bytes, limits.memory_bytes))
            if limits.cpu_seconds is not None:
                seconds = math.ceil(limits.cpu_seconds)
                resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))
        value = function(*args, **kwargs)
        status, reason = "completed", "worker completed within hard limits"
    except (MemoryError, ResourceLimitExceeded) as error:
        status, reason, value = "inconclusive", str(error) or "worker memory limit exceeded", None
    except Exception as error:  # noqa: BLE001 -- serialize failures at the process boundary
        status, reason, value = "error", f"{type(error).__name__}: {error}", None
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        cpu = usage.ru_utime + usage.ru_stime
        rss = int(usage.ru_maxrss) * (1 if sys.platform == "darwin" else 1024)
    except ImportError:
        cpu, rss = None, None
    try:
        connection.send((status, reason, value, cpu, rss))
    except (MemoryError, OSError):
        # The parent treats a missing/truncated response as inconclusive.
        pass
    finally:
        connection.close()


def run_isolated(function: Callable[..., Any], *args: Any,
                 limits: HardLimits | None = None,
                 session: VerificationSession | None = None,
                 kwargs: dict[str, Any] | None = None) -> IsolatedResult:
    """Run an importable callable in a fresh, bounded process.

    ``function`` and arguments must be spawn-pickleable. The return status
    describes execution; a completed verification may itself be inconclusive.
    Abrupt worker failure is never interpreted as a semantic difference.
    """
    limits = limits or HardLimits()
    session = session or current_session()
    started = time.perf_counter()
    deadline = started + limits.wall_seconds
    if session is not None and session.deadline is not None:
        deadline = min(deadline, session.deadline)
    if started >= deadline:
        return IsolatedResult("inconclusive", "parent verification deadline exhausted")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(sender, function, args, kwargs or {}, limits))
    payload = None
    reason = "worker exited without a complete result"
    try:
        # A caller may have inspected another checkout on sys.path. Spawn must
        # import the same installed implementation as this parent, rather than
        # whichever historical package currently happens to precede it.
        with _SPAWN_LOCK:
            previous_path = list(sys.path)
            try:
                sys.path[:] = [_PACKAGE_ROOT] + [p for p in previous_path if p != _PACKAGE_ROOT]
                process.start()
            finally:
                sys.path[:] = previous_path
        sender.close()
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                reason = "hard whole-call wall deadline exhausted"
                break
            if receiver.poll(min(remaining, 0.02)):
                try:
                    payload = receiver.recv()
                except (EOFError, OSError):
                    pass
                break
            if not process.is_alive():
                break
        if payload is not None:
            process.join(max(0.0, deadline - time.perf_counter()))
    finally:
        if process.pid is not None and process.is_alive():
            process.terminate()
            process.join(0.2)
            if process.is_alive():
                process.kill()
                process.join(0.2)
        receiver.close()
        sender.close()
    elapsed = time.perf_counter() - started
    if time.perf_counter() >= deadline:
        return IsolatedResult("inconclusive", "hard whole-call wall deadline exhausted",
                              wall_seconds=elapsed, exitcode=process.exitcode)
    if payload is None:
        return IsolatedResult("inconclusive", reason, wall_seconds=elapsed,
                              exitcode=process.exitcode)
    status, reason, value, cpu, rss = payload
    if process.exitcode != 0:
        status, reason, value = "inconclusive", "worker failed during cleanup", None
    return IsolatedResult(status, reason, value, elapsed, cpu, rss, process.exitcode)
