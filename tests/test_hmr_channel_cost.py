"""Regression tests for the HMR channel cost study, exact renaming and block decomposition.

Every numerical claim in the delivery is produced by these modules, so the tests pin the two things
that could silently invalidate them:

* the instrumented and renamed paths must return the **same verdict** as ``check_full_channel``;
* the block decomposition must agree with the monolithic Python check, including on wide programs
  where only the decomposition can run natively.
"""
from __future__ import annotations

import pytest

from research.hmr_native_channel.benchmark import case as family
from research.hmr_native_channel.blocks import (
    Component,
    components,
    decompose_decision,
    join_partition,
    restrict,
)
from research.hmr_native_channel.native_channel import (
    _scalar,
    check_full_channel,
)
from research.hmr_native_channel.profile import cases as profile_cases
from research.hmr_native_channel.profile import profile_channel
from research.hmr_native_channel.rename_reuse import (
    check_full_channel_renamed,
    cross_check,
    shift_map,
)
from research.hmr_native_channel.width_study import (
    NATIVE_MAX_DATA,
    ancilla_locality,
    probe_widths,
)
from symq.backends import has_native, make_algebra
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded


def has_native_backend() -> bool:
    return has_native()


needs_native = pytest.mark.skipif(
    not has_native_backend(), reason="the native C core is not built in this environment"
)


def _budget(seconds: float = 240.0) -> Budget:
    return Budget(max_seconds=seconds)


# ------------------------------------------------------------------ the six profile stages


def test_profile_matches_the_reference_verdict_on_all_seven_comparison_kinds():
    observed = {}
    for name, (left, right) in profile_cases().items():
        profile = profile_channel(left, right, backend="zdd", budget=_budget())
        assert profile.matched, (name, profile.expected, profile.observed)
        observed[name] = profile.observed
    assert observed["identical"] == "equivalent"
    assert observed["equivalent_other"] == "equivalent"
    assert observed["output_difference"].startswith("output_difference")
    assert observed["kernel_difference"] == "kernel_difference"
    assert observed["phase_difference"] == "phase_difference"
    assert observed["repaired"] == "equivalent"
    assert observed["unrepaired"] != "equivalent"


def test_profile_attributes_the_dominant_cost_to_the_output_functions():
    """The published families spend their time building ``F(x)`` and ``F(y)``, not phases."""
    left, right = family(8, 70, "nonlinear")
    profile = profile_channel(left, right, backend="zdd", budget=_budget())
    stages = profile.stages
    symbolic = stages.outputs_x + stages.outputs_y
    assert symbolic > 0.9 * stages.total, (
        f"outputs {symbolic:.4f}s of {stages.total:.4f}s"
    )
    assert stages.phase0_x + stages.phase0_y < 0.05 * stages.total
    assert profile.work.zero_phase_final is True
    assert profile.work.zero_coefficients_final is True


def test_the_timed_families_have_a_trivial_kernel_and_the_nonlinear_one_moves_data():
    for family_name, data, hmr in (("affine", 8, 4), ("nonlinear", 6, 3)):
        program, reference = family(data, hmr, family_name)
        mask = (1 << data) - 1
        moved = False
        for assignment in range(1 << data):
            bits, phase, coefficients = _scalar(program, assignment)
            ref_bits, ref_phase, ref_coefficients = _scalar(reference, assignment)
            assert phase == 0 and ref_phase == 0
            assert coefficients == tuple(0 for _ in coefficients)
            assert ref_coefficients == ()
            assert bits == ref_bits
            moved |= (bits & mask) != assignment
        assert moved is (family_name == "nonlinear")


# --------------------------------------------------------------------- exact variable renaming


@needs_native
def test_rename_is_an_exact_anf_substitution():
    algebra = make_algebra("zdd-native", 4, _budget())
    x0, x1 = algebra.variable(0), algebra.variable(1)
    y0, y1 = algebra.variable(2), algebra.variable(3)
    source = algebra.xor(algebra.product([x0, x1]), x1)
    expected = algebra.xor(algebra.product([y0, y1]), y1)
    renamed = algebra.manager.rename(source, shift_map(2))
    assert algebra.to_anf(renamed) == algebra.to_anf(expected)
    assert algebra.equal(renamed, expected)


