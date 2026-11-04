"""Research-only isolated producer for source-bound classical SAT-miter proofs.

The child is a separately killable Linux process with RLIMIT_AS / RLIMIT_CPU.
Its result is *untrusted*: only the parent-side solver-free source/CNF/RUP
checker can return proved. This is NOT a hostile-Python sandbox, nor a
hard deadline or RSS bound on the parent-side source verification.
"""
from __future__ import annotations

import json
import math
import os
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from symq.circuit import Circuit, circuit_from_dict
from symq.labs.lrat_rup import Limits
from symq.resources import Guard, ResourceLimitExceeded
from symq.sat.encoding import Contract

_KIND = "symq_classical_miter_isolated_v1"
_PIN = re.compile(r"[0-9a-f]{64}\Z")
_BOOT = (
    "import resource,runpy,sys;"
    "m=int(sys.argv[1]);c=int(sys.argv[2]);"
    "resource.setrlimit(resource.RLIMIT_AS,(m,m));"
    "resource.setrlimit(resource.RLIMIT_CPU,(c,c+1));"
    "resource.setrlimit(resource.RLIMIT_CORE,(0,0));"
    "sys.argv=['_isolated_miter_worker']+sys.argv[3:];"
    "runpy.run_module('symq.labs._isolated_miter_worker',run_name='__main__')"
)


class _TransportLimit(Exception):
    """The worker transport did not return a bounded, complete result."""


def _pairs(items: object, name: str) -> dict[int, int]:
    if type(items) is not list:
        raise ValueError(f"{name} must be a list of exact integer pairs")
    result: dict[int, int] = {}
    for item in items:
        if (type(item) is not list or len(item) != 2
                or any(type(v) is not int for v in item)):
            raise ValueError(f"{name}: invalid pair")
        a, b = item
        if a in result:
            raise ValueError(f"{name}: repeated key")
        result[a] = b
    return result


def _strict_pairs(values):
    output = {}
    for key, value in values:
        if key in output:
            raise ValueError("duplicate JSON object field")
        output[key] = value
    return output


def parse_isolated_miter_request(request: bytes, *, max_request_bytes: int = 131072,
                                 max_source_gates: int = 5000,
                                 max_width: int = 256
                                 ) -> tuple[Circuit, Circuit, Contract]:
    """Bound bytes and gate count before constructing even one Circuit.

    The input is canonical JSON and a strictly closed request vocabulary;
    no filenames, executable paths, module names or Python objects come from it.
    """
    if type(request) is not bytes or not request or len(request) > max_request_bytes:
        raise ValueError("invalid or oversized request bytes")
    try:
        obj = json.loads(request.decode("utf-8"), object_pairs_hook=_strict_pairs)
    except RecursionError as error:
        raise ValueError("over-nested isolated request JSON") from error
    if (type(obj) is not dict or set(obj) != {"kind", "schema_version", "left", "right",
                                               "contract"}
            or type(obj["kind"]) is not str or obj["kind"] != _KIND
            or type(obj["schema_version"]) is not int or obj["schema_version"] != 1):
        raise ValueError("unsupported isolated request schema")
    if type(obj["left"]) is not dict or type(obj["right"]) is not dict:
        raise ValueError("source circuits must be objects")
    left_raw, right_raw = obj["left"], obj["right"]
    for raw in (left_raw, right_raw):
        if type(raw.get("gates")) is not list:
            raise ValueError("source gates must be lists")
        if (type(raw.get("width")) is not int
                or not 1 <= raw["width"] <= max_width):
            raise ValueError("source width outside isolated limit")
    if len(left_raw["gates"]) + len(right_raw["gates"]) > max_source_gates:
        raise ValueError("source gate limit")
    c = obj["contract"]
    if (type(c) is not dict or
            set(c) != {"input_constants", "observed_outputs",
                       "restored_wires", "output_map"}):
        raise ValueError("unsupported classical contract schema")
    observations = c["observed_outputs"]
    if observations is not None and (
            type(observations) is not list or
            any(type(x) is not int for x in observations)):
        raise ValueError("observed outputs must be integer array or null")
    restored = c["restored_wires"]
    if type(restored) is not list or any(type(x) is not int for x in restored):
        raise ValueError("restored wires must be integer array")
    try:
        left = circuit_from_dict(left_raw)
        right = circuit_from_dict(right_raw)
    except TypeError as error:
        # Gate() reports non-integer qubits as TypeError; keep one refusal type.
        raise ValueError(f"invalid source gate: {error}") from error
    contract = Contract(
        input_constants=_pairs(c["input_constants"], "input_constants"),
        observed_outputs=None if observations is None else tuple(observations),
        restored_wires=tuple(restored),
        output_map=_pairs(c["output_map"], "output_map"),
    )
    if left.width != right.width:
        raise ValueError("source widths differ")
    contract.validate(left.width)
    if contract.assumption is not None:
        raise ValueError("assumption AST unsupported by isolated proof contract")
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
    if canonical != request:
        raise ValueError("isolated request must use canonical JSON bytes")
    return left, right, contract


