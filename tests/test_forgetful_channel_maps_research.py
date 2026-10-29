"""Physical forgetful-map regression tests for experimental proof-contract adapters.

All finite channels are evaluated on EVERY |x><y| basis matrix unit.
The tests intentionally use the merged, bounded hybrid CPTP oracle rather
than depending on unpublished API-contract branches.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product

from research.hybrid_channel.oracle import (
    HybridProgram,
    coherence_image,
    coherence_instrument,
    same_channel,
    same_instrument,
)


def _add(out: dict[tuple[int, int], Fraction], key: tuple[int, int], value: Fraction) -> None:
    new_value = out.get(key, Fraction(0)) + value
    if new_value:
        out[key] = new_value
    else:
        out.pop(key, None)


def _forget_classical(
    instrument: dict[tuple[int, ...], dict[tuple[int, int], Fraction]],
) -> dict[tuple[int, int], Fraction]:
    """Actually sum conditioned CP maps; do not merely relabel a theorem."""
    result: dict[tuple[int, int], Fraction] = {}
    for conditioned in instrument.values():
        for key, weight in conditioned.items():
            _add(result, key, weight)
    return result


def _trace_ancillas(
    full: dict[tuple[int, int], Fraction], data: int
) -> dict[tuple[int, int], Fraction]:
    """Independent partial trace of the data+ancilla output matrix."""
    mask = (1 << data) - 1
    result: dict[tuple[int, int], Fraction] = {}
    for (row, col), weight in full.items():
        if row >> data == col >> data:
            _add(result, (row & mask, col & mask), weight)
    return result


def test_different_full_channels_can_be_equal_after_partial_trace() -> None:
    """Counterexample: X on a clean ancilla changes full but not reduced output."""
    identity = HybridProgram(1, 1)
    ancilla_x = HybridProgram(1, 1).x(1)

    assert not same_channel(identity, ancilla_x).equivalent
    assert same_channel(identity, ancilla_x, trace_ancillas=True).equivalent

    for x, y in product(range(2), repeat=2):
        first = coherence_image(identity, x, y)
        second = coherence_image(ancilla_x, x, y)
        assert first != second, (x, y)
        assert _trace_ancillas(first, 1) == _trace_ancillas(second, 1)
        assert _trace_ancillas(first, 1) == coherence_image(
            identity, x, y, trace_ancillas=True
        )
        assert _trace_ancillas(second, 1) == coherence_image(
            ancilla_x, x, y, trace_ancillas=True
        )


def test_instrument_forgetting_explicitly_sums_all_conditioned_maps() -> None:
    """A different circuit with global NEG has identical observed CP instrument."""
    left = (
        HybridProgram(1, 1)
        .measure_z(0, "b0")
        .x(0, condition="b0")
        .store("b1", 1)
    )
    right = (
        HybridProgram(1, 1)
        .measure_z(0, "b0")
        .x(0, condition="b0")
        .store("b1", 1)
        .neg()
    )
    observed = ("b0", "b1")
    assert same_instrument(left, right, observed_slots=observed).equivalent
    assert same_channel(left, right).equivalent

    for trace in (False, True):
        assert same_instrument(
            left, right, observed_slots=observed, trace_ancillas=trace
        ).equivalent
        for program in (left, right):
            for x, y in product(range(2), repeat=2):
                conditioned = coherence_instrument(
                    program, x, y, observed_slots=observed, trace_ancillas=trace
                )
                assert _forget_classical(conditioned) == coherence_image(
                    program, x, y, trace_ancillas=trace
                )


def test_different_instruments_can_hide_the_same_channel() -> None:
    """Overwriting an observed slot changes its instrument, not the CP channel."""
    left = HybridProgram(1).measure_z(0, "b0").x(0, condition="b0")
    right = (
        HybridProgram(1).measure_z(0, "b0").x(0, condition="b0").store("b0", 0)
    )

    assert same_channel(left, right).equivalent
    assert not same_instrument(left, right, observed_slots=("b0",)).equivalent
    assert coherence_instrument(left, 1, 1, observed_slots=("b0",)) != (
        coherence_instrument(right, 1, 1, observed_slots=("b0",))
    )
    for x, y in product(range(2), repeat=2):
        for program in (left, right):
            assert _forget_classical(
                coherence_instrument(program, x, y, observed_slots=("b0",))
            ) == coherence_image(program, x, y)


def test_repaired_hmr_forgetting_matches_unitary_reference_on_all_coherences() -> None:
    """The corrected HMR instrument sums to the exact unitary MAC channel."""
    reference = HybridProgram(3, 1).ccx(0, 1, 2)
    corrected = (
        HybridProgram(3, 1)
        .ccx(0, 1, 3)
        .cx(3, 2)
        .hmr(3, "b0")
        .cz(0, 1, condition="b0")
    )
    raw = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0")
    assert same_channel(corrected, reference).equivalent
    assert same_channel(corrected, reference, trace_ancillas=True).equivalent
    assert not same_channel(raw, reference).equivalent

    for x, y in product(range(8), repeat=2):
        full = _forget_classical(
            coherence_instrument(corrected, x, y, observed_slots=("b0",))
        )
        assert full == coherence_image(reference, x, y)
        assert _trace_ancillas(full, 3) == coherence_image(
            reference, x, y, trace_ancillas=True
        )


def test_traced_instrument_equality_does_not_imply_full_channel_equality() -> None:
    """Critical counterexample to outcome-forgetting without trace metadata.

    Equal reduced instruments may encode different retained-ancilla
    quantum channels. A verdict-only ProofResult cannot infer FULL_QUANTUM_CHANNEL
    without knowing the output frame.
    """
    left = HybridProgram(1, 1).store("b0", 0)
    right = HybridProgram(1, 1).x(1).store("b0", 0)
    slots = ("b0",)
    assert same_instrument(left, right, observed_slots=slots, trace_ancillas=True).equivalent
    assert not same_instrument(left, right, observed_slots=slots, trace_ancillas=False).equivalent
    assert same_channel(left, right, trace_ancillas=True).equivalent
    assert not same_channel(left, right, trace_ancillas=False).equivalent
    for x, y in product(range(2), repeat=2):
        reduced_left = coherence_instrument(
            left, x, y, observed_slots=slots, trace_ancillas=True
        )
        reduced_right = coherence_instrument(
            right, x, y, observed_slots=slots, trace_ancillas=True
        )
        assert reduced_left == reduced_right
        assert _forget_classical(reduced_left) == coherence_image(
            left, x, y, trace_ancillas=True
        )
        assert _forget_classical(reduced_right) == coherence_image(
            right, x, y, trace_ancillas=True
        )
        assert coherence_image(left, x, y) != coherence_image(right, x, y)
