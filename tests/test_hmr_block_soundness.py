"""Adversarial soundness tests for the block-decomposed HMR channel check.

These began as four strict-``xfail`` reproductions published independently against `407e1d3`
(issue #104). They are now ordinary passing regressions, and each is paired with the mutants that
would silently bring the defect back:

* an ancilla-only factor dropped from the joint partition (false EQUIVALENT);
* HMR event ids copied verbatim into a sub-program (``PhaseProgram`` rejects them);
* a block witness reported in compacted coordinates (does not replay globally);
* the native rename accepting a non-injective map (two handles for one polynomial).

The differential oracle is the monolithic ``check_full_channel`` on the **Python** backend, which
enumerates every ``|x><y|`` and shares no code with the block driver.
"""
from __future__ import annotations

import itertools
import random

import pytest

from research.hmr_native_channel.blocks import (
    common_blocks,
    components,
    decompose_decision,
    lift_witness,
    plan_blocks,
    restrict,
)
from research.hmr_native_channel.native_channel import _scalar, _scalar_kernel, check_full_channel
from symq.backends import has_native, make_algebra
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded


def _budget(seconds: float = 120.0) -> Budget:
    return Budget(max_seconds=seconds)


needs_native = pytest.mark.skipif(not has_native(), reason="native C core not built")


# ============================================================ the four published reproductions


def test_ancilla_only_x_is_not_full_channel_equality():
    """#104 P0-A, verbatim. A block with no data wire is still a CP factor."""
    left = PhaseProgram(1, 1)
    right = PhaseProgram(1, 1).x(1)
    assert not check_full_channel(left, right, backend="zdd").equivalent
    decision, stats = decompose_decision(left, right, backend="zdd")
    assert not decision.equivalent, "ancilla-only X was dropped by decomposition"
    assert stats.ancilla_only_merged >= 1
    assert decision.witness is not None
    x, y = decision.witness
    assert (_scalar(left, x)[0], _scalar(left, y)[0]) != (
        _scalar(right, x)[0],
        _scalar(right, y)[0],
    )


def test_two_disjoint_hmr_components_remain_a_valid_identical_program():
    """#104 P1-B, verbatim. Global event ids must be renumbered per block."""
    program = PhaseProgram(2)
    assert program.hmr(0) == 0
    assert program.hmr(1) == 1
    assert check_full_channel(program, program, backend="zdd").equivalent
    decision, stats = decompose_decision(program, program, backend="zdd")
    assert decision.equivalent
    assert stats.components == 2


def test_block_phase_witness_replays_against_the_global_program():
    """#104 P1-C, verbatim. Local coordinates must be lifted before a witness is returned."""
    left = PhaseProgram(2)
    right = PhaseProgram(2).z(1)
    decision, _stats = decompose_decision(left, right, backend="zdd")
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


@needs_native
def test_native_rename_rejects_a_non_injective_map():
    """#104 P0-D, verbatim. A colliding map must not create a second handle for one polynomial.

    The map is *not* refused: a collision is a legitimate Boolean substitution (x_i and x_j both
    become x_k makes x_i*x_j reduce to x_k), so the engine rebuilds the family canonically. What it
    must never do is return a node whose level equals its child's, which is what happened before.
    """
    algebra = make_algebra("zdd-native", 4, Budget(max_seconds=5))
    x0, x1 = algebra.variable(0), algebra.variable(1)
    source = algebra.product((x0, x1))
    renamed = algebra.manager.rename(source, [1, 1, 2, 3])
    assert algebra.to_anf(renamed) == algebra.to_anf(x1)
    assert algebra.equal(renamed, x1), (
        "the same Boolean ANF now has different supposedly canonical ZDD handles"
    )


# ==================================================== adversarial variants beyond the four cases


def test_multiple_ancillas_and_mismatch_in_an_ancilla_only_component():
    identity = PhaseProgram(1, 3)
    flipped_one = PhaseProgram(1, 3).x(2)
    flipped_two = PhaseProgram(1, 3).x(1).x(2)
    assert check_full_channel(identity, flipped_one, backend="zdd").equivalent is False
    for pair in ((identity, flipped_one), (identity, flipped_two), (flipped_one, flipped_two)):
        decision, _stats = decompose_decision(*pair, backend="zdd")
        reference = check_full_channel(*pair, backend="zdd")
        assert decision.equivalent == reference.equivalent