def make_isolated_miter_request(left: Circuit, right: Circuit,
                                contract: Contract | None = None) -> bytes:
    """Produce a canonical request; not a proof or externally authenticated pin."""
    if type(left) is not Circuit or type(right) is not Circuit:
        raise TypeError("exact Circuits required")
    if contract is not None and type(contract) is not Contract:
        raise TypeError("exact Contract required")
    value = Contract() if contract is None else contract
    value.validate(left.width)
    if value.assumption is not None or left.width != right.width:
        raise ValueError("unsupported isolated circuit or assumption")
    obj = {
        "kind": _KIND, "schema_version": 1,
        "left": left.to_dict(), "right": right.to_dict(),
        "contract": {
            "input_constants": [[k, v] for k, v in sorted(value.input_constants.items())],
            "observed_outputs": None if value.observed_outputs is None
            else list(value.observed_outputs),
            "restored_wires": list(value.restored_wires),
            "output_map": [[k, v] for k, v in sorted(value.output_map.items())],
        },
    }
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    parse_isolated_miter_request(payload)
    return payload


def _worker_command(memory_bytes: int, cpu_seconds: int, request_path: str,
                    wall_seconds: float, limits: Limits,
                    request_limit: int) -> list[str]:
    # -I disables user site, PYTHONPATH, and the current working directory.
    # The fixed bootstrap installs RLIMIT_AS / RLIMIT_CPU *before* importing
    # the SymQ worker. No user input can provide executable code or a module.
    return [
        sys.executable, "-I", "-c", _BOOT, str(memory_bytes), str(cpu_seconds),
        request_path, str(wall_seconds), str(request_limit), str(limits.max_bytes),
        str(limits.max_variables), str(limits.max_clauses),
        str(limits.max_steps), str(limits.max_visits),
    ]


def _kill_group(proc: subprocess.Popen) -> None:
    # Every spawned child gets its own session/process group. A child may
    # leave a descendant holding a pipe open: kill the entire group.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _wait_exited_no_reap(proc: subprocess.Popen, deadline: float) -> bool:
    """Observe exit without reaping: the leader PID pins its process-group ID."""
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


def _read_bounded(proc: subprocess.Popen, *, deadline: float,
                  max_output_bytes: int) -> tuple[bytes, bytes]:
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    with selectors.DefaultSelector() as poller:
        for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if stream is None:
                raise _TransportLimit("worker pipe missing")
            os.set_blocking(stream.fileno(), False)
            poller.register(stream, selectors.EVENT_READ, name)
        while poller.get_map():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise _TransportLimit("worker wall deadline exceeded")
            for key, _events in poller.select(timeout=min(remaining, 0.1)):
                try:
                    chunk = os.read(key.fileobj.fileno(), 4096)
                except BlockingIOError:
                    continue
                if not chunk:
                    poller.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                buf = buffers[key.data]
                if len(buf) + len(chunk) > max_output_bytes:
                    raise _TransportLimit(f"worker {key.data} limit exceeded")
                buf.extend(chunk)
    return bytes(buffers["stdout"]), bytes(buffers["stderr"])