@needs_native
def test_rename_identity_and_error_paths():
    algebra = make_algebra("zdd-native", 4, _budget())
    value = algebra.product([algebra.variable(0), algebra.variable(1)])
    assert algebra.manager.rename(value, [0, 1, 2, 3]) == value
    with pytest.raises(ValueError, match="one entry per variable"):
        algebra.manager.rename(value, [0, 1])
    with pytest.raises(ValueError, match="outside algebra width"):
        algebra.manager.rename(value, [0, 1, 2, 9])
    with pytest.raises(ValueError, match="outside this manager"):
        algebra.manager.rename(10_000, [0, 1, 2, 3])


@needs_native
def test_renamed_second_half_equals_the_recomputed_one():
    """The reuse is only legitimate if the renamed y state is literally the recomputed one."""
    from research.hmr_native_channel.native_channel import _State

    left, _right = family(8, 30, "nonlinear")
    algebra = make_algebra("zdd-native", 2 * left.data, _budget())
    lx = _symbolic_into(left, algebra, 0)
    ly = _symbolic_into(left, algebra, left.data)
    mapping = shift_map(left.data)
    renamed = _State(
        tuple(algebra.manager.rename(v, mapping) for v in lx.outputs),
        algebra.manager.rename(lx.phase0, mapping),
        tuple(algebra.manager.rename(c, mapping) for c in lx.outcome_coefficients),
    )
    assert all(algebra.equal(a, b) for a, b in zip(renamed.outputs, ly.outputs))
    assert algebra.equal(renamed.phase0, ly.phase0)
    assert all(
        algebra.equal(a, b)
        for a, b in zip(renamed.outcome_coefficients, ly.outcome_coefficients)
    )


def _symbolic_into(program: PhaseProgram, algebra, offset: int):
    from research.hmr_native_channel.native_channel import _symbolic
    from symq.resources import Guard

    return _symbolic(program, algebra, offset, Guard(_budget()))


@needs_native
def test_renamed_path_agrees_with_the_reference_on_every_comparison_kind():
    for name, (left, right) in profile_cases().items():
        assert cross_check(left, right, budget=_budget()), name
    for family_name, data, hmr in (
        ("affine", 8, 130),
        ("nonlinear", 8, 70),
        ("nonlinear", 12, 25),
    ):
        left, right = family(data, hmr, family_name)
        assert cross_check(left, right, budget=_budget()), (family_name, data, hmr)


@needs_native
def test_renamed_path_reports_its_own_stage_cost():
    left, right = family(8, 70, "nonlinear")
    decision, stats = check_full_channel_renamed(left, right, budget=_budget())
    assert decision.equivalent
    assert stats.rename_seconds >= 0.0
    assert stats.outputs_seconds > 0.0
    hmr_events = len([op for op in left.ops if op.kind == "hmr"])
    expected_calls = 4 + 2 * hmr_events  # two outputs, one phase0 plus one coefficient per event
    assert stats.rename_calls == expected_calls


def test_renamed_path_refuses_a_non_native_backend():
    left, right = family(6, 4, "nonlinear")
    with pytest.raises(ValueError, match="native-only"):
        check_full_channel_renamed(left, right, backend="zdd", budget=_budget())


# ------------------------------------------------------------------ block decomposition


def test_components_are_disjoint_and_cover_every_wire():
    left, _right = family(36, 8, "nonlinear")
    parts = components(left)
    seen: set[int] = set()
    for part in parts:
        wires = set(part.data_wires) | set(part.ancilla_wires)
        assert not (seen & wires), "components must be disjoint"
        seen |= wires
    assert seen == set(range(left.width))


def test_join_partition_is_a_refinement_of_both_programs():
    left, right = family(36, 8, "nonlinear")
    blocks = join_partition(left, right)
    for program in (left, right):
        for component in components(program):
            for wire in component.data_wires:
                holders = [block for block in blocks if wire in block]
                assert len(holders) == 1
                assert set(component.data_wires) <= set(holders[0])
    covered = {wire for block in blocks for wire in block}
    assert covered == set(range(left.data))


