"""Independent negative probes of SymQ research stack PR #106--#112.

Retrieved unchanged assertions from PR #113 at 1f24a81c19cd02da911407d27c73a6c734cb7ef4.
Strict xfail markers are removed. The IPC test strengthens its former skip:
rejected arbitrary objects must not reconstruct or execute in the parent.
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


def test_classical_blocks_do_not_consume_elapsed_seconds_twice(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    program = Circuit(1).x(0)
    with VerificationSession(Budget(max_seconds=10)):
        now[0] = 106.0
        result = check_equivalence_by_blocks(
            program, program, backend="sparse", budget=Budget(max_seconds=10)
        )
        assert result.equivalent


def test_transcript_within_parent_deadline_is_not_rejected(monkeypatch):
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
        candidate_sha256=transcript.digest(frozen),
        backend="sparse", budget=Budget(max_seconds=10),
    )
    assert proof.equivalent


def _slow_decode(path):
    Path(path).write_text("decoded in parent", encoding="utf-8")
    time.sleep(3.0)
    return "decoded"


class _DelayedValue:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return _slow_decode, (self.marker,)


def _return_delayed_value(marker):
    return _DelayedValue(marker)


def test_hard_wall_binds_parent_result_decoding(tmp_path):
    marker = tmp_path / "decoded.txt"
    started = time.perf_counter()
    outcome = run_isolated(
        _return_delayed_value, str(marker),
        limits=HardLimits(wall_seconds=2, memory_bytes=None),
    )
    elapsed = time.perf_counter() - started
    assert not marker.exists(), "worker objects must never reconstruct in the parent"
    assert outcome.status == "inconclusive"
    assert elapsed < 2.75, f"2s hard wall, but parent blocked for {elapsed:.3f}s"


@pytest.mark.parametrize("coefficient", (0, 8))
def test_zero_modular_phase_terms_are_discarded(coefficient):
    value = affine_event_factor({0b11: coefficient}, (0, 1), k=3)
    assert value == Cyclotomic.root(3)


def test_hybrid_inspection_matches_actual_width_admissibility():
    program = HybridProgram(7)
    contract = VerificationContract(backend="hybrid-exact")
    declared = inspect(program, program, contract=contract)
    actual = verify(program, program, contract)
    assert actual.outcome == "inconclusive"
    assert "width" in actual.reason
    assert not declared.supported


def test_affine_event_factor_unconditional_constant_is_one():
    assert affine_event_factor({}, (0, 1), k=3) == Cyclotomic.root(3)


def test_hybrid_oracle_within_width_cap_is_supported_and_equal():
    program = HybridProgram(1)
    contract = VerificationContract(backend="hybrid-exact")
    assert inspect(program, program, contract=contract).supported
    assert verify(program, program, contract).equivalent
