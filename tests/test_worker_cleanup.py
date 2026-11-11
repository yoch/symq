"""Deterministic POSIX reaping interleavings, using two real spawned workers."""
from __future__ import annotations

import os
import sys
import time
from threading import Event, Lock, Thread, current_thread
from types import SimpleNamespace

import pytest

from symq.experimental import execution

if sys.platform != "win32":
    from multiprocessing.popen_fork import Popen as _ForkPopen

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX waitpid race")
_WATCHDOG = 10


def _capture_deferred_threads(monkeypatch):
    deferred = []

    def thread(*args, **kwargs):
        result = Thread(*args, **kwargs)
        if getattr(kwargs.get("target"), "__name__", None) == "_deferred_signal":
            deferred.append(result)
        return result

    monkeypatch.setattr(execution, "Thread", thread)
    return deferred


@pytest.mark.timing
@pytest.mark.parametrize("expired", [False, True])
def test_concurrent_start_cannot_lose_another_workers_exit_status(monkeypatch, expired):
    """Pause a real reaper between waitpid and publishing the child's status.

    The competing thread reaches the reaper through Process.start/_cleanup,
    while the owner already has a valid worker result. Events force the race;
    no short wall limit or lucky process scheduling is needed to reproduce it.
    """
    reaped, publish, owner_join, enter_join, owner_acquiring = (Event() for _ in range(5))
    expire_clock = Event()
    target, results, errors = {}, {}, {}
    real_poll = _ForkPopen.poll
    real_wait = execution._ReapingPopen.wait
    real_perf_counter = time.perf_counter
    real_kill = os.kill
    unsafe_signals = []
    deferred = _capture_deferred_threads(monkeypatch)

    class ObservedLock:
        def __init__(self):
            self.lock = Lock()

        def acquire(self, blocking=True, timeout=-1):
            if (blocking and current_thread().name == "owner"
                    and reaped.is_set() and not publish.is_set()):
                owner_acquiring.set()
            return self.lock.acquire(blocking, timeout)

        def release(self):
            self.lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()

    def paused_poll(self, flag=os.WNOHANG):
        if self is target.get("popen") and current_thread().name == "competitor":
            assert flag == os.WNOHANG
            # The pipe sentinel can close just before waitpid reports exit.
            end = time.monotonic() + _WATCHDOG
            while True:
                pid, status = os.waitpid(self.pid, flag)
                if pid == self.pid:
                    break
                assert time.monotonic() < end, "real child did not exit"
                time.sleep(0.001)
            reaped.set()
            assert publish.wait(_WATCHDOG), "publication was not released"
            self.returncode = os.waitstatus_to_exitcode(status)
            return self.returncode
        return real_poll(self, flag)

    def gated_wait(self, timeout=None):
        if current_thread().name == "owner" and not target:
            target["popen"] = self
            assert execution._wait_handles([self.sentinel], _WATCHDOG)
            owner_join.set()
            assert enter_join.wait(_WATCHDOG), "owner join was not released"
        return real_wait(self, timeout)

    def perf_counter():
        offset = 20 if current_thread().name == "owner" and expire_clock.is_set() else 0
        return real_perf_counter() + offset

    def guarded_kill(pid, sig):
        if pid == target["popen"].pid:
            unsafe_signals.append(sig)
        else:
            real_kill(pid, sig)

    def run(name, values):
        try:
            results[name] = execution.run_isolated(
                sum, values, limits=execution.HardLimits(wall_seconds=10, memory_bytes=None)
            )
        except BaseException as error:  # noqa: BLE001 -- report thread assertions to the test
            errors[name] = error

    monkeypatch.setattr(execution, "Lock", ObservedLock)
    monkeypatch.setattr(_ForkPopen, "poll", paused_poll)
    monkeypatch.setattr(execution._ReapingPopen, "wait", gated_wait)
    monkeypatch.setattr(execution, "time", SimpleNamespace(
        perf_counter=perf_counter, monotonic=time.monotonic, sleep=time.sleep,
    ))
    owner = Thread(target=run, args=("owner", [1, 2]), name="owner")
    competitor = Thread(target=run, args=("competitor", [4, 5]), name="competitor")
    owner.start()
    try:
        assert owner_join.wait(_WATCHDOG), errors
        competitor.start()
        assert reaped.wait(_WATCHDOG), errors
        popen = target["popen"]
        assert popen.returncode is None
        # These callers must neither wait for the paused publisher nor signal
        # its already-reaped PID, which the OS could now reuse.
        monkeypatch.setattr(os, "kill", guarded_kill)
        assert popen.poll() is None
        assert popen.wait(0) is None
        popen.terminate()
        popen.kill()
        assert unsafe_signals == []
        enter_join.set()
        assert owner_acquiring.wait(_WATCHDOG), errors
        if expired:
            expire_clock.set()
    finally:
        enter_join.set()
        publish.set()
        owner.join(_WATCHDOG)
        if competitor.ident is not None:
            competitor.join(_WATCHDOG)
        for thread in deferred:
            thread.join(_WATCHDOG)
    assert not owner.is_alive() and not competitor.is_alive()
    assert len(deferred) == 2 and all(not thread.is_alive() for thread in deferred)
    assert unsafe_signals == []
    assert not errors, errors
    assert target["popen"].returncode == 0
    assert results["competitor"].status == "completed"
    assert results["competitor"].value == 9 and results["competitor"].exitcode == 0
    if expired:
        # A valid payload and eventual exitcode 0 do not authorize a decision
        # after the whole-call deadline. This clock jump avoids a slow test.
        assert results["owner"].status == "inconclusive"
        assert "deadline" in results["owner"].reason
        assert results["owner"].value is None and results["owner"].exitcode == 0
        assert results["owner"].wall_seconds >= 10
    else:
        assert results["owner"].status == "completed"
        assert results["owner"].value == 3 and results["owner"].exitcode == 0
        assert results["owner"].wall_seconds < 10