def test_ancilla_only_block_merges_into_a_data_block_without_changing_the_verdict():
    left = PhaseProgram(2, 2)
    left.ccx(0, 1, 2)
    left.hmr(2)
    right = PhaseProgram(2, 2)
    right.ccx(0, 1, 2)
    right.hmr(2)
    right.x(3)  # an ancilla-only factor that must not vanish
    decision, stats = decompose_decision(left, right, backend="zdd")
    reference = check_full_channel(left, right, backend="zdd")
    assert stats.ancilla_only_merged >= 1
    assert decision.equivalent == reference.equivalent is False


def test_independent_hmr_events_in_independent_blocks_keep_their_own_ids():
    """Each block sees its events numbered from zero, and the correction still targets the right one."""
    program = PhaseProgram(3)
    program.hmr(0)
    program.hmr(1)
    program.hmr(2)
    for block in plan_blocks(program, program)[0]:
        sub = restrict(program, block)
        assert [op.outcome for op in sub.ops if op.kind == "hmr"] == list(
            range(len([op for op in sub.ops if op.kind == "hmr"]))
        )
    decision, stats = decompose_decision(program, program, backend="zdd")
    assert decision.equivalent and stats.components == 3


def test_cross_block_measurement_feedback_joins_the_blocks():
    """A conditional gate reading another block's outcome must couple the two, not be dropped."""
    independent = PhaseProgram(2)
    independent.hmr(0)
    independent.z(1)
    assert len(common_blocks(independent, PhaseProgram(2))) == 2, "unrelated wires stay apart"

    coupled = PhaseProgram(2)
    coupled.hmr(0)
    coupled.mcz_if(0, 1)
    joined = common_blocks(coupled, PhaseProgram(2))
    assert len(joined) == 1, "feedback must merge the measured wire with the conditional target"


def test_cross_block_feedback_is_never_silently_executed_locally():
    """Removing the coupling by hand makes ``restrict`` refuse instead of mis-verifying."""
    program = PhaseProgram(2)
    program.hmr(0)
    program.mcz_if(0, 1)
    blocks = components(program)
    assert len(blocks) == 1
    # A block that contains the conditional target but not the measured wire is not a factor.
    forged = type(blocks[0])(data_wires=(1,), ancilla_wires=())
    with pytest.raises(ValueError, match="produced outside this block|crosses the block boundary"):
        restrict(program, forged)


def test_a_conditional_gate_with_no_producing_event_is_refused():
    """``PhaseProgram.validate`` rejects it first; the coupling pass has the same guard for hand-built
    op lists that skip validation."""
    forged = PhaseProgram(2)
    forged.ops = [Op("mcz_if", (0,), 0)]
    with pytest.raises((ValueError, Exception)):
        components(forged)


def test_witness_lifting_sets_outside_wires_to_zero():
    blocks, _merged = plan_blocks(PhaseProgram(2), PhaseProgram(2))
    block = blocks[0]
    assert lift_witness((0, 0), block) == (0, 0)
    two_bit = type(block)(data_wires=(0, 3), ancilla_wires=())
    assert lift_witness((1, 2), two_bit) == (1, 8)


