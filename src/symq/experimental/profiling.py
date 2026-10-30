"""Exclusive stage timings around the public verifier, with inspectable evidence.

Profiling adds instrumentation overhead.  Its stage times describe that
instrumented call; comparative benchmarks must time uninstrumented calls in
fresh workers.  No second channel algorithm is implemented here.
"""
from __future__ import annotations

import html
import json
import platform
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import Path
from typing import Any

from symq.resources import Budget, ResourceLimitExceeded, VerificationSession

_ACTIVE: ContextVar[ExclusiveTimer | None] = ContextVar("symq_exclusive_profile", default=None)


class ExclusiveTimer:
    """Attribute nested time once, subtracting every child's inclusive duration."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self.clock = clock
        self.seconds: dict[str, float] = {}
        self.counters: dict[str, int | float] = {}
        self._stack: list[list[Any]] = []

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        if type(name) is not str or not name:
            raise ValueError("stage name must be a nonempty string")
        frame: list[Any] = [name, self.clock(), 0.0]
        self._stack.append(frame)
        try:
            yield
        finally:
            elapsed = max(0.0, self.clock() - frame[1])
            if not self._stack or self._stack.pop() is not frame:
                raise RuntimeError("profile stages must close in stack order")
            self.seconds[name] = self.seconds.get(name, 0.0) + max(0.0, elapsed - frame[2])
            if self._stack:
                self._stack[-1][2] += elapsed

    def finish(self, total: float) -> None:
        if self._stack:
            raise RuntimeError("profile still has open stages")
        measured = sum(self.seconds.values())
        if measured > total + max(1e-9, total * 1e-9):
            raise RuntimeError("exclusive stage times exceed whole-call elapsed time")
        self.seconds["orchestration"] = self.seconds.get("orchestration", 0.0) + max(
            0.0, total - measured)


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Optional hook used by the actual verifier; a no-op outside profiling."""
    timer = _ACTIVE.get()
    if timer is None:
        yield
    else:
        with timer.stage(name):
            yield


def count(name: str, amount: float = 1) -> None:
    timer = _ACTIVE.get()
    if timer is not None:
        timer.counters[name] = timer.counters.get(name, 0) + amount


def observe(name: str, value: float | None) -> None:
    timer = _ACTIVE.get()
    if timer is not None and value is not None:
        timer.counters[name] = value


@dataclass(frozen=True)
class ProfileReport:
    result: Any
    stage_seconds: tuple[tuple[str, float], ...]
    counters: tuple[tuple[str, int | float], ...]
    total_seconds: float
    cpu_seconds: float
    environment: tuple[tuple[str, str], ...]
    schema_version: int = 1

    def to_dict(self) -> dict:
        from .serialization import result_to_dict
        return {"schema_version": self.schema_version,
                "result": result_to_dict(self.result),
                "timing": {"whole_call_wall_seconds": self.total_seconds,
                           "whole_call_cpu_seconds": self.cpu_seconds,
                           "exclusive_stage_seconds": dict(self.stage_seconds),
                           "sum_stage_seconds": sum(value for _, value in self.stage_seconds)},
                "counters": dict(self.counters), "environment": dict(self.environment),
                "measurement_scope": "one instrumented public verify call; stage hooks add overhead",
                "proof_scope": "exact computation and checked counterexamples; no independent UNSAT certificate"}

    def write_json(self, path: str | Path) -> None:
        from .serialization import save_json
        save_json(self.to_dict(), path)

    def write_html(self, path: str | Path) -> None:
        """Write a self-contained report; all source/contract hashes remain inspectable."""
        payload = self.to_dict()
        rows = "".join(
            f"<tr><td>{html.escape(name)}</td><td>{seconds:.9f}</td>"
            f"<td>{(100 * seconds / self.total_seconds if self.total_seconds else 0):.2f}%</td></tr>"
            for name, seconds in self.stage_seconds)
        evidence = html.escape(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False))
        outcome = html.escape(self.result.outcome)
        reason = html.escape(self.result.reason)
        document = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SymQ verification profile</title><style>
body{{font:16px system-ui,sans-serif;max-width:1050px;margin:3rem auto;padding:0 1rem;color:#16232c}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:.6rem;border-bottom:1px solid #ccd7df;text-align:left}}
pre{{overflow:auto;background:#f1f5f8;padding:1rem;font-size:13px}}small{{color:#455a68}}
</style><h1>SymQ verification profile</h1><p><strong>{outcome}</strong> — {reason}</p>
<p>Whole call: {self.total_seconds:.6f} wall seconds; {self.cpu_seconds:.6f} CPU seconds.
Stage durations are exclusive and reconcile to the whole call, including orchestration.</p>
<table><thead><tr><th>Stage</th><th>Seconds</th><th>Share</th></tr></thead><tbody>{rows}</tbody></table>
<p><small>This instrumented call includes profiling overhead. It establishes the recorded theorem
on its declared domain and output contract. It is not a comparative speed benchmark or an
independently checked UNSAT certificate. A missing stage means it was not measured separately.</small></p>
<details open><summary>Result, source fingerprints and measurement evidence</summary><pre>{evidence}</pre></details>
</html>"""
        Path(path).write_text(document, encoding="utf-8")


def profile(left: Any, right: Any, contract: Any = None, *, theorem: str | None = None,
            backend: str | None = None, budget: Budget | None = None,
            **contract_kwargs: Any) -> ProfileReport:
    """Profile the same public ``verify`` call, with a shared whole-call budget."""
    from .api import verify
    timer = ExclusiveTimer()
    token = _ACTIVE.set(timer)
    started, cpu_started = time.perf_counter(), time.process_time()
    result = None
    try:
        try:
            with VerificationSession(budget) as session:
                with timer.stage("orchestration"):
                    result = verify(left, right, contract, theorem=theorem, backend=backend,
                                    budget=budget, **contract_kwargs)
                session.check_time()
        except ResourceLimitExceeded as error:
            if result is None:
                # Entry itself can time out. Let the public API validate its
                # contract and produce the usual nondecisive record, with no
                # renewed time available for semantic work.
                result = verify(left, right, contract, theorem=theorem, backend=backend,
                                budget=Budget(max_seconds=1e-12), **contract_kwargs)
            result = replace(result, outcome="inconclusive", reason=str(error),
                             witness=None, witness_kind=None, witness_checked=False)
    finally:
        _ACTIVE.reset(token)
    elapsed, cpu = time.perf_counter() - started, time.process_time() - cpu_started
    timer.finish(elapsed)
    for name, value in result.statistics:
        timer.counters.setdefault(name, value)
    try:
        version = metadata.version("symq")
    except metadata.PackageNotFoundError:
        version = "not installed"
    return ProfileReport(result, tuple(sorted(timer.seconds.items())),
                         tuple(sorted(timer.counters.items())), elapsed, cpu,
                         (("python", platform.python_version()), ("platform", platform.platform()),
                          ("symq", version)))
