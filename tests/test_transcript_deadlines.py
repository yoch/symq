"""Deterministic whole-call deadlines through temporal proof obligations."""
from __future__ import annotations

import time

import pytest

from symq import Budget, Circuit, Gate, ResourceLimitExceeded
from symq.experimental import classical_transcript as transcript
from symq.experimental import composition, proof_graph
from symq.experimental.execution import HardLimits, IsolatedResult
from symq.experimental.hybrid import HOp, HybridProgram
from symq.resources import VerificationSession


def _clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(time, "perf_counter", lambda: now[0])
    return now


def _classical_check(left, right, steps, **kwargs):
    return transcript.verify_transcript(
        left, right, steps,
        reference_sha256=transcript.digest(transcript.Program.freeze(left)),
        candidate_sha256=transcript.digest(transcript.Program.freeze(right)),
        backend="sparse", **kwargs,
    )


@pytest.mark.parametrize("elapsed", (0.0, 6.0, 9.999))
def test_two_local_slots_inherit_one_absolute_deadline(monkeypatch, elapsed):
    now = _clock(monkeypatch)
    one = transcript.Program.freeze(Circuit(1).x(0))
    two = transcript.Program.freeze(Circuit(2).cx(0, 1))
    steps = (transcript.Slot(one, one, (0,)),
             transcript.Slot(two, two, (0, 1), preserved=(0,)),
             transcript.Common((Gate("x", (1,)),)))
    program = Circuit(2).x(0).cx(0, 1).x(1)
    original = transcript.check_equivalence
    children = []

    def local(*args, **kwargs):
        children.append(kwargs["budget"])
        return original(*args, **kwargs)

    monkeypatch.setattr(transcript, "check_equivalence", local)
    with VerificationSession(Budget(max_seconds=10, max_nodes=50, max_terms=20)):
        now[0] += elapsed
        result = _classical_check(program, program, steps,
                                  budget=Budget(max_seconds=10, max_nodes=30, max_terms=40))
        assert result.equivalent and result.unique_lemmas == 2
    assert len(children) == 2
    assert all(b.max_seconds is None and b.absolute_deadline == 110 for b in children)
    assert all(b.max_nodes == 30 and b.max_terms == 20 for b in children)


def test_validation_and_two_slots_do_not_shrink_remaining_time(monkeypatch):
    now = _clock(monkeypatch)
    one = transcript.Program.freeze(Circuit(1).x(0))
    two = transcript.Program.freeze(Circuit(2).cx(0, 1))
    program = Circuit(2).x(0).cx(0, 1)
    steps = (transcript.Slot(one, one, (0,)), transcript.Slot(two, two, (0, 1)))
    unfold, local = transcript._unfold, transcript.check_equivalence
    deadlines = []

    def validation(*args, **kwargs):
        result = unfold(*args, **kwargs)
        now[0] = 106.0
        return result

    def delayed_local(*args, **kwargs):
        deadlines.append(kwargs["budget"].absolute_deadline)
        result = local(*args, **kwargs)
        now[0] += 1.5
        return result

    monkeypatch.setattr(transcript, "_unfold", validation)
    monkeypatch.setattr(transcript, "check_equivalence", delayed_local)
    assert _classical_check(program, program, steps, budget=Budget(max_seconds=10)).equivalent
    assert now[0] == 109 and deadlines == [110, 110]


def test_late_local_witness_is_not_a_decisive_substitution_failure(monkeypatch):
    now = _clock(monkeypatch)
    left, right = Circuit(1).x(0), Circuit(1)
    slot = transcript.Slot(transcript.Program.freeze(left), transcript.Program.freeze(right), (0,))
    local = transcript.check_equivalence

    def late_witness(*args, **kwargs):
        result = local(*args, **kwargs)
        assert result.witness is not None
        now[0] = 110.0
        return result

    monkeypatch.setattr(transcript, "check_equivalence", late_witness)
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        _classical_check(left, right, (slot,), budget=Budget(max_seconds=10))


