"""Hard subprocess limits, distinct from cooperative engine budgets.

Workers are spawned: no native manager or node identifier is shared with the
caller. The parent's wall deadline includes interpreter startup and cleanup.
"""
from __future__ import annotations

import json
import math
import multiprocessing
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any

from symq.resources import ResourceLimitExceeded, VerificationSession, current_session

_SPAWN_LOCK = RLock()
_PACKAGE_ROOT = str(Path(__file__).resolve().parents[2])
MAX_RESULT_BYTES = 1024 * 1024
MAX_RESULT_DEPTH = 64
MAX_RESULT_ITEMS = 100_000
CLEANUP_GRACE_SECONDS = 0.2


def _check_wire(value: Any, *, depth: int = 0, count: list[int] | None = None) -> None:
    """Closed result language: no constructors, callbacks or pickle reducers."""
    count = [0] if count is None else count
    count[0] += 1
    if depth > MAX_RESULT_DEPTH or count[0] > MAX_RESULT_ITEMS:
        raise ValueError("worker result exceeds structural limit")
    kind = type(value)
    if value is None or kind in (bool, str):
        return
    if kind is int and value.bit_length() <= 4096:
        return
    if kind is float and math.isfinite(value):
        return
    if kind in (list, tuple, dict):
        if kind is dict and any(type(key) is not str for key in value):
            raise ValueError("worker result dictionary keys must be strings")
        for child in value.values() if kind is dict else value:
            _check_wire(child, depth=depth + 1, count=count)
        return
    raise ValueError("worker result must contain only bounded JSON primitives")


def _send_wire(connection: Any, payload: list) -> None:
    _check_wire(payload)
    encoded = json.dumps(payload, allow_nan=False, ensure_ascii=True,
                         separators=(",", ":")).encode("ascii")
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("worker result exceeds byte limit")
    connection.send_bytes(encoded)


def _receive_wire(connection: Any, box: list, ready: Event) -> None:
    # Even a truncated frame or a slow JSON parser cannot hold up the caller.
    # This daemon only creates bounded builtins and never reconstructs objects.
    try:
        encoded = connection.recv_bytes(MAX_RESULT_BYTES)
        payload = json.loads(encoded)
        _check_wire(payload)
        if (type(payload) is not list or len(payload) != 5
                or payload[0] not in ("completed", "inconclusive", "unsupported", "error")
                or type(payload[1]) is not str
                or (payload[3] is not None and (type(payload[3]) not in (int, float)
                                               or payload[3] < 0))
                or (payload[4] is not None and (type(payload[4]) is not int
                                               or payload[4] < 0))):
            raise ValueError("invalid worker result envelope")
        box.append(payload)
    except (EOFError, OSError, ValueError, TypeError, RecursionError, MemoryError):
        pass
    finally:
        ready.set()


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
                _send_wire(connection, ["unsupported", "hard memory/CPU limits require resource",
                                        None, None, None])
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
        _send_wire(connection, [status, reason, value, cpu, rss])
    except (ValueError, TypeError, RecursionError):
        _send_wire(connection, ["inconclusive", "worker result rejected by typed IPC limits",
                                None, cpu, rss])
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

    ``function`` and arguments are trusted and must be spawn-pickleable. Results
    are bounded JSON primitives, encoded in the worker; arbitrary returned
    objects are refused without invoking their pickle reconstruction. Reception
    and decoding run behind the parent's deadline. OS cleanup has a separate
    grace of at most ``CLEANUP_GRACE_SECONDS`` (subject to OS scheduling).
    This is resource isolation, not a sandbox for hostile worker code: workers
    retain the caller's filesystem/network permissions. The return status
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
    box: list = []
    ready = Event()
    reason = "worker exited without a complete result"
    try:
        # A caller may have inspected another checkout on sys.path. Spawn must
        # import the same installed implementation as this parent, rather than
        # whichever historical package currently happens to precede it.
        if not _SPAWN_LOCK.acquire(timeout=max(0.0, deadline - time.perf_counter())):
            return IsolatedResult("inconclusive", "parent spawn deadline exhausted",
                                  wall_seconds=time.perf_counter() - started)
        try:
            previous_path = list(sys.path)
            try:
                sys.path[:] = [_PACKAGE_ROOT] + [p for p in previous_path if p != _PACKAGE_ROOT]
                process.start()
            finally:
                sys.path[:] = previous_path
        finally:
            _SPAWN_LOCK.release()
        sender.close()
        reader = Thread(target=_receive_wire, args=(receiver, box, ready), daemon=True)
        reader.start()
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                reason = "hard whole-call wall deadline exhausted"
                break
            if ready.wait(min(remaining, 0.02)):
                payload = box[0] if box else None
                break
        if payload is not None:
            process.join(max(0.0, deadline - time.perf_counter()))
    finally:
        if process.pid is not None and process.is_alive():
            process.terminate()
            process.join(CLEANUP_GRACE_SECONDS / 2)
            if process.is_alive():
                process.kill()
                process.join(CLEANUP_GRACE_SECONDS / 2)
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
