"""Adversarial double-isolation tests: no source proof in the parent process."""
from __future__ import annotations

import json
import sys
import time

import pytest

import symq.labs.isolated_miter as producer_transport
import symq.labs.isolated_miter_supervisor as supervisor
from symq import Circuit
from symq.labs.lrat_rup import Limits
from symq.labs.miter_cnf import export_classical_miter_cnf


def _case(valid: bool = True) -> tuple[bytes, str]:
    lhs = Circuit(3).ccx(0, 1, 2)
    if valid:
        lhs.ccx(0, 1, 2)
    rhs = Circuit(3)
    data = producer_transport.make_isolated_miter_request(lhs, rhs)
    source = export_classical_miter_cnf(lhs, rhs)
    return data, source.source_sha256


@pytest.mark.sat
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux worker OS caps")
def test_real_producer_and_trusted_verifier_both_os_limited(monkeypatch):
    request, sha = _case()
    # Prove that the supervising Python interpreter does not parse a Circuit
    # or call the RUP kernel: only the separately spawned verifier may do so.
    def forbidden(*_args, **_kwargs):
        raise AssertionError("supervisor must never verify in-process")

    monkeypatch.setattr(producer_transport, "parse_isolated_miter_request", forbidden)
    from symq.labs import miter_proof_bundle

    monkeypatch.setattr(miter_proof_bundle, "check_classical_miter_proof", forbidden)
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha,
        limits=Limits(max_seconds=12), wall_seconds=15,
        memory_bytes=1073741824,
    )
    assert result["status"] == "proved", result
    assert result["independent_unsat_checked"]
    assert result["source_recomputed"]
    assert result["producer_os_limited"]
    assert result["verifier_os_limited"]
    assert not result["controlled_use_authorized"]


@pytest.mark.sat
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux OS limits")
def test_non_equivalent_source_and_wrong_independent_sha_cannot_prove():
    bad_request, bad_sha = _case(valid=False)
    bad = supervisor.prove_separately_verified_miter_request(
        bad_request, expected_source_sha256=bad_sha,
        wall_seconds=10, memory_bytes=1073741824,
    )
    assert bad["status"] != "proved"
    assert not bad["independent_unsat_checked"]
    valid, _ = _case()
    forged = supervisor.prove_separately_verified_miter_request(
        valid, expected_source_sha256="0" * 64,
        wall_seconds=10, memory_bytes=1073741824,
    )
    assert forged["status"] != "proved"
    assert not forged["independent_unsat_checked"]


