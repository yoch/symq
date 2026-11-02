"""Exact coherences, nonsymmetric operator bases and adverse representation boundaries."""
import random
from fractions import Fraction

import pytest

from symq.circuit import UnsupportedOperation
from symq.experimental.hybrid import HOp, HybridProgram, coherence_image
from symq.labs import backward_ancilla as baseline
from symq.labs import shift_diagonal_ancilla as sd
from symq.resources import Budget


def _evaluate(poly, assignment):
    return sum((c for mask, c in poly.items() if mask & assignment == mask), Fraction(0))


def _matrix(effect, data):
    result = {}
    for column in range(1 << data):
        for row in range(1 << data):
            if type(effect) is set:
                result[row, column] = (sum(mask & column == mask for mask in effect) % 2
                                       if row == column else 0)
            else:
                result[row, column] = _evaluate(effect.get(row ^ column, {}), column)
    return result


def _check(program, target):
    guard, limits = baseline._settings(None, None)
    work = sd.Work(guard, limits)
    source = baseline._freeze(program, target, work)
    effect = sd._effect(source, target, work)
    matrix = _matrix(effect, program.data)
    for x in range(1 << program.data):
        for y in range(1 << program.data):
            channel = coherence_image(program, x, y, max_width=6, max_events=8)
            expected = sum((c for (a, b), c in channel.items() if a == b and a >> target & 1),
                           Fraction(0))
            assert matrix[y, x] == expected
    actual = sd.check_shift_diagonal(program, target)
    reference = baseline.check_clean_ancilla(program, target)
    assert actual.status == reference.status == ("not_clean" if any(matrix.values()) else "clean")
    if actual.status == "not_clean":
        assert matrix[actual.assignment, actual.assignment] == actual.probability > 0
    return actual, effect


def _gate(kind, wires, value):
    if kind in {"x", "cx", "ccx", "mcx"}:
        *controls, target = wires
        return value ^ ((1 << target) if all(value >> q & 1 for q in controls) else 0), 1
    if kind in {"swap", "cswap"}:
        a, b = wires[-2:]
        condition = kind == "swap" or value >> wires[0] & 1
        flip = condition and ((value >> a) ^ (value >> b)) & 1
        return value ^ (((1 << a) | (1 << b)) if flip else 0), 1
    return value, -1 if kind == "neg" or all(value >> q & 1 for q in wires) else 1


@pytest.mark.parametrize("kind,wires", [
    ("x", (1,)), ("cx", (1, 0)), ("ccx", (0, 1, 2)), ("mcx", (2, 0, 1)),
    ("swap", (0, 2)), ("cswap", (1, 2, 0)), ("z", (1,)), ("cz", (2, 1)),
    ("ccz", (2, 0, 1)), ("neg", ()),
])
@pytest.mark.parametrize("condition", [None, "b0", "!b0"])
def test_arbitrary_nonsymmetric_operator_basis_fixes_orientation(kind, wires, condition):
    """Every X^s diag(monomial) basis operator, not just symmetric physical effects."""
    guard, limits = baseline._settings(Budget(max_terms=4096), baseline.AncillaLimits(
        max_products=10000000))
    work = sd.Work(guard, limits)
    op = HOp(kind, wires, condition=condition)
    for shift in range(8):
        for monomial in range(16):  # Includes the classical bit as well.
            effect = {shift: {monomial: Fraction(1)}}
            for primitive in reversed(sd._primitives(op)):
                effect = sd._polynomial_step(effect, primitive, {"b0": 8}, work)
            for classical in (0, 1):
                active = condition is None or bool(classical ^ (condition == "!b0"))
                for column in range(8):
                    moved, sign = _gate(kind, wires, column) if active else (column, 1)
                    coefficient = int(monomial & (moved | (classical << 3)) == monomial)
                    row, sign2 = _gate(kind, wires, moved ^ shift) if active else (moved ^ shift, 1)
                    actual = {r: _evaluate(effect.get(r ^ column, {}), column | (classical << 3))
                              for r in range(8)}
                    assert {r: c for r, c in actual.items() if c} == (
                        {row: Fraction(sign * sign2)} if coefficient else {})


def test_mcx_has_value_dependent_shift_and_composed_coefficient():
    guard, limits = baseline._settings(None, None)
    work = sd.Work(guard, limits)
    effect = sd._unitary({1: {0: Fraction(1)}}, HOp("ccx", (0, 1, 2)), work)
    assert effect == {1: {0: Fraction(1), 2: Fraction(-1)}, 5: {2: Fraction(1)}}


def test_trace_witness_uses_monomial_means_not_only_constant_coefficient():
    program = HybridProgram(2, 1).hmr(0, "b0").cx(1, 2, condition="b0")
    result, effect = _check(program, 2)
    assert effect == {0: {2: Fraction(1, 2)}, 1: {2: Fraction(-1, 2)}}
    assert result.assignment & 2 and result.probability == Fraction(1, 2)


def test_boolean_mode_promotes_only_for_a_relevant_outcome():
    irrelevant = HybridProgram(1, 1).hmr(0, "b0").store("b0", 0).x(1, condition="b0")
    result, _ = _check(irrelevant, 1)
    assert result.status == "clean" and result.mode == "boolean" and result.promotions == 0
    relevant = HybridProgram(1, 1).hmr(0, "b0").x(1, condition="b0")
    result, _ = _check(relevant, 1)
    assert result.mode == "shift_polynomial" and result.promotions == 1


@pytest.mark.parametrize("kind,condition", [("invert", None), ("invert", "b0"),
                                           ("invert", "!b0"), ("oxor", None)])