def test_expired_owner_preserves_signals_until_a_paused_reaper_resumes(monkeypatch):
    """A lock held before waitpid does not imply that the child has exited."""
    started, in_poll, release_poll, expired, owner_done = (Event() for _ in range(5))
    target, results, errors = {}, {}, {}
    real_poll = _ForkPopen.poll
    real_start = execution._ReapingProcess.start
    real_perf_counter = time.perf_counter
    deferred = _capture_deferred_threads(monkeypatch)

    def process_start(self):
        real_start(self)
        if current_thread().name == "owner":
            target["popen"] = self._popen
            started.set()

    def paused_poll(self, flag=os.WNOHANG):
        if self is target.get("popen") and current_thread().name == "competitor":
            in_poll.set()
            assert release_poll.wait(_WATCHDOG), "live child's reaper was not released"
        return real_poll(self, flag)

    def perf_counter():
        offset = 20 if current_thread().name == "owner" and expired.is_set() else 0
        return real_perf_counter() + offset

    def run(name, function, argument):
        try:
            results[name] = execution.run_isolated(
                function, argument,
                limits=execution.HardLimits(wall_seconds=10, memory_bytes=None),
            )
        except BaseException as error:  # noqa: BLE001 -- surface thread failures in the test
            errors[name] = error
        finally:
            if name == "owner":
                owner_done.set()

    monkeypatch.setattr(execution._ReapingProcess, "start", process_start)
    monkeypatch.setattr(_ForkPopen, "poll", paused_poll)
    monkeypatch.setattr(execution, "time", SimpleNamespace(
        perf_counter=perf_counter, monotonic=time.monotonic, sleep=time.sleep,
    ))
    owner = Thread(target=run, args=("owner", time.sleep, 30), name="owner")
    competitor = Thread(target=run, args=("competitor", sum, [4, 5]), name="competitor")
    owner.start()
    try:
        assert started.wait(_WATCHDOG), errors
        competitor.start()
        assert in_poll.wait(_WATCHDOG), errors
        os.kill(target["popen"].pid, 0)  # child is still alive; no actual signal
        expired.set()
        assert owner_done.wait(_WATCHDOG), errors
        assert not errors, errors
        result = results["owner"]
        assert result.status == "inconclusive" and result.value is None
        assert "deadline" in result.reason and result.exitcode is None
        assert len(deferred) == 2 and all(thread.is_alive() for thread in deferred)
        # Return did not wait for the held reaper or discard either request.
        assert not release_poll.is_set()
    finally:
        release_poll.set()
        owner.join(_WATCHDOG)
        if competitor.ident is not None:
            competitor.join(_WATCHDOG)
        for thread in deferred:
            thread.join(_WATCHDOG)
    assert not owner.is_alive() and not competitor.is_alive()
    assert not errors, errors
    assert all(not thread.is_alive() for thread in deferred)
    assert target["popen"].returncode < 0  # killed, not a naturally completed worker
    with pytest.raises(ChildProcessError):
        os.waitpid(target["popen"].pid, os.WNOHANG)  # actually reaped
    assert results["competitor"].status == "completed"
    assert results["competitor"].value == 9 and results["competitor"].exitcode == 0


@pytest.mark.parametrize("timeout", [None, 1.0])
def test_ready_sentinel_does_not_make_join_return_before_exit(monkeypatch, timeout):
    popen = object.__new__(execution._ReapingPopen)
    popen.returncode, popen.sentinel = None, 123
    popen._reap_lock = Lock()
    polls, pauses = [], []

    def poll(self, flag):
        assert flag == os.WNOHANG
        polls.append(flag)
        if len(polls) == 2:
            self.returncode = 0
        return self.returncode

    def pause(seconds):
        assert popen._reap_lock.acquire(blocking=False), "waiting held the reaping lock"
        popen._reap_lock.release()
        pauses.append(seconds)

    monkeypatch.setattr(_ForkPopen, "poll", poll)
    monkeypatch.setattr(execution, "_wait_handles", lambda handles, timeout: handles)
    monkeypatch.setattr(execution, "time", SimpleNamespace(
        monotonic=lambda: 0, sleep=pause,
    ))
    assert popen.wait(timeout) == 0
    assert len(polls) == 2 and pauses == [0.001]


def test_unavailable_exit_status_obeys_the_original_join_budget(monkeypatch):
    popen = object.__new__(execution._ReapingPopen)
    popen.returncode, popen.sentinel = None, 123
    popen._reap_lock = Lock()
    clock = [0.0]
    waits, polls = [], []

    def sentinel_wait(handles, timeout):
        waits.append(timeout)
        clock[0] += 0.002
        return handles

    def poll(self, flag):
        polls.append(flag)

    def pause(seconds):
        assert popen._reap_lock.acquire(blocking=False)
        popen._reap_lock.release()
        clock[0] += seconds

    monkeypatch.setattr(_ForkPopen, "poll", poll)
    monkeypatch.setattr(execution, "_wait_handles", sentinel_wait)
    monkeypatch.setattr(execution, "time", SimpleNamespace(
        monotonic=lambda: clock[0], sleep=pause,
    ))
    assert popen.wait(0.004) is None
    assert clock[0] == pytest.approx(0.004)
    assert waits == [0.004] and polls == [os.WNOHANG] * 3
    assert popen.returncode is None