def _proposal_command(*_args, **_kwargs) -> list[str]:
    response = json.dumps(
        {"schema_version": 1, "status": "proposal", "bundle": {}},
        sort_keys=True, separators=(",", ":"),
    )
    return [sys.executable, "-I", "-c", f"print({response!r})"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux worker supervision")
def test_forged_producer_proposal_is_rejected_by_actual_verifier(monkeypatch):
    request, sha = _case()
    monkeypatch.setattr(supervisor, "_worker_command", _proposal_command)
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha,
        wall_seconds=5, memory_bytes=1073741824,
    )
    assert result["producer_os_limited"]
    assert result["verifier_os_limited"]
    assert result["status"] != "proved"
    assert not result["independent_unsat_checked"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux worker supervision")
def test_verifier_timeout_cannot_return_a_positive(monkeypatch):
    request, sha = _case()
    monkeypatch.setattr(supervisor, "_worker_command", _proposal_command)
    monkeypatch.setattr(
        supervisor, "_verifier_command",
        lambda *_a, **_kw: [sys.executable, "-I", "-c", "import time;time.sleep(60)"],
    )
    start = time.monotonic()
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha, wall_seconds=0.3,
    )
    assert time.monotonic() - start < 4
    assert result["status"] == "inconclusive"
    assert not result["independent_unsat_checked"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux worker supervision")
def test_verifier_memory_pressure_cannot_return_a_positive(monkeypatch):
    request, sha = _case()
    monkeypatch.setattr(supervisor, "_worker_command", _proposal_command)
    hog = (
        "import resource;"
        "resource.setrlimit(resource.RLIMIT_AS,(134217728,134217728));"
        "x=bytearray(536870912)"
    )
    monkeypatch.setattr(
        supervisor, "_verifier_command",
        lambda *_a, **_kw: [sys.executable, "-I", "-c", hog],
    )
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha, wall_seconds=3,
    )
    assert result["status"] == "inconclusive"
    assert not result["independent_unsat_checked"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux worker supervision")
def test_failed_process_cleanup_cannot_release_a_positive(monkeypatch):
    request, sha = _case()
    monkeypatch.setattr(supervisor, "_worker_command", _proposal_command)

    def failed_cleanup(_proc):
        raise OSError("injected killpg failure")

    monkeypatch.setattr(supervisor, "_kill_group", failed_cleanup)
    with pytest.raises(RuntimeError, match="cleanup"):
        supervisor.prove_separately_verified_miter_request(
            request, expected_source_sha256=sha,
            wall_seconds=3,
        )


def test_protocol_strictness_and_oversized_request_no_process_spawn(monkeypatch):
    for data in (
        b'{"schema_version":1,"status":"verified","source_sha256":"x"}',
        b'{"schema_version":1,"status":"verified","source_sha256":"0","cnf_sha256":"0"}',
        b'{"schema_version":1,"status":"verified","source_sha256":"0","cnf_sha256":"0","extra":1}',
        b'{"schema_version":1,"status":"proposal","bundle":{},"bundle":{}}',
        b'{"schema_version":1,"status":true}',
    ):
        with pytest.raises((ValueError, supervisor._ProtocolError)):
            supervisor._decode_response(data, role="verifier")
    def forbidden(*_a, **_kw):
        raise AssertionError("too-large request must never run worker")
    monkeypatch.setattr(supervisor, "_worker_command", forbidden)
    data = b"x" * 140000
    result = supervisor.prove_separately_verified_miter_request(
        data, expected_source_sha256="0" * 64,
    )
    assert result["status"] in {"invalid", "unsupported"}
    assert not result["independent_unsat_checked"]


def test_unsupported_os_and_inherited_budget_fail_closed(monkeypatch):
    request, sha = _case()
    with monkeypatch.context() as patch:
        patch.setattr(supervisor.sys, "platform", "darwin")
        result = supervisor.prove_separately_verified_miter_request(
            request, expected_source_sha256=sha,
        )
    assert result["status"] == "unsupported"
    assert not result["independent_unsat_checked"]
    if sys.platform.startswith("linux"):
        from symq.resources import Budget, VerificationSession

        with VerificationSession(Budget(max_bytes=16)):
            limited = supervisor.prove_separately_verified_miter_request(
                request, expected_source_sha256=sha,
            )
        assert limited["status"] == "unsupported"
        assert not limited["independent_unsat_checked"]



@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process groups")
def test_descendant_holding_verifier_pipe_is_killed_on_deadline(monkeypatch):
    request, sha = _case()
    monkeypatch.setattr(supervisor, "_worker_command", _proposal_command)
    # The verifier exits but a same-process-group descendant retains stdout.
    # The parent must keep waiting for pipe EOF and then kill the group.
    code = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-I','-c',"
        "'import time;time.sleep(60)']);"
        "print('verifier exited',flush=True)"
    )
    monkeypatch.setattr(
        supervisor, "_verifier_command",
        lambda *_a, **_kw: [sys.executable, "-I", "-c", code],
    )
    started = time.monotonic()
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha, wall_seconds=0.35,
    )
    assert time.monotonic() - started < 4
    assert result["status"] == "inconclusive"
    assert not result["independent_unsat_checked"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux child output")
def test_verifier_stdout_flood_and_nonzero_exit_both_refused(monkeypatch):
    request, sha = _case()
    monkeypatch.setattr(supervisor, "_worker_command", _proposal_command)
    monkeypatch.setattr(
        supervisor, "_verifier_command",
        lambda *_a, **_kw: [
            sys.executable, "-I", "-c",
            "import sys;sys.stdout.write('X'*100000)",
        ],
    )
    flood = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha, wall_seconds=3,
    )
    assert flood["status"] == "inconclusive"
    assert not flood["independent_unsat_checked"]
    assert "stdout limit" in flood["reason"]

    # Even a well-formed, apparently positive verdict has no authority
    # when the trusted verifier process crashes or exits nonzero.
    fake = json.dumps(
        {"schema_version": 1, "status": "verified",
         "source_sha256": sha, "cnf_sha256": "1" * 64},
        sort_keys=True, separators=(",", ":"),
    )
    monkeypatch.setattr(
        supervisor, "_verifier_command",
        lambda *_a, **_kw: [
            sys.executable, "-I", "-c",
            f"import sys;print({fake!r});sys.exit(7)",
        ],
    )
    failed = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha, wall_seconds=3,
    )
    assert failed["status"] == "inconclusive"
    assert not failed["independent_unsat_checked"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux wall monitor")
def test_outer_verification_session_deadline_is_not_reset(monkeypatch):
    from symq.errors import ResourceLimitExceeded
    from symq.resources import Budget, VerificationSession

    monkeypatch.setattr(
        supervisor, "_worker_command",
        lambda *_a, **_kw: [
            sys.executable, "-I", "-c", "import time;time.sleep(60)",
        ],
    )
    request, sha = _case()
    started = time.monotonic()
    result = {}
    try:
        with VerificationSession(Budget(max_seconds=0.2)):
            result = supervisor.prove_separately_verified_miter_request(
                request, expected_source_sha256=sha, wall_seconds=15,
            )
    except ResourceLimitExceeded:
        # VerificationSession independently checks its deadline at exit.
        pass
    assert time.monotonic() - started < 4
    assert result["status"] == "inconclusive"
    assert not result["independent_unsat_checked"]



@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux WNOWAIT")
def test_group_leader_remains_unreaped_until_process_group_cleanup(monkeypatch):
    import os

    request, sha = _case()
    response = json.dumps(
        {"schema_version": 1, "status": "inconclusive"},
        sort_keys=True, separators=(",", ":"),
    )
    monkeypatch.setattr(
        supervisor, "_worker_command",
        lambda *_a, **_kw: [sys.executable, "-I", "-c", f"print({response!r})"],
    )
    original_kill = supervisor._kill_group
    observed = []

    def kill_before_reap(proc):
        assert proc.returncode is None
        # The leader's PID is still reserved because the supervisor used
        # waitid(WNOWAIT), not Popen.wait/poll, before group termination.
        status = os.waitid(
            os.P_PID, proc.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG,
        )
        assert status is not None
        observed.append(proc.pid)
        original_kill(proc)

    monkeypatch.setattr(supervisor, "_kill_group", kill_before_reap)
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha, wall_seconds=3,
    )
    assert result["status"] == "inconclusive"
    assert not result["independent_unsat_checked"]
    assert len(observed) == 1



def test_missing_waitid_wnowait_capability_refuses_before_start(monkeypatch):
    request, sha = _case()

    def must_not_spawn(*_args, **_kwargs):
        raise AssertionError("unsupported platform must not start worker")

    with monkeypatch.context() as scope:
        scope.delattr(supervisor.os, "WNOWAIT", raising=False)
        scope.setattr(supervisor, "_worker_command", must_not_spawn)
        result = supervisor.prove_separately_verified_miter_request(
            request, expected_source_sha256=sha,
        )
    assert result["status"] == "unsupported"
    assert not result["independent_unsat_checked"]



def test_deeply_nested_untrusted_worker_frame_is_invalid_not_uncaught():
    # Well below the output byte cap, but beyond Python's JSON nesting
    # depth. Parsing must yield the same fail-closed protocol refusal.
    nested = b"[" * 1500 + b"0" + b"]" * 1500
    for role in ("producer", "verifier"):
        with pytest.raises(supervisor._ProtocolError, match="invalid or over-nested"):
            supervisor._decode_response(nested, role=role)
