from __future__ import annotations

import copy
import json
import random
from fractions import Fraction

import pytest
from testkit.affine_phase_oracle import same_channel

from symq.circuit import UnsupportedOperation
from symq.labs import affine_phase as module
from symq.labs.affine_phase import (
    AffineSupport,
    DerivativeLimits,
    check_affine_phase,
    replay_affine_phase,
)
from symq.labs.dyadic_phase import DyadicGate, DyadicPhaseProgram
from symq.phase import Op, PhaseProgram
from symq.resources import Budget


def dephase(width, rows, constants=0):
    source = PhaseProgram(width, 1)
    for i, row in enumerate(rows):
        if constants >> i & 1:
            source.x(width)
        for q in range(width):
            if row >> q & 1:
                source.cx(q, width)
        source.hmr(width)
    return source


def test_real_source_signature_and_portable_receipt():
    left, right = DyadicPhaseProgram(3), DyadicPhaseProgram(3).t(0)
    source = dephase(3, (1, 3, 1), constants=5)
    result = check_affine_phase(left, right, source)
    assert result.equivalent and not result.different
    assert result.receipt.signature_rows == (1, 3, 1)
    assert result.receipt.signature_constants == (1, 0, 1)
    assert result.receipt.kernel_basis == (4,)
    document = json.loads(json.dumps(result.receipt.to_dict()))
    assert replay_affine_phase(left, right, source, document).equivalent
    assert same_channel(left, right, source)


@pytest.mark.parametrize("offset", [0, 1])
def test_correlated_support_requires_its_own_tangent_directions(offset):
    support = AffineSupport(2, offset, (3,))
    left, right, source = DyadicPhaseProgram(2), DyadicPhaseProgram(2).z(0), PhaseProgram(2)
    result = check_affine_phase(left, right, source, support=support)
    assert result.status == "not_proved" and result.receipt is None
    assert set(result.witness) == {offset, offset ^ 3}
    assert not same_channel(left, right, source, offset=offset, columns=(3,))
    right.z(1)
    assert check_affine_phase(left, right, source, support=support).equivalent
    assert same_channel(left, right, source, offset=offset, columns=(3,))


def test_dyadic_derivative_must_not_be_reduced_modulo_two():
    left, right, source = DyadicPhaseProgram(2), DyadicPhaseProgram(2).t(0).t(1), dephase(2, (3,))
    result = check_affine_phase(left, right, source)
    assert result.status == "not_proved" and result.witness == (0, 3)
    assert not same_channel(left, right, source)
    right = DyadicPhaseProgram(2).z(0).z(1)
    assert check_affine_phase(left, right, source).equivalent
    assert same_channel(left, right, source)


def test_nonlinear_signature_can_be_affine_on_the_declared_support():
    source = PhaseProgram(2, 1).ccx(0, 1, 2)
    source.hmr(2)
    left, right = DyadicPhaseProgram(2), DyadicPhaseProgram(2).t(0)
    assert check_affine_phase(left, right, source).reason.startswith("dephaser signature")
    for offset, expected in ((2, True), (0, False)):
        support = AffineSupport(2, offset, (1,))
        result = check_affine_phase(left, right, source, support=support)
        assert result.equivalent is expected
        assert same_channel(left, right, source, offset=offset, columns=(1,)) is expected


def test_common_dephaser_phase_cancels_but_feedback_changes_the_signature():
    left, right = DyadicPhaseProgram(2), DyadicPhaseProgram(2).t(0)
    source = dephase(2, (1,))
    source.cz(0, 1)
    assert check_affine_phase(left, right, source).equivalent
    assert same_channel(left, right, source)
    source.z_if(0, 0)
    assert check_affine_phase(left, right, source).status == "not_proved"
    assert not same_channel(left, right, source)


def test_dephaser_must_restore_all_data_and_retained_ancillas():
    left, right = DyadicPhaseProgram(2), DyadicPhaseProgram(2)
    for source in (PhaseProgram(2).x(0), PhaseProgram(2, 1).cx(0, 2)):
        result = check_affine_phase(left, right, source)
        assert result.status == "not_proved"
        assert "restore" in result.reason and result.receipt is None


def test_dephaser_restoration_can_hold_only_on_declared_support():
    source = PhaseProgram(2, 1).cx(0, 2).cx(1, 2)
    left = DyadicPhaseProgram(2)
    assert check_affine_phase(left, left, source).status == "not_proved"
    result = check_affine_phase(left, left, source, support=AffineSupport(2, 0, (3,)))
    assert result.equivalent
    assert same_channel(left, left, source, columns=(3,))


