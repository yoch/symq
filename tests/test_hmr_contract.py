"""HMR validation and channel witnesses: the four defects #72 reports, fixed and guarded.

Each section reproduces a defect from issue #72 before asserting the corrected behaviour, so the
test fails on the old code for the reason the issue describes rather than by accident.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))

import channel
import factored

from symq.phase import (
    Op,
    PhaseProgram,
    UnsupportedOperation,
    check_phase_equivalence,
    phase_semantics,
)
from symq.phase_oracle import run_program

# --------------------------------------------------------------------- defect 1: hmr(None)


def test_a_raw_hmr_without_an_outcome_is_refused_before_interpretation():
    """``validate`` used to accept ``outcome=None``; ``phase_semantics`` then raised TypeError.

    The refusal must happen at validation, with a defined exception, and never as an accidental
    ``int + None``.
    """
    program = PhaseProgram(1, 0)
    program.ops.append(Op("hmr", (0,), None))
    with pytest.raises(UnsupportedOperation, match="explicit outcome index"):
        program.validate()
    with pytest.raises(UnsupportedOperation, match="explicit outcome index"):
        phase_semantics(program)


def test_the_builder_still_sets_the_index():
    """Backward compatibility: a builder-generated program is unchanged and still valid."""
    program = PhaseProgram(1, 0)
    index = program.hmr(0)
    assert index == 0
    assert program.ops[-1].outcome == 0
    program.validate()
    assert phase_semantics(program).measurements == 1


@pytest.mark.parametrize("outcome", [True, False, 1.0, "0", 0.5])
def test_non_integer_outcomes_are_refused(outcome):
    program = PhaseProgram(1, 0)
    program.ops.append(Op("hmr", (0,), outcome))
    with pytest.raises(UnsupportedOperation):
        program.validate()


@pytest.mark.parametrize("outcome", [-1, 1, 5])
def test_out_of_sequence_outcomes_are_refused(outcome):
    program = PhaseProgram(1, 0)
    program.ops.append(Op("hmr", (0,), outcome))
    with pytest.raises(UnsupportedOperation, match="not the next measurement"):
        program.validate()


@pytest.mark.parametrize("outcome", [True, False, 1.0, "0"])
def test_non_integer_feed_forward_outcomes_are_refused(outcome):
    program = PhaseProgram(2, 0)
    program.hmr(0)
    program.ops.append(Op("mcz_if", (1,), outcome))
    with pytest.raises(UnsupportedOperation):
        program.validate()


def test_a_feed_forward_on_a_future_measurement_is_refused():
    program = PhaseProgram(2, 0)
    program.hmr(0)
    program.ops.append(Op("mcz_if", (1,), 3))
    with pytest.raises(UnsupportedOperation, match="not an earlier measurement"):
        program.validate()


# ------------------------------------------------------- defect 2: the Z_8 documentation


def test_the_documented_fragment_is_sign_phase_only():
    """The module claimed ``Z_8`` arithmetic; implemented phases are ``(-1)`` exponents only.

    The assertion is on the docstring itself: a claim that contradicts the code is a defect even
    when the code is right, because a reader will design against the wrong fragment.
    """
    import symq.phase as phase_module

    doc = phase_module.__doc__ or ""
    assert "Z_8" not in doc and "Z₈" not in doc, "the Z_8 claim is back"
    assert "sign-phase" in doc.lower() or "sign phase" in doc.lower()


def test_phases_are_boolean_not_eighth_roots():
    """Every phase evaluates to 0 or 1, i.e. a sign, never a complex root of unity."""
    program = PhaseProgram(2, 1).ccx(0, 1, 2)
    program.hmr(2)
    semantics = phase_semantics(program)
    for assignment in range(1 << (program.data + program.measurements)):
        assert semantics.phase.evaluate(assignment) in (0, 1)


# ---------------------------------------- defect 3: channel witness coordinates with ancillas


def phase_difference_program(extra_phase: bool) -> PhaseProgram:
    """Two data wires, one ancilla, one non-constant measured syndrome ``g_0 = x0``."""
    program = PhaseProgram(2, 1)
    program.mcx(0, 2)
    program.hmr(2)
    if extra_phase:
        program.mcz(0, 1)
    return program


def test_the_witness_coordinates_are_valid_with_ancillas():
    """The witness used ``data + ancillas`` for the split instead of ``data``.

    With ``data = 2`` and one ancilla the old code returned ``(7, 0)`` for a valid range of
    ``0..3``: the x coordinate came from the wrong half of the pair space.
    """
    left, right = phase_difference_program(True), phase_difference_program(False)
    verdict = factored.equivalent_channel(left, right)
    assert not verdict.equivalent
    assert verdict.phase_witness is not None
    x, y = verdict.phase_witness
    assert 0 <= x < (1 << left.data), f"x={x} outside 0..{(1 << left.data) - 1}"
    assert 0 <= y < (1 << left.data), f"y={y} outside 0..{(1 << left.data) - 1}"


def test_the_witness_really_witnesses_the_channel_difference():
    """A coordinate in range is not enough: that coherence must actually differ under the oracle."""
    left, right = phase_difference_program(True), phase_difference_program(False)
    verdict = factored.equivalent_channel(left, right)
    x, y = verdict.phase_witness
    image_left = channel.coherence_image(left, x, y)
    image_right = channel.coherence_image(right, x, y)
    assert image_left != image_right, (
        f"the reported witness ({x}, {y}) does not separate the two channels")


def test_the_criterion_agrees_with_the_oracle_on_this_pair():
    left, right = phase_difference_program(True), phase_difference_program(False)
    assert factored.equivalent_channel(left, right).equivalent is False
    assert channel.same_channel(left, right) is False


def test_branch_equality_and_channel_equality_are_distinct_notions():
    """The strict criterion refuses a program that violates O2; the channel one may accept it.

    Comparing a program with *itself* is the cleanest demonstration: it is trivially equal at
    every branch level, yet the strict criterion reports an O2 violation because its phase depends
    on the outcome. The two predicates answer different questions and must not be conflated.
    """
    program = phase_difference_program(True)
    strict = check_phase_equivalence(program, program)
    assert strict.violations, "the strict criterion refuses a program whose phase depends on m"
    assert factored.equivalent_channel(program, program).equivalent, (
        "a program is trivially channel-equivalent to itself")
    assert channel.same_channel(program, program)


# --------------------------------------------------- defect 4: positive and negative outcomes


@pytest.mark.parametrize("outcome", [0, 1])
def test_every_outcome_of_a_positive_case_matches_the_oracle(outcome):
    """The accepted feedback program must agree with the state-vector oracle on both outcomes.

    ``run_program`` returns *unnormalised* integer amplitudes with the per-Hadamard ``1/sqrt 2``
    left out, so the comparison is ``±1`` against the sign the semantics predicts. The previous
    version compared against ``round(sign * 2**(M/2))``, which is nonsense as soon as ``M`` is odd:
    ``2**0.5`` is not an integer and rounding it hides the error.
    """
    program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    index = program.hmr(3)
    program.cz_if(index, 0, 1)
    specification = PhaseProgram(3, 1).ccx(0, 1, 2)
    semantics = phase_semantics(program)
    for x in range(1 << program.data):
        predicted = run_program(program, x, outcome)
        assignment = x | (outcome << program.data)
        basis = sum(value.evaluate(assignment) << wire
                    for wire, value in enumerate(semantics.outputs))
        expected_sign = -1 if semantics.phase.evaluate(assignment) else 1
        assert predicted == {basis: expected_sign}, (x, outcome, predicted)
    assert factored.equivalent_channel(program, specification).equivalent
    assert channel.same_channel(program, specification)


@pytest.mark.parametrize("measurements", [1, 2, 3])
def test_the_oracle_amplitudes_are_integers_with_several_measurements(measurements):
    """A case with several measurements, where the naive normalisation would round the wrong way."""
    program = PhaseProgram(2, 0)
    for _ in range(measurements):
        program.hmr(0)
    for outcome in range(1 << measurements):
        state = run_program(program, 0, outcome)
        assert state, "every outcome of this program keeps some amplitude"
        assert all(isinstance(value, int) for value in state.values()), (
            "run_program keeps integer amplitudes; no square root is ever approximated")


def test_a_wrong_phase_mutant_is_refused():
    """The negative control: omit the correction and the channel really differs."""
    program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    program.hmr(3)  # no correction at all
    specification = PhaseProgram(3, 1).ccx(0, 1, 2)
    assert not factored.equivalent_channel(program, specification).equivalent
    assert not channel.same_channel(program, specification)


def test_a_kernel_difference_is_reported_without_a_fabricated_witness():
    """Two programs with the *same* output functions but different syndromes.

    The previous version of this test used ``if verdict.kernel_differs:`` on a pair that also had
    different outputs, so the checker returned an output difference and the kernel branch was never
    exercised. Here the outputs are identical by construction and the ancilla is reset on both
    sides, so the only possible reason to differ is the syndrome kernel:

    * ``left`` measures an ancilla holding ``x0``, ``right`` measures one holding ``x1``;
    * both leave the data wires untouched and the ancilla at 0;
    * the kernels are ``[x0(x)=x0(y)]`` and ``[x1(x)=x1(y)]``, which are different relations.

    A kernel difference has no ``(x, y)`` witness yet -- the criterion can prove the kernels differ
    but cannot point at one pair -- so the verdict must say so rather than invent coordinates.
    """
    left = PhaseProgram(2, 1)
    left.mcx(0, 2)
    left.hmr(2)
    right = PhaseProgram(2, 1)
    right.mcx(1, 2)
    right.hmr(2)

    left_form, right_form = factored.factor(left), factored.factor(right)
    assert left_form.outputs == right_form.outputs, "the output functions must be identical"
    assert left_form.g != right_form.g, "the syndrome functions must differ"
    assert not left_form.unclean_ancillas() and not right_form.unclean_ancillas()

    verdict = factored.equivalent_channel(left, right)
    assert verdict.equivalent is False
    assert verdict.kernel_differs is True, "the failure must be attributed to the kernel"
    assert verdict.outputs_differ_on is None, "no output differs, so none may be blamed"
    assert verdict.phase_witness is None, "a kernel difference must not fabricate a witness"
    assert channel.same_channel(left, right) is False, "the oracle must confirm the difference"


def test_a_kernel_witness_is_never_invented_even_when_one_side_has_none():
    """Sanity: an agreeing-in-output pair with equal kernels *is* accepted, so the test above is sharp."""
    left = PhaseProgram(2, 1)
    left.mcx(0, 2)
    left.hmr(2)
    right = PhaseProgram(2, 1)
    right.mcx(0, 2)
    right.hmr(2)
    verdict = factored.equivalent_channel(left, right)
    assert verdict.equivalent is True
    assert channel.same_channel(left, right)


def test_the_phase_witness_is_checked_on_the_full_channel_too():
    """The witness must be a difference of the *full* channel, not only of the traced one.

    ``trace_ancillas`` defaults to ``True`` in ``coherence_image``, so a test that never passes
    ``False`` only checks the reduced channel. Both are checked here on the same witness.
    """
    left, right = phase_difference_program(True), phase_difference_program(False)
    verdict = factored.equivalent_channel(left, right)
    x, y = verdict.phase_witness
    full_left = channel.coherence_image(left, x, y, trace_ancillas=False)
    full_right = channel.coherence_image(right, x, y, trace_ancillas=False)
    traced_left = channel.coherence_image(left, x, y, trace_ancillas=True)
    traced_right = channel.coherence_image(right, x, y, trace_ancillas=True)
    assert full_left != full_right, "the witness must separate the full channels"
    assert traced_left != traced_right, "and the reduced ones"


def test_the_same_reduced_channel_can_hide_a_different_full_channel():
    """``cx(0,1)`` and ``cx(0,1); x(1)``: identical on the data wires, different on the ancilla.

    This is the case the audit asked for. A checker that only compares the traced channel would
    call these equivalent; the full comparison must not.
    """
    left = PhaseProgram(1, 1).cx(0, 1)
    right = PhaseProgram(1, 1).cx(0, 1).x(1)
    assert channel.same_channel(left, right, trace_ancillas=True), "the data channels agree"
    assert not channel.same_channel(left, right), "the full channels do not"
    # And the images differ in the ancilla part, which is what tracing would hide.
    full_left = channel.coherence_image(left, 0, 0, trace_ancillas=False)
    full_right = channel.coherence_image(right, 0, 0, trace_ancillas=False)
    assert full_left != full_right
    assert channel.coherence_image(left, 0, 0) == channel.coherence_image(right, 0, 0)


def test_the_oracle_comparison_is_external_not_an_api_guarantee():
    """``equivalent_channel`` returns a witness; it does **not** replay it by itself.

    The tests replay every witness against ``channel.py``, which is an independent implementation.
    That is a property of this test suite, not of the production API: a caller that trusts the
    verdict without replaying gets the criterion's word, not a checked certificate. The docstring
    and ``PILOT_A_CORRECTED.md`` say so; this test pins the distinction so it cannot be quietly
    upgraded to a claim.
    """
    import inspect

    source = inspect.getsource(factored.equivalent_channel)
    assert "channel" not in source.split("def ", 1)[0], (
        "the criterion must not import the oracle: replaying is the caller's job")
    left, right = phase_difference_program(True), phase_difference_program(False)
    verdict = factored.equivalent_channel(left, right)
    x, y = verdict.phase_witness
    assert channel.coherence_image(left, x, y) != channel.coherence_image(right, x, y)