@pytest.mark.parametrize("restored", (True, False))
def test_preserved_wire_equality_obeys_final_deadline(monkeypatch, restored):
    now = _clock(monkeypatch)
    program = Circuit(1)
    frozen = transcript.Program.freeze(program)
    slot = transcript.Slot(frozen, frozen, (0,), preserved=(0,))
    factory = transcript.make_algebra

    def slow_algebra(*args, **kwargs):
        algebra = factory(*args, **kwargs)

        def slow_equal(left, right):
            now[0] = 110.0
            return restored

        algebra.equal = slow_equal
        return algebra

    monkeypatch.setattr(transcript, "make_algebra", slow_algebra)
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        _classical_check(program, program, (slot,), budget=Budget(max_seconds=10))


def _quantum_check(program, steps):
    return composition.verify_channel_transcript(
        program, program, steps,
        reference_sha256=composition.hybrid_digest(program),
        candidate_sha256=composition.hybrid_digest(program),
        budget=Budget(max_seconds=10),
    )


@pytest.mark.parametrize("preserved", (True, False))
def test_quantum_frame_obligation_cannot_complete_after_deadline(monkeypatch, preserved):
    now = _clock(monkeypatch)
    fragment = composition.HybridFragment(1, ())
    slot = composition.ChannelSlot(fragment, fragment, (0,), preserved=(0,))

    def slow_frame(*args):
        now[0] = 110.0
        return preserved

    monkeypatch.setattr(composition, "_identity_frame", slow_frame)
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        _quantum_check(HybridProgram(1), (slot,))


def test_quantum_common_suffix_remains_under_whole_call_deadline(monkeypatch):
    now = _clock(monkeypatch)
    fragment = composition.HybridFragment(1, ())
    suffix = (HOp("x", (0,)),)
    steps = (composition.ChannelSlot(fragment, fragment, (0,)), composition.HybridCommon(suffix))
    advance = composition._advance_known

    def slow_suffix(known, ops):
        advance(known, ops)
        if ops == suffix:
            now[0] = 110.0

    monkeypatch.setattr(composition, "_advance_known", slow_suffix)
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        _quantum_check(HybridProgram(1, ops=list(suffix)), steps)


def _graph():
    frozen = transcript.Program.freeze(Circuit(1))
    node = proof_graph.ProofNode("identity", proof_graph.ClassicalObligation(frozen, frozen))
    return proof_graph.ProofGraph((node,), "identity")


def test_graph_only_converts_to_relative_duration_at_spawn_boundary(monkeypatch):
    now = _clock(monkeypatch)
    budgets = []

    def isolated(function, obligation, backend, budget, *, limits, session):
        assert session.deadline == 110
        assert budget.absolute_deadline is None
        budgets.append(budget.max_seconds)
        # This test executes in the orchestration thread, where contextvars do
        # not carry the parent session; the worker starts a fresh local epoch.
        assert function(obligation, backend, budget)
        now[0] += 1.5
        return IsolatedResult("completed", "checked simulated spawned leaf", True)

    monkeypatch.setattr(proof_graph, "run_isolated", isolated)
    with VerificationSession(Budget(max_seconds=10)):
        now[0] = 106.0
        assert proof_graph.ProofKernel().verify(
            _graph(), budget=Budget(max_seconds=10), independent=True,
            limits=HardLimits(wall_seconds=10, memory_bytes=None),
        ).accepted
    assert budgets == [4, 2.5] and now[0] == 109


def test_graph_late_leaf_never_enters_success_cache(monkeypatch):
    now = _clock(monkeypatch)

    def isolated(*args, **kwargs):
        now[0] = 110.0
        return IsolatedResult("completed", "late worker", True)

    monkeypatch.setattr(proof_graph, "run_isolated", isolated)
    kernel = proof_graph.ProofKernel()
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        kernel.verify(_graph(), budget=Budget(max_seconds=10), independent=True,
                      limits=HardLimits(wall_seconds=10, memory_bytes=None))
    assert not kernel._verified