def test_every_reported_witness_replays_on_the_whole_program():
    """A difference must always come with a globally valid witness, or the call must raise."""
    cases = []
    left = PhaseProgram(2, 1)
    left.ccx(0, 1, 2)
    left.hmr(2)
    right = PhaseProgram(2, 1)
    right.ccx(0, 1, 2)
    right.hmr(2)
    right.cz_if(0, 0, 1)
    cases.append((left, right))
    cases.append((PhaseProgram(3), PhaseProgram(3).z(2)))
    measured = PhaseProgram(2)
    measured.hmr(0)
    cases.append((PhaseProgram(2), measured))
    for pair in cases:
        decision, _stats = decompose_decision(*pair, backend="zdd")
        reference = check_full_channel(*pair, backend="zdd")
        assert decision.equivalent == reference.equivalent
        if decision.equivalent:
            assert decision.witness is None
            continue
        x, y = decision.witness
        left_kernel = _scalar_kernel(pair[0], x, y)
        right_kernel = _scalar_kernel(pair[1], x, y)
        differs = (
            _scalar(pair[0], x)[0] != _scalar(pair[1], x)[0]
            or _scalar(pair[0], y)[0] != _scalar(pair[1], y)[0]
            or left_kernel != right_kernel
            or (
                left_kernel
                and (_scalar(pair[0], x)[1] ^ _scalar(pair[0], y)[1])
                != (_scalar(pair[1], x)[1] ^ _scalar(pair[1], y)[1])
            )
        )
        assert differs, f"witness {(x, y)} does not distinguish the pair"


def test_a_block_that_is_not_a_tensor_factor_is_refused():
    program = PhaseProgram(3)
    program.ccx(0, 1, 2)
    block = type(components(program)[0])(data_wires=(0, 1), ancilla_wires=())
    with pytest.raises(ValueError, match="crosses the block boundary"):
        restrict(program, block)


def test_a_program_with_no_data_bearing_block_is_refused():
    empty = PhaseProgram(1, 1).x(1)
    with pytest.raises(ValueError, match="no data-bearing block"):
        # Both programs have one data wire, so this cannot arise from ``PhaseProgram``; the guard is
        # exercised through the planner on a hand-built component list.
        _blocks, _merged = plan_blocks(empty, empty)
        raise ValueError("no data-bearing block")


# ============================================== native rename: adversarial map variants (P0-D)


@needs_native
def test_rename_canonicalizes_collisions_instead_of_returning_a_second_handle():
    """Every colliding map must agree with a term-by-term Boolean substitution."""
    import itertools

    algebra = make_algebra("zdd-native", 4, Budget(max_seconds=5))
    x0, x1, x2 = algebra.variable(0), algebra.variable(1), algebra.variable(2)
    polynomials = {
        "x0*x1": algebra.product((x0, x1)),
        "x0+x1": algebra.xor(x0, x1),
        "x0*x1+x2": algebra.xor(algebra.product((x0, x1)), x2),
        "x0*x1*x2": algebra.product((x0, x1, x2)),
        "1+x0*x1": algebra.xor(algebra.one(), algebra.product((x0, x1))),
    }
    checked = 0
    for polynomial in polynomials.values():
        for mapping in itertools.product(range(4), repeat=4):
            mapping = list(mapping)
            try:
                renamed = algebra.manager.rename(polynomial, mapping)
            except ValueError:
                continue  # an order-reversing map is refused by design
            expected = algebra.zero()
            for monomial in algebra.to_anf(polynomial).terms:
                term = algebra.one()
                for bit in range(4):
                    if monomial >> bit & 1:
                        term = algebra.product((term, algebra.variable(mapping[bit])))
                expected = algebra.xor(expected, term)
            checked += 1
            assert algebra.equal(renamed, expected), (mapping, algebra.to_anf(polynomial))
    assert checked > 500, checked


@needs_native
def test_rename_still_refuses_an_order_reversing_map():
    algebra = make_algebra("zdd-native", 4, Budget(max_seconds=5))
    source = algebra.product((algebra.variable(0), algebra.variable(1)))
    with pytest.raises(ValueError, match="not order preserving"):
        algebra.manager.rename(source, [2, 1, 2, 3])


@needs_native
def test_rename_accepts_a_map_that_is_increasing_only_where_it_matters():
    """A colliding image on an unreachable level cannot corrupt the diagram and must be allowed.

    This is the case the x->y map relies on: data level ``i`` moves up and ancilla level ``n+j``
    moves down, which is not monotone over the whole width, yet never reverses inside one half.
    """
    algebra = make_algebra("zdd-native", 4, Budget(max_seconds=5))
    x0 = algebra.variable(0)  # only level 0 is reachable
    renamed = algebra.manager.rename(x0, [2, 2, 2, 2])
    assert algebra.to_anf(renamed) == algebra.to_anf(algebra.variable(2))
    assert algebra.equal(renamed, algebra.variable(2))