def test_singleton_fibres_skip_phase_expansion_but_require_output_equality(monkeypatch):
    width = 24
    left, right, source = DyadicPhaseProgram(width, k=40), DyadicPhaseProgram(width, k=40), dephase(width, tuple(1 << q for q in range(width)))
    for q in range(1, width):
        right.cx(q, 0)
    right.phase(0, Fraction(1, 1 << 40))
    for q in range(width - 1, 0, -1):
        right.cx(q, 0)
    monkeypatch.setattr(module, "_lift", lambda *args: pytest.fail("no phase lift is necessary"))
    result = check_affine_phase(left, right, source, budget=Budget(max_terms=1000))
    assert result.equivalent and result.metrics["singleton_fibres"] == 1
    assert result.metrics["phase_predicates"] == 0
    right.x(0)
    assert check_affine_phase(left, right, source).status == "not_proved"


def test_measured_parity_skips_lifting_even_with_a_nontrivial_kernel(monkeypatch):
    width = 24
    left, right = DyadicPhaseProgram(width, k=40), DyadicPhaseProgram(width, k=40)
    row = (1 << width) - 1
    source = dephase(width, (row,))
    for q in range(1, width):
        right.cx(q, 0)
    right.phase(0, Fraction(1, 1 << 40))
    for q in range(width - 1, 0, -1):
        right.cx(q, 0)
    monkeypatch.setattr(module, "_lift", lambda *args: pytest.fail("invariant predicates need no lift"))
    result = check_affine_phase(left, right, source, budget=Budget(max_terms=1000))
    assert result.equivalent
    assert result.metrics["kernel_dimension"] == width - 1
    assert result.metrics["skipped_invariant_contributions"] == width - 1


def test_weighted_sign_lift_avoids_irrelevant_modular_terms():
    width = 18
    left, right, source = DyadicPhaseProgram(width, k=40), DyadicPhaseProgram(width, k=40), PhaseProgram(width)
    for q in range(1, width):
        right.cx(q, 0)
    right.z(0)
    for q in range(width - 1, 0, -1):
        right.cx(q, 0)
    result = check_affine_phase(left, right, source, budget=Budget(max_terms=1000))
    assert result.status == "not_proved" and result.witness is not None


@pytest.mark.parametrize("offset", [0, 1, 3])
def test_singleton_support_has_no_phase_obligation_but_has_an_output_obligation(offset):
    left, right, source = DyadicPhaseProgram(2), DyadicPhaseProgram(2).t(0), PhaseProgram(2)
    support = AffineSupport(2, offset, ())
    assert check_affine_phase(left, right, source, support=support).equivalent
    assert same_channel(left, right, source, offset=offset, columns=())
    right.x(1)
    assert check_affine_phase(left, right, source, support=support).status == "not_proved"


def test_different_dyadic_moduli_are_normalized_exactly():
    left = DyadicPhaseProgram(2, k=3).phase(0, Fraction(1, 8))
    right = DyadicPhaseProgram(2, k=5).phase(0, Fraction(4, 32))
    source = PhaseProgram(2)
    result = check_affine_phase(left, right, source)
    assert result.equivalent and result.receipt.k == 5
    assert same_channel(left, right, source)


def test_seeded_full_kraus_matrix_unit_differential():
    rng = random.Random(139_20261102)
    positives = negatives = 0
    for _ in range(96):
        width, k = 3, rng.choice((3, 4, 5))
        rows = tuple(rng.randrange(8) for _ in range(rng.randrange(4)))
        source = dephase(width, rows, rng.randrange(8)).cz(0, 1)
        dimension = rng.randrange(4)
        columns = tuple((1, 3, 7)[:dimension])
        offset = rng.randrange(8)
        support = AffineSupport(width, offset, columns)
        left, right = DyadicPhaseProgram(width, k=k), DyadicPhaseProgram(width, k=k)
        for _ in range(3):
            gate = rng.choice(("x", "cx", "ccx"))
            wires = tuple(rng.sample(range(width), {"x": 1, "cx": 2, "ccx": 3}[gate]))
            left.append(gate, *wires)
            right.append(gate, *wires)
        for _ in range(rng.randrange(4)):
            right.phase(rng.randrange(width), Fraction(rng.randrange(1, 1 << k), 1 << k))
        expected = same_channel(left, right, source, offset=offset, columns=columns)
        result = check_affine_phase(left, right, source, support=support)
        assert result.equivalent is expected, (rows, offset, columns, result)
        positives += expected
        negatives += not expected
        if result.receipt:
            assert replay_affine_phase(left, right, source, result.receipt.to_dict(), support=support).equivalent
    assert positives >= 20 and negatives >= 20


def test_kernel_is_reconstructed_and_complete_for_every_small_binary_matrix():
    # Every 2x3 matrix, not merely hand-picked ranks.
    for row0 in range(8):
        for row1 in range(8):
            rows = (row0, row1)
            source = dephase(3, rows)
            identity = DyadicPhaseProgram(3)
            receipt = check_affine_phase(identity, identity, source).receipt
            actual = {0}
            for vector in receipt.kernel_basis:
                actual |= {x ^ vector for x in tuple(actual)}
            expected = {x for x in range(8) if all((row & x).bit_count() % 2 == 0 for row in rows)}
            assert actual == expected


