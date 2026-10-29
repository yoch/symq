"""Independent adversarial reproductions against research PR #103.

This branch is isolated from the agent's owned PR. Expected failures are
marked strict xfail, documenting *existing* defects on the pinned HEAD.
Remove xfail and make them pass when fixing the source under review.
"""
from __future__ import annotations

import pytest

from research.hmr_native_channel.blocks import decompose_decision
from research.hmr_native_channel.native_channel import _scalar, check_full_channel
from symq.backends import make_algebra
from symq.phase import PhaseProgram
from symq.resources import Budget


@pytest.mark.xfail(strict=True, reason="P0: data-less ancilla-only quantum factor is discarded")
def test_ancilla_only_x_must_not_be_mistaken_for_full_channel_equality():
    left = PhaseProgram(1, 1)
    right = PhaseProgram(1, 1).x(1)
    assert not check_full_channel(left, right, backend="zdd").equivalent
    decision, _ = decompose_decision(left, right, backend="zdd")
    assert not decision.equivalent, "ancilla-only X was dropped by decomposition"


@pytest.mark.xfail(strict=True, reason="P1: global outcome identities require local reindexing")
def test_two_disjoint_hmr_components_are_still_a_valid_identical_program():
    program = PhaseProgram(2)
    assert program.hmr(0) == 0
    assert program.hmr(1) == 1
    assert check_full_channel(program, program, backend="zdd").equivalent
    decision, _ = decompose_decision(program, program, backend="zdd")
    assert decision.equivalent


@pytest.mark.xfail(strict=True, reason="P1: local witnesses must be embedded in global data coordinates")
def test_block_phase_witness_replays_against_original_global_pair():
    left = PhaseProgram(2)
    right = PhaseProgram(2).z(1)
    decision, _ = decompose_decision(left, right, backend="zdd")
    assert not decision.equivalent
    assert decision.witness_kind == "coherence"
    assert decision.witness is not None
    x, y = decision.witness
    assert 0 <= x < 4 and 0 <= y < 4
    left_relative = _scalar(left, x)[1] ^ _scalar(left, y)[1]
    right_relative = _scalar(right, x)[1] ^ _scalar(right, y)[1]
    assert left_relative != right_relative, (
        f"reported witness {(x, y)} does not distinguish the global programs"
    )


@pytest.mark.xfail(strict=True, reason="P0: rename accepts non-injective map that breaks canonical ZDD representation")
def test_native_rename_must_reject_duplicate_variable_images_or_normalize_boolean_anf():
    algebra = make_algebra("zdd-native", 4, Budget(max_seconds=5))
    x0, x1 = algebra.variable(0), algebra.variable(1)
    source = algebra.product((x0, x1))
    renamed = algebra.manager.rename(source, [1, 1, 2, 3])
    assert algebra.to_anf(renamed) == algebra.to_anf(x1)
    assert algebra.equal(renamed, x1), (
        "the same Boolean ANF now has different supposedly canonical ZDD handles"
    )
