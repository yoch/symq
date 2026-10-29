"""Differential tests for C/ZDD-native factored HMR full quantum channels."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

from research.hmr_native_channel.native_channel import check_full_channel
from symq import Budget, PhaseProgram, ResourceLimitExceeded
from symq.backends import has_native

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import channel
import factored


def random_program(rng: random.Random, data: int, ancillas: int) -> PhaseProgram:
    program = PhaseProgram(data, ancillas)
    for _ in range(rng.randint(1, 8)):
        gate = rng.choice(("mcx", "mcx", "mcz", "hmr", "mcz_if"))
        if gate == "hmr":
            program.hmr(rng.randrange(program.width))
            continue
        count = rng.randint(1, min(3, program.width))
        qubits = rng.sample(range(program.width), count)
        if gate == "mcz_if" and program.measurements:
            program.mcz_if(rng.randrange(program.measurements), *qubits)
        elif gate == "mcx":
            program.mcx(*qubits)
        else:
            program.mcz(*qubits)
    return program


@pytest.mark.parametrize("seed", range(80))
def test_zdd_channel_matches_independent_kraus_density_and_factored_reference(seed):
    rng = random.Random(17 + seed)
    data = rng.randint(1, 2)
    ancillas = rng.randint(0, 1)
    left = random_program(rng, data, ancillas)
    right = left if seed % 7 == 0 else random_program(rng, data, ancillas)
    expected = channel.same_channel(left, right)
    assert factored.equivalent_channel(left, right).equivalent == expected
    verdict = check_full_channel(left, right, backend="zdd")
    assert verdict.equivalent == expected
    assert verdict.theorem == "full_quantum_channel"
    if not verdict.equivalent:
        assert verdict.witness is not None
        if verdict.witness_kind == "input":
            assert verdict.witness[0] == verdict.witness[1]
        else:
            assert verdict.witness_kind == "coherence"
    if has_native():
        native = check_full_channel(left, right, backend="zdd-native")
        assert native.equivalent == expected
        assert native.witness_kind == verdict.witness_kind


def test_hmr_compute_and_feedback_corrected_and_uncorrected():
    p = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    m = p.hmr(3)
    p.cz_if(m, 0, 1)
    ref = PhaseProgram(3, 1).ccx(0, 1, 2)
    assert check_full_channel(p, ref, backend="zdd").equivalent
    p.ops.pop()
    verdict = check_full_channel(p, ref, backend="zdd")
    assert not verdict.equivalent
    assert verdict.witness_kind == "coherence"
    if has_native():
        assert not check_full_channel(p, ref, backend="zdd-native").equivalent


def test_global_measurement_sign_is_physical_channel_equivalent():
    a = PhaseProgram(2, 1).x(2)
    a.hmr(2)
    b = PhaseProgram(2, 1)
    assert check_full_channel(a, b, backend="zdd").equivalent
    assert channel.same_channel(a, b)
    if has_native():
        assert check_full_channel(a, b, backend="zdd-native").equivalent


def test_over_hundred_fresh_hmr_events_without_2_power_m_expansion():
    p = PhaseProgram(5, 1)
    for index in range(130):
        p.cx(index % 5, 5)
        event = p.hmr(5)
        p.z_if(event, index % 5)
    ref = PhaseProgram(5, 1)
    verdict = check_full_channel(p, ref, backend="zdd")
    assert verdict.equivalent and verdict.checked_events == 130
    if has_native():
        native = check_full_channel(p, ref, backend="zdd-native")
        assert native.equivalent and native.checked_events == 130


def test_native_pair_width_guard_and_no_implicit_fallback():
    p = PhaseProgram(33)
    with pytest.raises(ResourceLimitExceeded, match="native pair"):
        check_full_channel(p, p, backend="zdd-native")
    with pytest.raises(ValueError, match="explicit"):
        check_full_channel(PhaseProgram(1), PhaseProgram(1), backend="sparse")
    with pytest.raises(ResourceLimitExceeded, match="events"):
        many = PhaseProgram(1)
        for _ in range(5):
            many.hmr(0)
        check_full_channel(many, PhaseProgram(1), backend="zdd", max_events=2)


def test_refuses_other_semantics_and_exhausted_budget():
    p = PhaseProgram(2)
    p.ops.append("reset")
    with pytest.raises(ValueError):
        check_full_channel(p, p, backend="zdd")
    p.ops.pop()
    with pytest.raises(ResourceLimitExceeded):
        check_full_channel(p, p, backend="zdd", budget=Budget(max_seconds=1e-12))
    with pytest.raises(ValueError):
        check_full_channel(p, PhaseProgram(2, 1), backend="zdd")
