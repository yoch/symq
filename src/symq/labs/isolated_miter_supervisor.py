"""Two-stage OS-limited SAT proof production and *trusted* verification.

The public parent only validates bounded bytes, supervises child processes and
checks a tiny verdict frame. Both the untrusted SAT proof producer and the
trusted source/CNF/RUP verifier run in separate Linux processes with virtual
address-space, CPU and parent-enforced wall/output limits.

The verifier executable is fixed installed SymQ code, not chosen by the
request or producer. This is not an arbitrary-Python security sandbox.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from symq.labs.isolated_miter import (
    _kill_group,
    _read_bounded,
    _strict_pairs,
    _TransportLimit,
    _worker_command,
)
from symq.labs.lrat_rup import Limits
from symq.resources import Guard, ResourceLimitExceeded

_PIN = re.compile(r"[0-9a-f]{64}\Z")

# Exactly the same OS limit bootstrap as the untrusted producer, but the
# module is an independent fixed *trusted* verifier and never imports PySAT.
_VERIFY_BOOT = (
    "import resource,runpy,sys;"
    "m=int(sys.argv[1]);c=int(sys.argv[2]);"
    "resource.setrlimit(resource.RLIMIT_AS,(m,m));"
    "resource.setrlimit(resource.RLIMIT_CPU,(c,c+1));"
    "sys.argv=['_isolated_miter_verifier']+sys.argv[3:];"
    "runpy.run_module('symq.labs._isolated_miter_verifier',run_name='__main__')"
)


class _ProtocolError(ValueError):
    """An untrusted worker result did not satisfy its exact response schema."""


def _decode_response(blob: bytes, *, role: str) -> dict:
    try:
        payload = json.loads(blob.decode("utf-8"), object_pairs_hook=_strict_pairs)
    except (UnicodeDecodeError, ValueError) as exc:
        raise _ProtocolError(f"{role}: invalid JSON or repeated field") from exc
    if type(payload) is not dict or type(payload.get("schema_version")) is not int:
        raise _ProtocolError(f"{role}: invalid response container")
    if payload["schema_version"] != 1 or type(payload.get("status")) is not str:
        raise _ProtocolError(f"{role}: wrong version or status type")
    status = payload["status"]
    if role == "producer":
        if status == "proposal":
            if set(payload) != {"schema_version", "status", "bundle"}:
                raise _ProtocolError("producer: malformed proof proposal")
            if type(payload["bundle"]) is not dict:
                raise _ProtocolError("producer: bundle must be an object")
        elif status in {"not_proved", "inconclusive", "unsupported", "invalid"}:
            if set(payload) != {"schema_version", "status"}:
                raise _ProtocolError("producer: malformed non-proof result")
        else:
            raise _ProtocolError("producer: invalid status")
    elif role == "verifier":
        if status == "verified":
            if set(payload) != {"schema_version", "status",
                                "source_sha256", "cnf_sha256"}:
                raise _ProtocolError("verifier: malformed positive verdict")
            if any(type(payload[name]) is not str or not _PIN.fullmatch(payload[name])
                   for name in ("source_sha256", "cnf_sha256")):
                raise _ProtocolError("verifier: invalid digest")
        elif status in {"invalid", "inconclusive"}:
            if set(payload) != {"schema_version", "status"}:
                raise _ProtocolError("verifier: malformed refusal")
        else:
            raise _ProtocolError("verifier: invalid status")
    else:
        raise ValueError("unknown internal worker role")
    return payload


def _verifier_command(memory_bytes: int, cpu_seconds: int,
                      request_path: str, proposal_path: str,
                      expected_source_sha256: str, wall_seconds: float,
                      request_limit: int, output_limit: int,
                      limits: Limits) -> list[str]:
    """A hardcoded verified module, with no attacker-selected executable path."""
    return [
        sys.executable, "-I", "-c", _VERIFY_BOOT,
        str(memory_bytes), str(cpu_seconds),
        request_path, proposal_path, expected_source_sha256,
        str(wall_seconds), str(request_limit), str(output_limit),
        str(limits.max_bytes), str(limits.max_variables),
        str(limits.max_clauses), str(limits.max_steps), str(limits.max_visits),
    ]


def _wait_exited_no_reap(proc: subprocess.Popen, deadline: float) -> bool:
    """Observe exit without reaping: the leader PID pins its process-group ID.

    Linux WNOWAIT prevents a reusable group ID between the exit check and
    killpg. We only reap the leader *after* terminating any descendants.
    """
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise _TransportLimit("worker exit deadline exceeded")
        status = os.waitid(
            os.P_PID, proc.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG,
        )
        if status is not None:
            return status.si_code == os.CLD_EXITED and status.si_status == 0
        time.sleep(min(0.01, remaining))


def _run_capped(command: list[str], *, deadline: float,
                max_output_bytes: int) -> bytes:
    """Supervise one child, fail closed on all incomplete transport/cleanup."""
    proc = None
    try:
        if time.perf_counter() >= deadline:
            raise _TransportLimit("worker deadline before spawn")
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=True, start_new_session=True,
        )
        data, _stderr = _read_bounded(
            proc, deadline=deadline, max_output_bytes=max_output_bytes,
        )
        if not _wait_exited_no_reap(proc, deadline):
            raise _TransportLimit("worker process failed")
        # The process-group leader is still unreaped, so its PGID cannot be
        # recycled before the cleanup in finally.
        return data
    finally:
        if proc is not None:
            cleanup_error: OSError | subprocess.TimeoutExpired | None = None
            try:
                _kill_group(proc)
            except OSError as error:
                cleanup_error = error
            # Reap the pinned leader only after sending the group signal.
            try:
                proc.wait(timeout=2.0)
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup_error = error
            finally:
                for stream in (proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()
            if cleanup_error is not None:
                # Never release a provisional positive if cleanup is ambiguous.
                raise RuntimeError("worker group cleanup not confirmed") from cleanup_error


def prove_separately_verified_miter_request(
    request: bytes,
    *,
    expected_source_sha256: str,
    wall_seconds: float = 16.0,
    memory_bytes: int = 1073741824,
    max_request_bytes: int = 131072,
    max_output_bytes: int = 2097152,
    limits: Limits | None = None,
) -> dict:
    """Never run SAT, source-CNF encoding or RUP verification in the parent.

    Both worker subprocesses have independent Linux RLIMIT_AS / RLIMIT_CPU
    and the same parent deadline. The parent handles only size-bounded
    protocol frames. All positive verdicts come from a separate trusted,
    fixed-code verifier process, not from the untrusted proof producer.

    RLIMIT_AS bounds virtual address space, not RSS; process creation,
    Python interpreter overhead and cleanup can extend elapsed wall time.
    """
    result = {
        "status": "inconclusive", "independent_unsat_checked": False,
        "controlled_use_authorized": False, "source_recomputed": False,
        "producer_os_limited": False, "verifier_os_limited": False,
    }
    required_os = ("killpg", "waitid", "WNOWAIT", "WNOHANG", "WEXITED", "P_PID")
    if (not sys.platform.startswith("linux") or
            any(not hasattr(os, name) for name in required_os)):
        return {**result, "status": "unsupported",
                "reason": "Linux process-group, waitid(WNOWAIT) and RLIMIT_AS required"}
    if (type(wall_seconds) not in (float, int) or
            not math.isfinite(wall_seconds) or not 0 < wall_seconds <= 300):
        raise ValueError("wall_seconds must be finite in (0, 300]")
    for name, value, low, high in (
        ("memory_bytes", memory_bytes, 134217728, 4294967296),
        ("max_request_bytes", max_request_bytes, 1, 1048576),
        ("max_output_bytes", max_output_bytes, 1, 16777216),
    ):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} outside allowed bounds")
    if (type(expected_source_sha256) is not str or
            _PIN.fullmatch(expected_source_sha256) is None):
        raise ValueError("independent lowercase source SHA-256 required")
    if type(request) is not bytes or not request or len(request) > max_request_bytes:
        return {**result, "status": "invalid", "reason": "request byte ceiling"}
    proof_limits = Limits() if limits is None else limits
    if type(proof_limits) is not Limits:
        raise TypeError("exact proof Limits required")
    proof_limits.validate()
    inherited = Guard()
    if any((inherited.budget.max_bytes is not None,
            inherited.budget.max_nodes is not None,
            inherited.budget.max_terms is not None)):
        return {**result, "status": "unsupported",
                "reason": "unaccounted inherited byte/node/term budget"}
    try:
        inherited.check_time()
    except ResourceLimitExceeded as error:
        return {**result, "status": "inconclusive", "reason": str(error)}
    now = time.perf_counter()
    deadline = now + wall_seconds
    if inherited.deadline is not None:
        deadline = min(deadline, inherited.deadline)
    try:
        with tempfile.TemporaryDirectory(prefix="symq-verified-miter-") as tmp:
            source_file = str(Path(tmp) / "request.json")
            proposal_file = str(Path(tmp) / "proposal.json")
            Path(source_file).write_bytes(request)
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise _TransportLimit("budget exhausted before producer")
            cpu = max(1, math.ceil(remaining))
            raw = _run_capped(
                _worker_command(
                    memory_bytes, cpu, source_file,
                    min(remaining, proof_limits.max_seconds),
                    proof_limits, max_request_bytes,
                ),
                deadline=deadline,
                max_output_bytes=max_output_bytes,
            )
            result["producer_os_limited"] = True
            producer = _decode_response(raw, role="producer")
            if producer["status"] != "proposal":
                return {**result, "status": producer["status"]}
            # The proposal is untrusted. Only a trusted verifier may parse
            # the source into a Circuit or issue a source-equivalence verdict.
            Path(proposal_file).write_bytes(raw)
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise _TransportLimit("budget exhausted before verifier")
            cpu = max(1, math.ceil(remaining))
            verification_raw = _run_capped(
                _verifier_command(
                    memory_bytes, cpu, source_file, proposal_file,
                    expected_source_sha256,
                    min(remaining, proof_limits.max_seconds),
                    max_request_bytes, max_output_bytes,
                    proof_limits,
                ),
                deadline=deadline, max_output_bytes=4096,
            )
            result["verifier_os_limited"] = True
            checked = _decode_response(verification_raw, role="verifier")
            if checked["status"] != "verified":
                return {**result, "status": checked["status"]}
            if checked["source_sha256"] != expected_source_sha256:
                raise _ProtocolError("verifier returned a different source identity")
            if time.perf_counter() >= deadline:
                raise _TransportLimit("verdict returned past parent deadline")
            return {
                **result, "status": "proved", "independent_unsat_checked": True,
                "source_recomputed": True, "cnf_sha256": checked["cnf_sha256"],
                "source_sha256": expected_source_sha256,
            }
    except (OSError, ValueError, UnicodeError, _TransportLimit) as error:
        return {**result, "status": "inconclusive",
                "independent_unsat_checked": False,
                "source_recomputed": False, "reason": str(error)[:200]}