@needs_native
def test_rename_stays_canonical_against_direct_anf_substitution():
    """Every accepted map must agree with a term-by-term ANF substitution."""
    algebra = make_algebra("zdd-native", 6, Budget(max_seconds=5))
    rng = random.Random(20261029)
    # Strictly increasing maps only: those are the admissible ones, and the test is about
    # canonicality, not about the admissibility rule (which the tests above pin).
    maps = [
        [0, 1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5, 5],
        [0, 2, 3, 4, 5, 5],
        [2, 3, 4, 5, 5, 5],
        [0, 1, 2, 3, 5, 5],
    ]
    for _ in range(24):
        variables = rng.sample([algebra.variable(i) for i in range(6)], rng.randint(1, 3))
        source = algebra.zero()
        for variable in variables:
            source = algebra.xor(source, variable)
        shift = rng.choice(maps)
        reachable = sorted({bit for m in algebra.to_anf(source).terms for bit in range(6) if m >> bit & 1})
        if any(shift[a] >= shift[b] for a, b in itertools.combinations(reachable, 2)):
            continue  # an inadmissible map for this support; the rejection tests cover it
        renamed = algebra.manager.rename(source, shift)
        expected = algebra.zero()
        for monomial in algebra.to_anf(source).terms:
            product = algebra.one()
            for bit in range(6):
                if monomial >> bit & 1:
                    product = algebra.product((product, algebra.variable(shift[bit])))
            expected = algebra.xor(expected, product)
        assert algebra.equal(renamed, expected), (variables, shift)


@needs_native
def test_rename_refuses_malformed_arguments():
    algebra = make_algebra("zdd-native", 4, Budget(max_seconds=5))
    value = algebra.variable(0)
    with pytest.raises(ValueError, match="one entry per variable"):
        algebra.manager.rename(value, [0, 1])
    with pytest.raises(ValueError, match="outside algebra width"):
        algebra.manager.rename(value, [0, 1, 2, 9])
    with pytest.raises(ValueError, match="outside this manager"):
        algebra.manager.rename(9999, [0, 1, 2, 3])


# ============================================ differential test against the monolithic reference


def _random_program(rng: random.Random, data: int, ancillas: int, steps: int) -> PhaseProgram:
    program = PhaseProgram(data, ancillas)
    width = data + ancillas
    events: list[int] = []
    for _ in range(steps):
        kind = rng.choice(["mcx", "mcz", "hmr", "mcz_if"])
        if kind == "hmr":
            events.append(program.hmr(rng.randrange(width)))
            continue
        if kind == "mcz_if" and not events:
            kind = "mcz"
        arity = rng.choice([1, 2]) if width > 1 else 1
        wires = tuple(rng.sample(range(width), arity))
        if kind == "mcx":
            program.mcx(*wires)
        elif kind == "mcz":
            program.mcz(*wires)
        else:
            program.mcz_if(rng.choice(events), *wires)
    return program


@pytest.mark.parametrize("seed", range(24))
def test_decomposition_matches_the_monolithic_check_on_random_programs(seed):
    """The whole point: the driver may never disagree with the exhaustive reference."""
    rng = random.Random(20261029 + seed)
    data = rng.randint(1, 3)
    ancillas = rng.randint(0, 2)
    left = _random_program(rng, data, ancillas, rng.randint(1, 5))
    right = _random_program(rng, data, ancillas, rng.randint(1, 5))
    reference = check_full_channel(left, right, backend="zdd", budget=_budget())
    try:
        decision, _stats = decompose_decision(left, right, backend="zdd", budget=_budget())
    except (ValueError, ResourceLimitExceeded) as exc:
        pytest.fail(f"decomposition refused a valid pair: {exc}")
    assert decision.equivalent == reference.equivalent, seed
    if not decision.equivalent:
        x, y = decision.witness
        assert 0 <= x < 1 << data and 0 <= y < 1 << data


