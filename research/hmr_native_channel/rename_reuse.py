"""Experiment: reuse the ``x`` half by an exact variable rename instead of recomputing ``y``.

## The observation

``check_full_channel`` builds four symbolic states: outputs and phase of each program on the ``x``
copy (variables ``0..n-1``) and again on the ``y`` copy (variables ``n..2n-1``). For one program the
two halves apply *the same gate list*; only the variable offset differs. Measured on the published
families, the two halves therefore have identical diagram shapes (125/117/124/118 nodes on the two
sides at 8 data / 70 HMR) and occupy disjoint node ids purely because the variables differ.

So the ``y`` half is a **renaming** of the ``x`` half: ``i -> i + n`` for data variables and
``i -> i - n`` for ancillas, a monotone map that preserves the diagram order.

## Why this is exact and not an approximation

A ZDD node is ``(level, lo, hi)``. Renaming replaces every ``level`` by the image level and re-interns
the pair, so the result denotes the polynomial obtained by substituting ``x_i -> x_{map(i)}`` in every
monomial. That is a syntactic identity on ANF, not a heuristic: the test suite compares the renamed
half against an independently recomputed half, node by node, on outputs, phase and every coefficient.

The map must be **strictly monotone** to keep the diagram ordered; otherwise a child could sit at a
lower level than its parent. ``rename`` therefore refuses a non-monotone map rather than producing a
malformed diagram.

## What this does and does not buy

* It removes one of the two full symbolic passes: the per-call cost on the dominant stage drops by
  the measured factor, and the node table roughly halves.
* It does **not** help the two programs against each other. ``left`` and ``right`` are different gate
  lists, so their halves are genuinely distinct diagrams; nothing is reused there.
* It does **not** raise the 32-data-bit ceiling. It reduces work per call at a fixed width.

Everything here is opt-in and under ``research/``. No production default changes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from research.hmr_native_channel.native_channel import (
    ChannelDecision,
    _kernel,
    _scalar,
    _scalar_kernel,
    _sha,
    _State,
    _symbolic,
    check_full_channel,
)
from symq.backends import make_algebra
from symq.resources import Budget, Guard


def shift_map(data: int) -> list[int]:
    """The ``x`` -> ``y`` variable map: data wires move up by ``data``, ancillas move down."""
    return list(range(data, 2 * data)) + list(range(data))


@dataclass
class RenameStats:
    rename_calls: int = 0
    renamed_nodes_examined: int = 0
    outputs_seconds: float = 0.0
    rename_seconds: float = 0.0
    kernel_seconds: float = 0.0
    phase_seconds: float = 0.0
    total_seconds: float = 0.0
    node_count: int = 0
    peak_terms: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _rename_state(algebra: Any, state: _State, mapping: list[int]) -> _State:
    manager = getattr(algebra, "manager", None)
    if manager is None:
        raise TypeError("the rename path requires the native backend (no manager on Python ZDD)")
    outputs = tuple(manager.rename(value, mapping) for value in state.outputs)
    phase0 = manager.rename(state.phase0, mapping)
    coefficients = tuple(manager.rename(value, mapping) for value in state.outcome_coefficients)
    return _State(outputs, phase0, coefficients)


def check_full_channel_renamed(
    left: Any,
    right: Any,
    *,
    backend: str = "zdd-native",
    budget: Budget | None = None,
    max_events: int = 10000,
    max_ops: int = 100000,
) -> tuple[ChannelDecision, RenameStats]:
    """``check_full_channel`` with the second half of each program obtained by exact renaming.

    The theorem, the checks and the witness replay are unchanged; only how the ``y`` states are
    obtained differs. The verdict is compared against ``check_full_channel`` by the caller.
    """
    from symq.resources import ResourceLimitExceeded

    stats = RenameStats()
    if backend != "zdd-native":
        raise ValueError("the rename path is native-only; use backend='zdd-native'")
    left.validate()
    right.validate()
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("data and ancilla widths must match for full-channel equality")
    if any(len(program.ops) > max_ops for program in (left, right)):
        raise ResourceLimitExceeded("ops", max_ops, max(len(left.ops), len(right.ops)))
    if any(program.measurements > max_events for program in (left, right)):
        raise ResourceLimitExceeded(
            "events", max_events, max(left.measurements, right.measurements)
        )
    if 2 * left.data > 64:
        raise ResourceLimitExceeded("native pair variables", 64, 2 * left.data)

    left_sha, right_sha = _sha(left), _sha(right)
    guard = Guard(budget)
    started = time.perf_counter()
    algebra = make_algebra(backend, 2 * left.data, budget)
    mapping = shift_map(left.data)

    outputs_started = time.perf_counter()
    lx = _symbolic(left, algebra, 0, guard)
    stats.outputs_seconds += time.perf_counter() - outputs_started
    outputs_started = time.perf_counter()
    rx = _symbolic(right, algebra, 0, guard)
    stats.outputs_seconds += time.perf_counter() - outputs_started

    rename_started = time.perf_counter()
    ly = _rename_state(algebra, lx, mapping)
    ry = _rename_state(algebra, rx, mapping)
    stats.rename_seconds += time.perf_counter() - rename_started
    stats.rename_calls = 4 + 2 * len(lx.outcome_coefficients) + 2 * len(rx.outcome_coefficients)
    stats.renamed_nodes_examined = stats.rename_calls

    mask = (1 << left.data) - 1

    def different(reason: str, kind: str, xy: tuple[int, int]) -> ChannelDecision:
        if _sha(left) != left_sha or _sha(right) != right_sha:
            raise RuntimeError("mutable input programs changed during verification")
        return ChannelDecision(
            False, backend, "full_quantum_channel", reason,
            left_sha, right_sha, left.measurements + right.measurements, kind, xy,
        )

    for wire, (a, b) in enumerate(zip(lx.outputs, rx.outputs)):
        difference = algebra.xor(a, b)
        if not algebra.is_zero(difference):
            witness = algebra.min_monomial(difference)
            if witness is None:
                raise RuntimeError("nonzero output difference has no witness")
            assignment = witness & mask
            if (_scalar(left, assignment)[0] >> wire & 1) == (
                _scalar(right, assignment)[0] >> wire & 1
            ):
                raise RuntimeError("native output witness fails independent integer replay")
            stats.total_seconds = time.perf_counter() - started
            stats.node_count = algebra.node_count
            return different(f"full output wire {wire} differs", "input", (assignment, assignment)), stats

    kernel_started = time.perf_counter()
    kl = _kernel(algebra, lx, ly, guard)
    kr = _kernel(algebra, rx, ry, guard)
    kernel_mismatch = algebra.xor(kl, kr)
    kernel_differs = not algebra.is_zero(kernel_mismatch)
    stats.kernel_seconds += time.perf_counter() - kernel_started
    if kernel_differs:
        witness = algebra.min_monomial(kernel_mismatch)
        if witness is None:
            raise RuntimeError("nonzero channel-kernel difference has no witness")
        x, y = witness & mask, (witness >> left.data) & mask
        if _scalar_kernel(left, x, y) == _scalar_kernel(right, x, y):
            raise RuntimeError("native kernel witness fails independent scalar replay")
        stats.total_seconds = time.perf_counter() - started
        stats.node_count = algebra.node_count
        return different("outcome-dephasing kernels differ", "coherence", (x, y)), stats

    phase_started = time.perf_counter()
    phase_x = algebra.xor(lx.phase0, rx.phase0)
    phase_y = algebra.xor(ly.phase0, ry.phase0)
    mismatch = algebra.product((kl, algebra.xor(phase_x, phase_y)))
    phase_differs = not algebra.is_zero(mismatch)
    stats.phase_seconds += time.perf_counter() - phase_started
    if phase_differs:
        witness = algebra.min_monomial(mismatch)
        if witness is None:
            raise RuntimeError("nonzero relative-phase difference has no witness")
        x, y = witness & mask, (witness >> left.data) & mask
        a = _scalar(left, x)[1] ^ _scalar(right, x)[1]
        b = _scalar(left, y)[1] ^ _scalar(right, y)[1]
        if (a == b or not _scalar_kernel(left, x, y) or not _scalar_kernel(right, x, y)):
            raise RuntimeError("native phase witness fails independent integer replay")
        stats.total_seconds = time.perf_counter() - started
        stats.node_count = algebra.node_count
        return different("relative phase differs on retained coherence", "coherence", (x, y)), stats

    if _sha(left) != left_sha or _sha(right) != right_sha:
        raise RuntimeError("mutable input programs changed during verification")
    stats.total_seconds = time.perf_counter() - started
    stats.node_count = algebra.node_count
    stats.peak_terms = getattr(algebra.stats, "peak_terms", None)
    return ChannelDecision(
        True, backend, "full_quantum_channel", "all basis coherences match",
        left_sha, right_sha, left.measurements + right.measurements,
    ), stats


def cross_check(left: Any, right: Any, *, budget: Budget | None = None) -> bool:
    """Both paths must agree on the verdict, or the experiment is void for that case."""
    reference = check_full_channel(left, right, backend="zdd-native", budget=budget)
    candidate, _stats = check_full_channel_renamed(left, right, budget=budget)
    return (
        reference.equivalent == candidate.equivalent
        and reference.reason == candidate.reason
        and reference.witness_kind == candidate.witness_kind
    )
