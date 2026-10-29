"""Independent physical witness-replay test for the corrected HMR block driver.

Pinned to PR #103. A pair of input basis states that both programs fully
dephase has ZERO channel image for both, even if the output permutations differ.
The global-witness replay helper must not declare this pair distinguishing.
"""
from __future__ import annotations

import pytest

from research.hmr_native_channel.blocks import channels_differ_at
from research.hmr_native_channel.native_channel import _scalar_kernel
from research.hybrid_channel.oracle import HybridProgram, coherence_image
from symq.phase import PhaseProgram


@pytest.mark.xfail(
    strict=True,
    reason="global witness replay returns True for both-zero channel images",
)
def test_dephased_coherence_cannot_be_a_channel_difference_witness() -> None:
    left = PhaseProgram(1, 1).cx(0, 1)
    left.hmr(1)
    right = PhaseProgram(1, 1).cx(0, 1)
    right.hmr(1)
    right.x(0)

    assert not _scalar_kernel(left, 0, 1)
    assert not _scalar_kernel(right, 0, 1)

    physical_left = HybridProgram(1, 1).cx(0, 1).hmr(1, "b0")
    physical_right = HybridProgram(1, 1).cx(0, 1).hmr(1, "b0").x(0)
    assert coherence_image(physical_left, 0, 1) == {}
    assert coherence_image(physical_right, 0, 1) == {}

    # A true witness must compare the actual channel images, not only F(x).
    # PR #103 helper compares F first and reports a difference incorrectly.
    assert channels_differ_at(left, right, 0, 1) is None


def test_the_diagonal_still_distinguishes_the_two_channels() -> None:
    left = PhaseProgram(1, 1).cx(0, 1)
    left.hmr(1)
    right = PhaseProgram(1, 1).cx(0, 1)
    right.hmr(1)
    right.x(0)
    assert channels_differ_at(left, right, 0, 0) is True
