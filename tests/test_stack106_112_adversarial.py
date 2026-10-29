"""Independent source-pinned audit of stack #106--#112.

Strict xfails reproduce observed defects, not accepted correctness.
Remove xfail and require normal PASS when fixing the reviewed source.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from symq import Budget, Circuit
from symq.equivalence import check_equivalence_by_blocks
from symq.experimental import VerificationContract, inspect, verify
from symq.experimental import classical_transcript as transcript
from symq.experimental.cyclotomic import Cyclotomic, affine_event_factor
from symq.experimental.execution import HardLimits, run_isolated
from symq.experimental.hybrid import HybridProgram
from symq.resources import VerificationSession


@pytest.mark.xfail(strict=True, reason="P1: remaining duration is subtracted twice under an active session")
def test_classical_blocks_keep_the_absolute_parent_deadline(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    program = Circuit(1).x(0)
    with VerificationSession(Budget(max_seconds=10)):
        now[0] = 106.0
        proof = check_equivalence_by_blocks(program, program, backend="sparse",
                                             budget=Budget(max_seconds=10))
        assert proof.equivalent


@pytest.mark.xfail(strict=True, reason="P1: transcript remaining budget is re-anchored at parent start")
def test_temporal_transcript_does_not_consume_elapsed_time_twice(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    program = Circuit(1).x(0)
    frozen = transcript.Program.freeze(program)
    original_unfold = transcript._unfold

    def delayed_unfold(*args, **kwargs):
        result = original_unfold(*args, **kwargs)
        now[0] = 106.0
        return result

    monkeypatch.setattr(transcript, "_unfold", delayed_unfold)
    proof = transcript.verify_transcript(
        program, program, [transcript.Slot(frozen, frozen, (0,))],
        reference_sha256=transcript.digest(frozen),
        candidate_sha256=transcript.digest(frozen), backend="sparse",
        budget=Budget(max_seconds=10),
    )
    assert proof.equivalent


def _reconstruct_value(marker: str):
    Path(marker).write_text("parent decoded returned value", encoding="utf-8")
    time.sleep(3.0)
    return "decoded"


class _DelayedDecodedValue:
    def __init__(self, marker: str):
        self.marker = marker

    def __reduce__(self):
        return _reconstruct_value, (self.marker,)


def _return_delayed_value(marker: str):
    return _DelayedDecodedValue(marker)


@pytest.mark.xfail(strict=True, reason="P1: blocking parent recv/unpickle escapes hard wall limit")
def test_hard_wall_includes_receiving_and_decoding_worker_result(tmp_path):
    marker = tmp_path / "decoded.txt"
    started = time.perf_counter()
    result = run_isolated(_return_delayed_value, str(marker),
                          limits=HardLimits(wall_seconds=2, memory_bytes=None))
    elapsed = time.perf_counter() - started
    if not marker.exists():
        pytest.skip("worker did not deliver before deadline; decoding path not exercised")
    assert result.status == "inconclusive"
    assert elapsed < 2.75, f"hard wall=2s, actual={elapsed:.3f}s: parent decoding is unbounded"


@pytest.mark.parametrize("coefficient", (0, 8))
@pytest.mark.xfail(strict=True, reason="P2: zero modulo 8 nonlinear event term raises KeyError")
def test_affine_event_factor_discards_modular_zero_terms(coefficient):
    actual = affine_event_factor({0b11: coefficient}, (0, 1), k=3)
    assert actual == Cyclotomic.root(3)


@pytest.mark.xfail(strict=True, reason="P2: inspect hides fixed hybrid-exact width cap")
def test_capability_inspection_discloses_fixed_hybrid_width_cap():
    program = HybridProgram(7)
    contract = VerificationContract(backend="hybrid-exact")
    capability = inspect(program, program, contract=contract)
    decision = verify(program, program, contract)
    assert decision.outcome == "inconclusive" and "width" in decision.reason
    assert not capability.supported


def test_affine_constant_control_really_equals_one():
    assert affine_event_factor({}, (0, 1), k=3) == Cyclotomic.root(3)


def test_hybrid_within_width_cap_remains_admissible_and_equal():
    program = HybridProgram(1)
    contract = VerificationContract(backend="hybrid-exact")
    assert inspect(program, program, contract=contract).supported
    assert verify(program, program, contract).equivalent