@pytest.mark.parametrize("field,value", [
    ("schema", "wrong"), ("source_sha256", "0" * 64), ("phase_sha256", "f" * 64),
    ("parameter_dimension", 1), ("k", 4), ("signature_rows", []),
    ("signature_constants", [1]), ("kernel_basis", []),
    ("kernel_basis", [True]), ("kernel_basis", [1]), ("kernel_basis", (2,)),
])
def test_mutated_receipts_are_not_proofs(field, value):
    left, right, source = DyadicPhaseProgram(2), DyadicPhaseProgram(2).t(0), dephase(2, (1,))
    document = check_affine_phase(left, right, source).receipt.to_dict()
    document[field] = value
    result = replay_affine_phase(left, right, source, document)
    assert result.status == "not_proved" and result.receipt is None


def test_unknown_receipt_fields_and_non_json_equality_tricks_are_rejected():
    class AlwaysEqual(int):
        def __eq__(self, other):
            return True

    source, left = PhaseProgram(1), DyadicPhaseProgram(1)
    document = check_affine_phase(left, left, source).receipt.to_dict()
    for bad in (dict(document, extra=1), dict(document, k=AlwaysEqual(3)), [document], None):
        assert replay_affine_phase(left, left, source, bad).status == "not_proved"


@pytest.mark.parametrize("changed", ["left", "right", "dephaser", "support"])
def test_even_semantically_equivalent_source_changes_invalidate_a_receipt(changed):
    left, right, source = DyadicPhaseProgram(2), DyadicPhaseProgram(2), PhaseProgram(2)
    support = AffineSupport(2, 0, (3,))
    document = check_affine_phase(left, right, source, support=support).receipt.to_dict()
    if changed == "left":
        left.x(0).x(0)
    elif changed == "right":
        right.x(1).x(1)
    elif changed == "dephaser":
        source.cz(0, 1)
    else:
        support = AffineSupport(2, 3, (3,))
    assert check_affine_phase(left, right, source, support=support).equivalent
    assert replay_affine_phase(left, right, source, document, support=support).status == "not_proved"


@pytest.mark.parametrize("support", [
    AffineSupport(2, 0, (1, 1)), AffineSupport(2, 0, (0,)),
    AffineSupport(2, 4, (1,)), AffineSupport(2, True, (1,)),
    AffineSupport(2, 0, (True,)), AffineSupport(2, 0, [1]), AffineSupport(3, 0, (1,)),
])
def test_malformed_or_dependent_affine_support_is_rejected(support):
    with pytest.raises((TypeError, ValueError)):
        check_affine_phase(DyadicPhaseProgram(2), DyadicPhaseProgram(2), PhaseProgram(2), support=support)


@pytest.mark.parametrize("target", ["dyadic_name", "dyadic_wire", "dephaser_kind", "dephaser_outcome"])
def test_deceptive_subclasses_are_rejected_before_interpretation(target):
    class String(str):
        pass

    class Integer(int):
        pass

    left, right, source = DyadicPhaseProgram(2).x(0), DyadicPhaseProgram(2), dephase(2, (1,))
    if target == "dyadic_name":
        object.__setattr__(left.gates[0], "name", String("x"))
    elif target == "dyadic_wire":
        object.__setattr__(left.gates[0], "wires", (Integer(0),))
    elif target == "dephaser_kind":
        object.__setattr__(source.ops[0], "kind", String("mcx"))
    else:
        object.__setattr__(source.ops[-1], "outcome", Integer(0))
    with pytest.raises(UnsupportedOperation):
        check_affine_phase(left, right, source)


@pytest.mark.parametrize("mutation", ["dyadic_gate", "dephaser_event", "dyadic_list", "bad_width", "bad_k", "angle"])
def test_mutated_programs_fail_closed(mutation):
    left, right, source = DyadicPhaseProgram(2), DyadicPhaseProgram(2), dephase(2, (1,))
    if mutation == "dyadic_gate":
        gate = DyadicGate("x", (0,))
        object.__setattr__(gate, "name", "h")
        left.gates.append(gate)
    elif mutation == "dephaser_event":
        source.ops[-1] = Op("hmr", (2,), 4)
    elif mutation == "dyadic_list":
        left.gates = ()
    elif mutation == "bad_width":
        left.width = True
    elif mutation == "bad_k":
        left.k = 65
    else:
        gate = DyadicGate("phase", (0,), Fraction(1, 8))
        object.__setattr__(gate, "angle", 0.125)
        left.gates.append(gate)
    with pytest.raises((TypeError, ValueError, UnsupportedOperation)):
        check_affine_phase(left, right, source)