def test_classical_self_updates_and_overwrite_in_both_modes(kind, condition):
    for first in ("hmr", "measure_z"):
        program = HybridProgram(2, 1)
        getattr(program, first)(0, "b0")
        program.x(2, condition="b0")
        if kind == "invert":
            program.invert("b0", condition=condition)
        else:
            program.oxor("b0", "b0")
        program.x(2, condition="b0").hmr(1, "b0").x(2, condition="b0")
        _check(program, 2)


def test_240_seeded_hybrid_programs_match_the_full_error_effect():
    rng = random.Random(145_20261102)
    names = ("x", "cx", "ccx", "mcx", "swap", "cswap", "z", "cz", "ccz", "neg",
             "hmr", "measure_z", "reset", "store", "invert", "oxor")
    seen, promoted = set(), 0
    for index in range(240):
        data = 2 if index % 3 else 3
        program = HybridProgram(data, 1).store("b0", index & 1).store("b1", index >> 1 & 1)
        for _ in range(4 + index % 6):
            kind = rng.choice(names)
            seen.add(kind)
            a, b, c = rng.sample(range(program.width), 3)
            condition = rng.choice((None, "b0", "!b0", "b1", "!b1"))
            slot = rng.choice(("b0", "b1"))
            if kind in {"hmr", "measure_z"}:
                getattr(program, kind)(a, slot)
            elif kind == "reset":
                program.reset(a)
            elif kind == "store":
                program.store(slot, rng.randrange(2))
            elif kind == "invert":
                program.invert(slot, condition=condition)
            elif kind == "oxor":
                program.oxor(slot, rng.choice(("b0", "b1")))
            elif kind == "neg":
                program.neg(condition=condition)
            else:
                qs = (a,) if kind in {"x", "z"} else (a, b) if kind in {
                    "cx", "cz", "swap"} else (a, b, c)
                getattr(program, kind)(*qs, condition=condition)
        result, _ = _check(program, data)
        promoted += result.promotions
    assert seen == set(names) and promoted >= 10


def _parity_boundary(k):
    program = HybridProgram(k + 1, 1).hmr(0, "b0")
    for q in range(1, k + 1):
        program.cx(q, k + 1)
    return program.x(k + 1, condition="b0")


def test_dense_parity_boundary_refuses_instead_of_truncating():
    small = _parity_boundary(2)
    _check(small, 3)
    program = _parity_boundary(8)
    result = sd.check_shift_diagonal(program, 9, budget=Budget(max_terms=64))
    assert result.status == "inconclusive" and result.assignment is None
    # The old representation stays compact on exactly this adverse family.
    assert baseline.check_clean_ancilla(program, 9, budget=Budget(max_terms=64)).status == "not_clean"


def test_nonadjacent_changed_controls_identity_and_mutant():
    controls = list(range(3))
    program = HybridProgram(3, 1).mcx(*controls, 3).x(0).mcx(*controls, 3).mcx(
        *controls[1:], 3).x(0)
    assert _check(program, 3)[0].status == "clean"
    mutant = HybridProgram(3, 1, program.ops[:3] + program.ops[4:])
    assert _check(mutant, 3)[0].status == "not_clean"


def test_global_budget_covers_conversion_and_final_cleanup(monkeypatch):
    p = HybridProgram(1, 1).cx(0, 1)
    assert sd.check_shift_diagonal(p, 1, limits=baseline.AncillaLimits(
        max_products=1)).status == "inconclusive"
    assert sd.check_shift_diagonal(p, 1, budget=Budget(absolute_deadline=0)).status == "inconclusive"
    clock = [0.0]
    monkeypatch.setattr("symq.resources.time.perf_counter", lambda: clock[0])
    monkeypatch.setattr(sd.Work, "__del__", lambda self: clock.__setitem__(0, 2.0), raising=False)
    result = sd.check_shift_diagonal(HybridProgram(1, 1), 1, budget=Budget(max_seconds=1))
    assert result.status == "inconclusive" and result.assignment is None


def test_published_public_fixtures_have_the_same_scoped_verdict():
    from benchmarks.backward_ancilla import _public_cases

    cases, _ = _public_cases()
    for case in cases:
        result = sd.check_shift_diagonal(case.program, case.target)
        assert result.status == case.expected


@pytest.mark.parametrize("operation", [
    HOp("h", (0,)), HOp("x", (True,)), HOp("store", (), slot="b0", value=True),
    HOp("x", (0,), condition="b0"), HOp("hmr", (0,), slot="b00"),
])
def test_new_entrypoint_validates_even_irrelevant_malformed_source(operation):
    # The target is untouched; accepting an empty backward cone must not skip validation.
    program = HybridProgram(1, 1)
    program.ops.append(operation)  # Bypass the constructor's own validation deliberately.
    with pytest.raises(UnsupportedOperation):
        sd.check_shift_diagonal(program, 1)


def test_strict_source_settings_and_snapshot_identity():
    class ForgedName(str):
        pass

    program = HybridProgram(1, 1)
    program.ops.append(HOp(ForgedName("x"), (0,)))
    with pytest.raises(UnsupportedOperation):
        sd.check_shift_diagonal(program, 1)
    program = HybridProgram(1, 1)
    program.data = True
    with pytest.raises(ValueError):
        sd.check_shift_diagonal(program, 1)
    with pytest.raises(ValueError):
        sd.check_shift_diagonal(HybridProgram(1, 1), True)
    for budget in (Budget(max_nodes=10), Budget(max_bytes=100)):
        with pytest.raises(ValueError):
            sd.check_shift_diagonal(HybridProgram(1, 1), 1, budget=budget)
    program = HybridProgram(1, 1)
    first = sd.check_shift_diagonal(program, 1)
    program.neg()
    second = sd.check_shift_diagonal(program, 1)
    assert first.status == second.status == "clean"
    assert first.source_sha256 != second.source_sha256