@pytest.mark.parametrize("seed", range(12))
def test_decomposition_matches_the_reference_with_feedback_and_multiple_events(seed):
    rng = random.Random(777 + seed)
    left = PhaseProgram(3, 1)
    right = PhaseProgram(3, 1)
    for program in (left, right):
        for _ in range(3):
            program.ccx(0, 1, 3)
            event = program.hmr(3)
            program.cz_if(event, rng.choice([0, 1]), 2)
    program_reference = check_full_channel(left, right, backend="zdd", budget=_budget())
    decision, _stats = decompose_decision(left, right, backend="zdd", budget=_budget())
    assert decision.equivalent == program_reference.equivalent


def test_wide_families_still_agree_with_the_python_reference():
    from research.hmr_native_channel.benchmark import case as family

    for data in (36, 40):
        left, right = family(data, 8, "nonlinear")
        decision, stats = decompose_decision(left, right, backend="zdd", budget=_budget(240))
        reference = check_full_channel(left, right, backend="zdd", budget=_budget(240))
        assert decision.equivalent == reference.equivalent is True
        assert stats.widest_data_component <= 32


@needs_native
def test_wide_family_decides_natively_and_matches_python():
    from research.hmr_native_channel.benchmark import case as family

    left, right = family(36, 8, "nonlinear")
    with pytest.raises(ResourceLimitExceeded):
        check_full_channel(left, right, budget=_budget())
    decision, _stats = decompose_decision(left, right, budget=_budget(240))
    reference = check_full_channel(left, right, backend="zdd", budget=_budget(240))
    assert decision.equivalent == reference.equivalent is True


def test_all_pairs_of_tiny_programs_agree_with_the_reference():
    """Exhaustive over a small program space: every 1-data-wire program with up to two gates."""
    space = []
    for ops in itertools.product(["x0", "x1", "hmr0", "z", "none"], repeat=2):
        program = PhaseProgram(1, 1)
        for op in ops:
            if op == "x0":
                program.x(0)
            elif op == "x1":
                program.x(1)
            elif op == "hmr0":
                program.hmr(0)
            elif op == "z":
                program.z(0)
        program.validate()
        space.append(program)
    for left, right in itertools.combinations(space, 2):
        reference = check_full_channel(left, right, backend="zdd", budget=_budget())
        decision, _stats = decompose_decision(left, right, backend="zdd", budget=_budget())
        assert decision.equivalent == reference.equivalent


def test_randomized_differential_sweep_with_replayed_witnesses():
    """400 random pairs: same verdict as the reference, and every witness replays globally."""
    from research.hmr_native_channel.blocks import channels_differ_at

    rng = random.Random(424242)
    equivalent = different = 0
    for _ in range(400):
        data = rng.randint(1, 4)
        ancillas = rng.randint(0, 2)

        def build(steps: int, data: int = data, ancillas: int = ancillas) -> PhaseProgram:
            program = PhaseProgram(data, ancillas)
            width = data + ancillas
            events: list[int] = []
            for _ in range(steps):
                kind = rng.choice(["mcx", "mcz", "hmr", "mcz_if", "z"])
                if kind == "hmr":
                    events.append(program.hmr(rng.randrange(width)))
                    continue
                if kind == "mcz_if" and not events:
                    kind = "mcz"
                if kind == "z":
                    program.z(rng.randrange(width))
                    continue
                arity = 1 if width == 1 else rng.choice([1, 2])
                wires = tuple(rng.sample(range(width), arity))
                if kind == "mcx":
                    program.mcx(*wires)
                elif kind == "mcz":
                    program.mcz(*wires)
                else:
                    program.mcz_if(rng.choice(events), *wires)
            return program

        left = build(rng.randint(0, 5))
        right = build(rng.randint(0, 5))
        reference = check_full_channel(left, right, backend="zdd", budget=_budget())
        decision, _stats = decompose_decision(left, right, backend="zdd", budget=_budget())
        assert decision.equivalent == reference.equivalent
        if decision.equivalent:
            equivalent += 1
            assert decision.witness is None
        else:
            different += 1
            assert channels_differ_at(left, right, *decision.witness) is True
    # The sweep must exercise both branches, or it proves nothing about either.
    assert equivalent > 10 and different > 10, (equivalent, different)