@pytest.mark.parametrize("malformation", ["integer_subclass", "unreduced", "negative_denominator"])
def test_forged_fraction_internals_are_rejected(malformation):
    class ZeroMultiply(int):
        def __mul__(self, other):
            return 0

    angle = Fraction(1, 8)
    if malformation == "integer_subclass":
        object.__setattr__(angle, "_numerator", ZeroMultiply(1))
    elif malformation == "unreduced":
        object.__setattr__(angle, "_numerator", 2)
        object.__setattr__(angle, "_denominator", 16)
    else:
        object.__setattr__(angle, "_denominator", -8)
    right = DyadicPhaseProgram(1)
    right.gates.append(DyadicGate("phase", (0,), angle))
    with pytest.raises(UnsupportedOperation):
        check_affine_phase(DyadicPhaseProgram(1), right, PhaseProgram(1))


def test_fraction_source_is_detached_before_semantic_work(monkeypatch):
    angle = Fraction(1, 8)
    left, right = DyadicPhaseProgram(1), DyadicPhaseProgram(1).phase(0, angle)
    original = module._dyadic_semantics

    def mutate_original(*args):
        object.__setattr__(angle, "_numerator", 0)
        return original(*args)

    monkeypatch.setattr(module, "_dyadic_semantics", mutate_original)
    result = check_affine_phase(left, right, PhaseProgram(1))
    assert result.status == "not_proved" and result.witness == (0, 1)


def test_extreme_integer_angles_reach_the_explicit_serialization_cap():
    right = DyadicPhaseProgram(1).phase(0, 1 << 4096)
    result = check_affine_phase(DyadicPhaseProgram(1), right, PhaseProgram(1))
    assert result.status == "inconclusive" and "angle_bits" in result.reason


def test_boundaries_and_structural_limits():
    left, right, source = DyadicPhaseProgram(2), DyadicPhaseProgram(2), dephase(2, (1, 2))
    for limits in (DerivativeLimits(max_width=2), DerivativeLimits(max_gates=1),
                   DerivativeLimits(max_measurements=1), DerivativeLimits(max_receipt_items=1)):
        result = check_affine_phase(left, right, source, limits=limits)
        assert result.status == "inconclusive" and result.receipt is None
    for budget in (Budget(max_terms=1), Budget(max_seconds=1e-12)):
        result = check_affine_phase(left, right, source, budget=budget)
        assert result.status == "inconclusive" and result.receipt is None
    for budget in (Budget(max_nodes=1), Budget(max_bytes=1)):
        with pytest.raises(ValueError):
            check_affine_phase(left, right, source, budget=budget)


def test_dense_unmeasured_modular_phase_can_exhaust_its_term_cap():
    width = 14
    left, right, source = DyadicPhaseProgram(width, k=20), DyadicPhaseProgram(width, k=20), PhaseProgram(width)
    for q in range(1, width):
        right.cx(q, 0)
    right.phase(0, Fraction(1, 1 << 20))
    for q in range(width - 1, 0, -1):
        right.cx(q, 0)
    result = check_affine_phase(left, right, source, budget=Budget(max_terms=128))
    assert result.status == "inconclusive" and result.receipt is None


@pytest.mark.parametrize("replay", [False, True])
def test_final_deadline_includes_semantic_scratch_cleanup(monkeypatch, replay):
    from symq import resources

    left, source = DyadicPhaseProgram(1), PhaseProgram(1)
    document = check_affine_phase(left, left, source).receipt.to_dict()
    clock = [0.0]
    original = module._check

    class SlowCleanup:
        def __del__(self):
            clock[0] += 2.0

    def delayed(*args):
        sentinel = SlowCleanup()
        result = original(*args)
        assert sentinel is not None
        return result

    monkeypatch.setattr(resources.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(module, "_check", delayed)
    if replay:
        result = replay_affine_phase(left, left, source, document, budget=Budget(max_seconds=1))
    else:
        result = check_affine_phase(left, left, source, budget=Budget(max_seconds=1))
    assert result.status == "inconclusive" and result.receipt is None


def test_receipt_loading_is_bounded_and_does_not_trust_a_receipt_object():
    left, source = DyadicPhaseProgram(1), PhaseProgram(1)
    receipt = check_affine_phase(left, left, source).receipt
    assert replay_affine_phase(left, left, source, receipt).status == "not_proved"
    document = receipt.to_dict()
    document["extra"] = document
    assert replay_affine_phase(left, left, source, document).status == "not_proved"
    document = copy.deepcopy(receipt.to_dict())
    document["kernel_basis"] = [0] * 100
    result = replay_affine_phase(left, left, source, document, limits=DerivativeLimits(max_receipt_items=50))
    assert result.status == "inconclusive"
