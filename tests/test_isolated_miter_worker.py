"""Adversarial regression of the isolated, untrusted SAT proof producer."""
from __future__ import annotations

import json
import sys
import time

import pytest

import symq.labs.isolated_miter as isolated
from symq import Circuit
from symq.labs.lrat_rup import Limits
from symq.labs.miter_cnf import export_classical_miter_cnf
from symq.sat.encoding import Contract


def _request_and_pin(left: Circuit, right: Circuit,
                     contract: Contract | None = None) -> tuple[bytes, str]:
    request = isolated.make_isolated_miter_request(left, right, contract)
    cnf = export_classical_miter_cnf(left, right, contract)
    return request, cnf.source_sha256


@pytest.mark.sat
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS is qualified on Linux")
def test_valid_worker_proposes_but_only_parent_proves():
    left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    request, source_sha = _request_and_pin(left, Circuit(3))
    result = isolated.prove_isolated_miter_request(
        request, expected_source_sha256=source_sha,
        wall_seconds=12, memory_bytes=1073741824,
        limits=Limits(max_seconds=10),
    )
    assert result["status"] == "proved", result
    assert result["independent_unsat_checked"]
    assert result["source_recomputed"]
    assert result["hard_worker_limit"]
    assert not result["controlled_use_authorized"]


@pytest.mark.sat
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS is qualified on Linux")
def test_satisfiable_miter_and_wrong_source_pin_cannot_prove():
    left = Circuit(3).ccx(0, 1, 2)
    request, source_sha = _request_and_pin(left, Circuit(3))
    result = isolated.prove_isolated_miter_request(
        request, expected_source_sha256=source_sha,
        wall_seconds=12, memory_bytes=1073741824,
    )
    assert result["status"] != "proved" and not result["independent_unsat_checked"]

    request, source_sha = _request_and_pin(Circuit(1), Circuit(1))
    wrong = isolated.prove_isolated_miter_request(
        request, expected_source_sha256="0" * 64,
        wall_seconds=12, memory_bytes=1073741824,
    )
    assert wrong["status"] != "proved"
    assert not wrong["independent_unsat_checked"]


def test_strict_closed_canonical_request_schema_and_early_gate_limit():
    valid, _sha = _request_and_pin(Circuit(1), Circuit(1))
    assert isolated.parse_isolated_miter_request(valid)[0].width == 1
    for extra in (
        lambda x: x.update({"arbitrary_code": "os.system('exit')"}),
        lambda x: x["left"].update({"width": 1000000000}),
        lambda x: x["left"].update({"gates": [["x", [0]]] * 6000}),
        lambda x: x["contract"].update({"assumption": {"var": "x.0"}}),
    ):
        changed = json.loads(valid)
        extra(changed)
        data = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
        with pytest.raises(ValueError):
            isolated.parse_isolated_miter_request(data)
    bad = valid.replace(b'"schema_version":1', b'"schema_version":true')
    with pytest.raises(ValueError):
        isolated.parse_isolated_miter_request(bad)
    # Duplicate JSON object keys cannot shadow the trusted contract.
    with pytest.raises(ValueError, match="duplicate"):
        isolated.parse_isolated_miter_request(valid[:-1] + b',"kind":"shadow"}')


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="process group test uses Linux")
def test_timeout_kills_nonterminating_worker_group(monkeypatch):
    def sleeper(*_a, **_kw):
        return [sys.executable, "-I", "-c", "import time;time.sleep(60)"]

    monkeypatch.setattr(isolated, "_worker_command", sleeper)
    request, sha = _request_and_pin(Circuit(1), Circuit(1))
    started = time.monotonic()
    result = isolated.prove_isolated_miter_request(
        request, expected_source_sha256=sha, wall_seconds=0.2,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 4
    assert result["status"] == "inconclusive"
    assert not result["independent_unsat_checked"]
    assert "deadline" in result["reason"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="bounded pipes require Linux")
def test_stdout_flood_and_forged_worker_positive_are_refused(monkeypatch):
    request, sha = _request_and_pin(Circuit(1), Circuit(1))
    monkeypatch.setattr(
        isolated, "_worker_command",
        lambda *_a, **_kw: [
            sys.executable, "-I", "-c",
            "import sys;sys.stdout.write('X'*1000000)",
        ],
    )
    flood = isolated.prove_isolated_miter_request(
        request, expected_source_sha256=sha, wall_seconds=3,
        max_output_bytes=128,
    )
    assert flood["status"] == "inconclusive"
    assert not flood["independent_unsat_checked"]
    assert "stdout limit" in flood["reason"]

    forged = json.dumps(
        {"schema_version": 1, "status": "proposal", "bundle": {}},
        separators=(",", ":"),
    )
    monkeypatch.setattr(
        isolated, "_worker_command",
        lambda *_a, **_kw: [
            sys.executable, "-I", "-c",
            f"import sys;sys.stdout.write({forged!r})",
        ],
    )
    result = isolated.prove_isolated_miter_request(
        request, expected_source_sha256=sha, wall_seconds=3,
    )
    assert result["status"] != "proved"
    assert not result["independent_unsat_checked"]
    assert not result["controlled_use_authorized"]


def test_oversized_request_is_rejected_without_starting_worker(monkeypatch):
    def trap(*_a, **_kw):
        raise AssertionError("unbounded input must not launch a worker")

    monkeypatch.setattr(isolated, "_worker_command", trap)
    result = isolated.prove_isolated_miter_request(
        b"x" * 150000, expected_source_sha256="0" * 64,
    )
    if sys.platform.startswith("linux"):
        assert result["status"] == "invalid"
    else:
        assert result["status"] == "unsupported"
    assert not result["independent_unsat_checked"]


def test_other_platforms_refuse_linux_memory_claim(monkeypatch):
    with monkeypatch.context() as mp:
        mp.setattr(isolated.sys, "platform", "darwin")
        result = isolated.prove_isolated_miter_request(
            b"{}", expected_source_sha256="0" * 64,
        )
    assert result["status"] == "unsupported"
    assert not result["hard_worker_limit"]
    assert not result["independent_unsat_checked"]