@needs_native
def test_restrict_drops_other_blocks_and_refuses_a_crossing_operation():
    left, _right = family(36, 8, "nonlinear")
    block = max(join_partition(left, left), key=len)
    ancillas = tuple(
        wire
        for component in components(left)
        if set(component.data_wires) <= set(block)
        for wire in component.ancilla_wires
    )
    sub = restrict(left, Component(data_wires=block, ancilla_wires=ancillas))
    assert sub.data == len(block)
    assert sub.width <= left.width
    for op in sub.ops:
        assert all(0 <= q < sub.width for q in op.qubits)
    # A block that omits a wire one op uses is not a tensor factor: refuse, do not renumber blindly.
    partial = Component(data_wires=block[1:], ancilla_wires=())
    with pytest.raises(ValueError, match="crosses the block boundary"):
        restrict(left, partial)


@needs_native
def test_decomposition_decides_thirty_six_and_forty_data_wires_natively():
    """Beyond the 32-data-wire ceiling, and with the same verdict as the Python reference."""
    for data in (36, 40):
        left, right = family(data, 8, "nonlinear")
        with pytest.raises(ResourceLimitExceeded):
            check_full_channel(left, right, budget=_budget())
        decision, stats = decompose_decision(left, right, budget=_budget())
        reference = check_full_channel(left, right, backend="zdd", budget=_budget())
        assert decision.equivalent is True
        assert decision.equivalent == reference.equivalent
        assert stats.widest_data_component <= NATIVE_MAX_DATA
        assert stats.components > 1


@needs_native
def test_decomposition_detects_a_broken_wide_program():
    left, right = family(36, 6, "nonlinear")
    broken = PhaseProgram(right.data, right.ancillas)
    broken.ops = list(right.ops[:-1])
    decision, _stats = decompose_decision(left, broken, budget=_budget())
    reference = check_full_channel(left, broken, backend="zdd", budget=_budget())
    assert decision.equivalent is False
    assert reference.equivalent is False
    assert decision.witness is not None or decision.witness_kind is not None


@needs_native
def test_decomposition_and_monolithic_agree_on_wide_mutants():
    left, right = family(36, 6, "nonlinear")
    for drop in (0, 2, 4):
        mutant = PhaseProgram(right.data, right.ancillas)
        mutant.ops = [op for index, op in enumerate(right.ops) if index != drop]
        decomposed, _stats = decompose_decision(left, mutant, budget=_budget())
        monolithic = check_full_channel(left, mutant, backend="zdd", budget=_budget())
        assert decomposed.equivalent == monolithic.equivalent, drop


def test_decomposition_refuses_a_component_that_is_still_too_wide(monkeypatch):
    """A block above the ceiling must raise, never be skipped and reported as equal."""
    left, right = family(8, 4, "nonlinear")
    monkeypatch.setattr(
        "research.hmr_native_channel.blocks.NATIVE_MAX_DATA", 2, raising=True
    )
    with pytest.raises(ResourceLimitExceeded):
        decompose_decision(left, right, budget=_budget())


# ------------------------------------------------------------------------- width boundary


def test_the_native_ceiling_is_exactly_32_data_wires():
    assert NATIVE_MAX_DATA == 32
    rows = probe_widths(widths=(31, 32, 33), hmr=8)
    native = {row.data: row.outcome for row in rows if row.backend == "zdd-native"}
    python = {row.data: row.outcome for row in rows if row.backend == "zdd"}
    assert native[31] == "equivalent"
    assert native[32] == "equivalent"
    assert native[33] == "resource_limit"
    assert python[33] == "equivalent", "the pure-Python backend must keep deciding"


def test_locality_reports_the_widest_connected_component():
    wide = family(36, 8, "nonlinear")[0]
    narrow = family(8, 4, "nonlinear")[0]
    wide_report = ancilla_locality(wide)
    narrow_report = ancilla_locality(narrow)
    assert wide_report.widest_local_block >= narrow_report.widest_local_block
    assert wide_report.reads_per_ancilla
    assert wide_report.factorable is True
    assert "block ceiling" in wide_report.detail


def test_an_op_outside_the_grammar_is_refused_by_the_decomposition_driver():
    left, right = family(8, 4, "nonlinear")
    forged = PhaseProgram(right.data, right.ancillas)
    forged.ops = [Op("cx", (0, 1)), Op("cx", (0, 1))]  # 'cx' is not in the sign/HMR grammar
    with pytest.raises(Exception):  # noqa: B017 - UnsupportedOperation, from validate()
        decompose_decision(left, forged, budget=_budget())