def prove_isolated_miter_request(
    request: bytes,
    *,
    expected_source_sha256: str,
    wall_seconds: float = 8.0,
    memory_bytes: int = 805306368,
    max_request_bytes: int = 131072,
    max_output_bytes: int = 2097152,
    limits: Limits | None = None,
) -> dict:
    """Use an OS-limited Linux producer and independently recheck any proof.

    Only the child process gets an OS-enforced address-space + CPU limit.
    The parent-side input parsing and LRAT checking remain *cooperative*;
    this is not an end-to-end process RSS or hostile-code isolation API.
    """
    result = {
        "status": "inconclusive", "independent_unsat_checked": False,
        "controlled_use_authorized": False, "source_recomputed": False,
        "hard_worker_limit": False,
    }
    if (not sys.platform.startswith("linux") or any(
            not hasattr(os, n) for n in
            ("killpg", "waitid", "WNOWAIT", "WNOHANG", "WEXITED", "P_PID"))):
        return {**result, "status": "unsupported",
                "reason": "Linux RLIMIT_AS and isolated process group required"}
    if (type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds)
            or not 0 < wall_seconds <= 300):
        raise ValueError("wall_seconds must be finite in (0, 300]")
    for name, n, minimum, maximum in (
        ("memory_bytes", memory_bytes, 134217728, 4294967296),
        ("max_request_bytes", max_request_bytes, 1, 1048576),
        ("max_output_bytes", max_output_bytes, 1, 16777216),
    ):
        if type(n) is not int or not minimum <= n <= maximum:
            raise ValueError(f"{name} outside supported range")
    if (type(expected_source_sha256) is not str or
            _PIN.fullmatch(expected_source_sha256) is None):
        raise ValueError("independently obtained lowercase source SHA-256 is required")
    if type(request) is not bytes or not request or len(request) > max_request_bytes:
        return {**result, "status": "invalid", "reason": "request byte limit"}

    bound = Limits() if limits is None else limits
    if type(bound) is not Limits:
        raise TypeError("exact Limits required")
    bound.validate()
    session_guard = Guard()
    if any((
        session_guard.budget.max_nodes is not None,
        session_guard.budget.max_terms is not None,
        session_guard.budget.max_bytes is not None,
    )):
        return {**result, "status": "unsupported",
                "reason": "inherited node/term/byte resource policy unsupported"}
    try:
        session_guard.check_time()
    except ResourceLimitExceeded as error:
        return {**result, "status": "inconclusive", "reason": str(error)}
    started = time.perf_counter()
    deadline = started + wall_seconds
    if session_guard.deadline is not None:
        deadline = min(deadline, session_guard.deadline)
    cpu_seconds = max(1, math.ceil(max(0.001, deadline - started)))
    proc = None
    try:
        with tempfile.TemporaryDirectory(prefix="symq-miter-worker-") as directory:
            name = str(Path(directory) / "source.json")
            Path(name).write_bytes(request)
            command = _worker_command(
                memory_bytes, cpu_seconds, name,
                min(max(0.001, deadline - time.perf_counter()), bound.max_seconds),
                bound, max_request_bytes,
            )
            proc = subprocess.Popen(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, close_fds=True,
            )
            output, _stderr = _read_bounded(
                proc, deadline=deadline, max_output_bytes=max_output_bytes,
            )
            # Observe exit WITHOUT reaping, then signal the still-pinned group,
            # then reap: never killpg() a PGID whose leader was already reaped.
            exited_ok = _wait_exited_no_reap(proc, deadline)
            done, proc = proc, None        # finally must not killpg a reaped PGID
            try:
                _kill_group(done)
                done.wait(timeout=2.0)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise RuntimeError("isolated worker cleanup was not confirmed") from error
            finally:
                for stream in (done.stdout, done.stderr):
                    if stream is not None:
                        stream.close()
            if not exited_ok:
                raise _TransportLimit("worker failed or was killed under OS limits")
            try:
                response = json.loads(output.decode("utf-8"), object_pairs_hook=_strict_pairs)
            except RecursionError as error:
                raise _TransportLimit("over-nested worker JSON") from error
            if (type(response) is not dict or
                    set(response) not in ({"schema_version", "status"},
                                         {"schema_version", "status", "bundle"})
                    or type(response["schema_version"]) is not int
                    or response["schema_version"] != 1
                    or type(response["status"]) is not str):
                raise _TransportLimit("worker result schema rejected")
            if response["status"] != "proposal":
                if set(response) != {"schema_version", "status"} or response["status"] not in {
                    "not_proved", "inconclusive", "unsupported", "invalid"
                }:
                    raise _TransportLimit("worker non-proof response rejected")
                # UNVERIFIED producer claim: no witness was replayed.
                return {**result, "status": response["status"], "hard_worker_limit": True,
                        "status_origin": "untrusted_producer", "negative_verified": False}
            if set(response) != {"schema_version", "status", "bundle"}:
                raise _TransportLimit("worker proof response schema rejected")

            # A worker's own status/proof/hash is UNTRUSTED. Reparse the
            # original, byte-limited input and regenerate the exact source CNF.
            left, right, contract = parse_isolated_miter_request(
                request, max_request_bytes=max_request_bytes,
            )
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise _TransportLimit("parent verifier deadline exceeded")
            from symq.labs.miter_proof_bundle import check_classical_miter_proof
            from symq.resources import Budget

            checked = check_classical_miter_proof(
                left, right, contract, response["bundle"],
                expected_source_sha256=expected_source_sha256,
                budget=Budget(max_seconds=remaining),
                limits=bound,
            )
            if checked["status"] != "proved" or not checked["independent_unsat_checked"]:
                return {
                    **result, "status": checked["status"], "hard_worker_limit": True,
                    "source_recomputed": checked["source_recomputed"],
                    "reason": checked.get("reason", "parent independently rejected proof"),
                }
            if time.perf_counter() >= deadline:
                raise _TransportLimit("parent verifier deadline exceeded")
            return {
                **result, "status": "proved",
                "independent_unsat_checked": True, "hard_worker_limit": True,
                "source_recomputed": True,
                "source_sha256": checked["source_sha256"],
                "cnf_sha256": checked["cnf_sha256"],
            }
    except (OSError, ValueError, UnicodeError, _TransportLimit,
            ResourceLimitExceeded) as error:
        return {**result, "status": "inconclusive", "reason": str(error)[:200]}
    finally:
        if proc is not None:
            try:
                _kill_group(proc)
                proc.wait(timeout=2.0)
            except (OSError, subprocess.TimeoutExpired) as error:
                # Fail closed: even a valid-looking proof must not be
                # accepted when the worker group could not be reaped.
                raise RuntimeError("isolated worker cleanup was not confirmed") from error
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
