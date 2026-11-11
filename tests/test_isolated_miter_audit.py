"""Regressions from the independent #204 audit (process, protocol and CNF-budget layers)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

import symq.labs.isolated_miter as isolated
import symq.labs.isolated_miter_supervisor as supervisor
from symq import Circuit
from symq.circuit import Gate
from symq.errors import ResourceLimitExceeded
from symq.labs.miter_cnf import export_classical_miter_cnf
from symq.labs.miter_proof_bundle import (
    check_classical_miter_proof,
    export_classical_miter_proof,
)
from symq.resources import Budget, VerificationSession

linux = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux supervision")


def _case() -> tuple[bytes, str]:
    lhs = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    rhs = Circuit(3)
    return (isolated.make_isolated_miter_request(lhs, rhs),
            export_classical_miter_cnf(lhs, rhs).source_sha256)


# --- protocol: one refusal type, no escaping TypeError/RecursionError -------------

def test_request_parser_refuses_non_integer_qubits_and_deep_nesting_as_value_error():
    request = json.loads(isolated.make_isolated_miter_request(Circuit(2).cx(0, 1), Circuit(2)))
    request["left"]["gates"][0][1][0] = True
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    # ``circuit_from_dict`` now refuses non-integer qubits itself, as a ValueError; the parser's
    # own conversion of Gate's TypeError ("invalid source gate") is no longer reached for them.
    with pytest.raises(ValueError, match="gate qubits must be integers"):
        isolated.parse_isolated_miter_request(canonical)
    deep = b"[" * 60_000 + b"]" * 60_000
    with pytest.raises(ValueError):
        isolated.parse_isolated_miter_request(deep, max_request_bytes=200_000)


def test_producer_negative_is_labelled_unverified(monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("supervisor requires Linux")
    request, sha = _case()
    calls = iter([b'{"schema_version":1,"status":"not_proved"}'])
    monkeypatch.setattr(supervisor, "_run_capped", lambda *a, **k: next(calls))
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha)
    assert result["status"] == "not_proved"
    assert result["status_origin"] == "untrusted_producer"
    assert result["negative_verified"] is False


def test_parent_never_parses_a_large_producer_frame(monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("supervisor requires Linux")
    request, sha = _case()
    big = b'{"bundle":' + b" " * 100_000 + b'{}}'
    frames = iter([big, b'{"schema_version":1,"status":"invalid"}'])
    monkeypatch.setattr(supervisor, "_run_capped", lambda *a, **k: next(frames))
    seen: list[int] = []
    original = supervisor._decode_response

    def spy(blob, *, role):
        seen.append(len(blob))
        return original(blob, role=role)

    monkeypatch.setattr(supervisor, "_decode_response", spy)
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha)
    assert result["status"] == "invalid"
    assert all(size <= supervisor._SMALL_FRAME for size in seen)


def test_verifier_inputs_are_not_written_through_producer_planted_symlinks(monkeypatch, tmp_path):
    if not sys.platform.startswith("linux"):
        pytest.skip("supervisor requires Linux")
    request, sha = _case()
    victim = tmp_path / "victim.txt"
    victim.write_text("untouched")
    commands: list[list[str]] = []

    def fake(command, **_kw):
        commands.append(command)
        if len(commands) == 1:
            request_path = Path(next(a for a in command if a.endswith("request.json")))
            (request_path.parent / "proposal.json").symlink_to(victim)
            return b'{"bundle":{},"schema_version":1,"status":"proposal"}'
        return b'{"schema_version":1,"status":"invalid"}'

    monkeypatch.setattr(supervisor, "_run_capped", fake)
    result = supervisor.prove_separately_verified_miter_request(
        request, expected_source_sha256=sha)
    assert result["status"] == "invalid"
    assert victim.read_text() == "untouched"
    producer_dir = Path(next(a for a in commands[0] if a.endswith("request.json"))).parent
    verifier_paths = [a for a in commands[1] if a.endswith(".json")]
    assert verifier_paths and all(Path(p).parent != producer_dir for p in verifier_paths)


def test_both_bootstraps_disable_core_dumps():
    assert "RLIMIT_CORE,(0,0)" in isolated._BOOT
    assert "RLIMIT_CORE,(0,0)" in supervisor._VERIFY_BOOT


# --- process: the older API never signals a process group after reaping it -------

@pytest.mark.sat
@linux
def test_old_api_signals_the_group_only_while_the_leader_is_unreaped(monkeypatch):
    request, sha = _case()
    observed: list[bool] = []
    original = isolated._kill_group

    def checked(proc):
        try:  # WNOWAIT inspection: ChildProcessError means the leader was reaped.
            os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            observed.append(True)
        except ChildProcessError:
            observed.append(False)
        original(proc)

    monkeypatch.setattr(isolated, "_kill_group", checked)
    result = isolated.prove_isolated_miter_request(request, expected_source_sha256=sha)
    assert result["status"] == "proved"
    assert observed and all(observed)


# --- CNF budgets -----------------------------------------------------------------

def test_shared_wide_gate_is_refused_before_source_serialization(monkeypatch):
    import symq.labs.miter_cnf as module

    wide = Gate("mcx", tuple(range(1000)))
    left = Circuit(1000)
    left.gates.extend([wide] * 30_000)

    def trapped(*_args, **_kwargs):
        raise AssertionError("source was serialized before the size refusal")

    monkeypatch.setattr(module, "_canonical", trapped)
    monkeypatch.setattr(Circuit, "to_dict", trapped)
    with pytest.raises(ResourceLimitExceeded) as error:
        export_classical_miter_cnf(left, Circuit(1000))
    assert error.value.resource == "bytes"


def test_byte_refusal_reports_the_callers_total_cap():
    left, right = Circuit(3).ccx(0, 1, 2).cx(0, 1), Circuit(3)
    low, high = 1, 1 << 20
    while low < high:  # smallest total byte cap that is accepted
        middle = (low + high) // 2
        try:
            export_classical_miter_cnf(left, right, max_bytes=middle)
            high = middle
        except ResourceLimitExceeded:
            low = middle + 1
    with pytest.raises(ResourceLimitExceeded) as error:
        export_classical_miter_cnf(left, right, max_bytes=low - 1)
    assert error.value.resource == "bytes"
    assert error.value.limit == low - 1
    assert error.value.observed > low - 1


@pytest.mark.sat
def test_inherited_node_or_term_budget_is_inconclusive_not_an_exception():
    left = right = Circuit(1).x(0)
    produced = export_classical_miter_proof(left, right)
    assert produced["status"] == "proved"
    pin = export_classical_miter_cnf(left, right).source_sha256
    for budget in (Budget(max_terms=10**6), Budget(max_nodes=10**6)):
        with VerificationSession(budget):
            exported = export_classical_miter_proof(left, right)
            assert exported["status"] == "inconclusive"
            assert "inherited node/term budget" in exported["reason"]
            result = check_classical_miter_proof(
                left, right, None, produced["bundle"], expected_source_sha256=pin)
            assert result["status"] == "inconclusive"
            assert "inherited node/term budget" in result["reason"]
            assert not result["independent_unsat_checked"]
