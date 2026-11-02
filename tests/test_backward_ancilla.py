"""Independent dense-channel and adversarial checks of one-observable proofs."""
from __future__ import annotations

import json
import random
from dataclasses import replace
from fractions import Fraction

import pytest

from symq.circuit import UnsupportedOperation
from symq.experimental.hybrid import HOp, HybridProgram, coherence_image, same_channel
from symq.labs import backward_ancilla as ba
from symq.labs.backward_ancilla import (
    AncillaLimits,
    check_clean_ancilla,
    replay_clean_ancilla,
)
from symq.resources import Budget, VerificationSession


def _oracle_effect(program, target):
    """Different representation: exact forward density/Kraus evolution on all units."""
    answer = {}
    for x in range(1 << program.data):
        for y in range(1 << program.data):
            matrix = coherence_image(program, x, y, max_width=6, max_events=8)
            answer[y, x] = sum((c for (u, v), c in matrix.items()
                                if u == v and u >> target & 1), Fraction(0))
    return answer


def _backward_effect(program, target):
    guard, limits = ba._settings(None, None)
    work = ba._Work(guard, limits)
    source = ba._freeze(program, target, work)
    effect = ba._effect(source, target, work)
    answer = {}
    for a in range(1 << program.data):
        for b in range(1 << program.data):
            answer[a, b] = sum((c * (-1 if (z & b).bit_count() & 1 else 1)
                                for (x, z, classical), c in effect.items()
                                if a == b ^ x and classical == 0), Fraction(0))
    return answer


def _assert_oracle(program, target):
    expected = _oracle_effect(program, target)
    assert _backward_effect(program, target) == expected
    result = check_clean_ancilla(program, target)
    assert result.status == ("not_clean" if any(expected.values()) else "clean")
    if result.clean:
        document = json.loads(json.dumps(result.certificate.to_dict()))
        assert replay_clean_ancilla(program, document).clean
    else:
        assert result.certificate is None
        assert result.witness is not None
        assignment = result.witness.assignment
        assert expected[assignment, assignment] == result.witness.probability > 0
    return result


def test_relational_cleanup_is_stronger_than_the_constant_only_abstraction():
    from symq.labs.channel_composition import _advance_known

    program = HybridProgram(1, 1).cx(0, 1).measure_z(0, "b0").x(1, condition="b0")
    known = [None, 0]
    _advance_known(known, tuple(program.ops))
    assert known[1] is None
    assert _assert_oracle(program, 1).clean
    # The data has been dephased. Cleanliness does not authorize a channel rewrite.
    assert not same_channel(program, HybridProgram(1, 1)).equivalent


def test_nonzero_effect_can_depend_on_input_coherences():
    program = HybridProgram(1, 1).hmr(0, "b0").x(1, condition="b0")
    effect = _oracle_effect(program, 1)
    assert effect == {(0, 0): Fraction(1, 2), (0, 1): Fraction(-1, 2),
                      (1, 0): Fraction(-1, 2), (1, 1): Fraction(1, 2)}
    result = _assert_oracle(program, 1)
    assert result.witness.probability == Fraction(1, 2)


@pytest.mark.parametrize("measurement,expected", [("hmr", "not_clean"), ("measure_z", "clean")])
def test_measurement_correlations_and_reset_are_distinguished(measurement, expected):
    program = HybridProgram(1, 1)
    getattr(program, measurement)(0, "b0")
    program.x(1, condition="b0").cx(0, 1)
    assert _assert_oracle(program, 1).status == expected


@pytest.mark.parametrize("kind,value", [("hmr", None), ("measure_z", None), ("store", 0),
                                        ("store", 1)])
def test_overwritten_slot_does_not_reuse_the_old_measurement(kind, value):
    program = HybridProgram(1, 1).measure_z(0, "b0").x(1, condition="b0")
    if kind == "store":
        program.store("b0", value)
    else:
        getattr(program, kind)(1, "b0")
    program.x(1, condition="b0")
    _assert_oracle(program, 1)


@pytest.mark.parametrize("operation,condition,status", [
    ("invert", "b0", "clean"), ("invert", "!b0", "not_clean"),
    ("oxor", None, "clean"), ("invert", None, "not_clean"),
])
def test_noninvertible_classical_self_updates(operation, condition, status):
    program = HybridProgram(1, 1).measure_z(0, "b0")
    if operation == "oxor":
        program.oxor("b0", "b0")
    else:
        program.invert("b0", condition=condition)
    program.x(1, condition="b0")
    assert _assert_oracle(program, 1).status == status


def test_reset_of_entangled_ancilla_is_clean_but_not_identity():
    program = HybridProgram(1, 1).cx(0, 1).reset(1)
    assert _assert_oracle(program, 1).clean
    assert not same_channel(program, HybridProgram(1, 1)).equivalent


def test_missing_phase_feedback_does_not_make_a_reset_ancilla_dirty():
    corrected = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(
        0, 1, condition="b0")
    missing = HybridProgram(3, 1, list(corrected.ops[:-1]))
    assert _assert_oracle(corrected, 3).clean
    assert _assert_oracle(missing, 3).clean
    assert not same_channel(corrected, missing).equivalent
    no_reset = HybridProgram(3, 1, list(corrected.ops[:2]))
    assert _assert_oracle(no_reset, 3).status == "not_clean"


def _direct_gate(kind, wires, value):
    if kind in {"x", "cx", "ccx", "mcx"}:
        *controls, target = wires
        return value ^ ((1 << target) if all(value >> q & 1 for q in controls) else 0), 1
    if kind in {"swap", "cswap"}:
        a, b = wires[-2:]
        enabled = kind == "swap" or bool(value >> wires[0] & 1)
        return value ^ (((1 << a) | (1 << b)) if enabled and
                        ((value >> a) ^ (value >> b)) & 1 else 0), 1
    sign = -1 if kind == "neg" or all(value >> q & 1 for q in wires) else 1
    return value, sign


@pytest.mark.parametrize("kind,wires", [
    ("x", (1,)), ("cx", (1, 0)), ("ccx", (2, 0, 1)), ("mcx", (2, 0, 1)),
    ("swap", (0, 2)), ("cswap", (1, 2, 0)), ("z", (1,)), ("cz", (2, 1)),
    ("ccz", (2, 0, 1)), ("neg", ()),
])
def test_unitary_pullbacks_match_all_real_pauli_matrices(kind, wires):
    """Includes anti-Hermitian XZ factors and SWAP's negative XXZZ coefficient."""
    op = HOp(kind, wires)
    guard, limits = ba._settings(Budget(max_terms=10000), AncillaLimits(max_products=10000000))
    work = ba._Work(guard, limits)
    for x in range(8):
        for z in range(8):
            result = ba._conjugate({(x, z, 0): Fraction(1)}, op, work)
            for column in range(8):
                first, sign = _direct_gate(kind, wires, column)
                sign *= -1 if (z & first).bit_count() & 1 else 1
                row, final_sign = _direct_gate(kind, wires, first ^ x)
                expected = {row: Fraction(sign * final_sign)}
                actual = {}
                for (a, b, c), coefficient in result.items():
                    assert c == 0
                    dest = column ^ a
                    actual[dest] = actual.get(dest, 0) + coefficient * (
                        -1 if (b & column).bit_count() & 1 else 1)
                assert {r: v for r, v in actual.items() if v} == expected


def test_seeded_hybrid_programs_match_all_matrix_units():
    rng = random.Random(14020261102)
    kinds = ["x", "cx", "ccx", "swap", "cswap", "z", "cz", "ccz",
             "hmr", "measure_z", "reset", "store", "invert", "oxor"]
    seen = set()
    for index in range(96):
        program = HybridProgram(2, 1).store("b0", index & 1).store("b1", (index >> 1) & 1)
        for _ in range(5):
            kind = rng.choice(kinds)
            seen.add(kind)
            a, b, c = rng.sample(range(3), 3)
            slot = rng.choice(("b0", "b1"))
            condition = rng.choice((None, "b0", "!b0", "b1", "!b1"))
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
            else:
                wires = (a,) if kind in {"x", "z"} else (
                    (a, b) if kind in {"cx", "cz", "swap"} else (a, b, c))
                getattr(program, kind)(*wires, condition=condition)
        _assert_oracle(program, 2)
    assert seen == set(kinds)


def test_wide_irrelevant_logic_is_validated_without_a_full_channel():
    program = HybridProgram(128, 1)
    for q in range(120):
        program.cx(q, (q + 1) % 128)
    program.cx(0, 128).cx(0, 128)
    result = check_clean_ancilla(program, 128)
    assert result.clean and result.checked_operations == 122
    assert result.peak_terms <= 4


def test_basis_witness_does_not_enumerate_all_inputs():
    result = check_clean_ancilla(HybridProgram(128, 1).cx(127, 128), 128)
    assert result.status == "not_clean"
    assert result.witness.assignment == 1 << 127
    assert result.witness.probability == 1


@pytest.mark.parametrize("limits", [AncillaLimits(max_width=2), AncillaLimits(max_operations=1),
                                    AncillaLimits(max_classical_slots=1),
                                    AncillaLimits(max_gate_qubits=1),
                                    AncillaLimits(max_products=1)])
def test_structural_and_work_caps_are_inconclusive(limits):
    program = HybridProgram(2, 1).store("b0", 0).store("b1", 0).cx(0, 2)
    result = check_clean_ancilla(program, 2, limits=limits)
    assert result.status == "inconclusive" and result.certificate is None and result.witness is None


@pytest.mark.parametrize("budget", [Budget(max_terms=1), Budget(max_seconds=1e-12),
                                    Budget(absolute_deadline=0)])
def test_term_and_time_caps_do_not_issue_a_certificate(budget):
    result = check_clean_ancilla(HybridProgram(1, 1), 1, budget=budget)
    assert result.status == "inconclusive" and result.certificate is None


@pytest.mark.parametrize("budget", [Budget(max_nodes=10), Budget(max_bytes=1000)])
def test_unsupported_resource_units_are_refused(budget):
    with pytest.raises(ValueError, match="node/byte"):
        check_clean_ancilla(HybridProgram(1, 1), 1, budget=budget)


def test_active_session_budget_is_inherited():
    with VerificationSession(Budget(max_terms=1)):
        assert check_clean_ancilla(HybridProgram(1, 1), 1).status == "inconclusive"


def test_mutated_instance_metadata_cannot_erase_declared_budgets():
    budget = Budget(max_terms=1)
    object.__setattr__(budget, "__dataclass_fields__", {})
    assert check_clean_ancilla(HybridProgram(1, 1), 1, budget=budget).status == "inconclusive"
    limits = AncillaLimits(max_width=1)
    object.__setattr__(limits, "__dataclass_fields__", {})
    assert check_clean_ancilla(HybridProgram(1, 1), 1, limits=limits).status == "inconclusive"


@pytest.mark.parametrize("replay", [False, True])
def test_final_deadline_includes_scratch_destruction(monkeypatch, replay):
    program = HybridProgram(1, 1)
    receipt = check_clean_ancilla(program, 1).certificate
    clock = [0.0]
    monkeypatch.setattr("symq.resources.time.perf_counter", lambda: clock[0])
    monkeypatch.setattr(ba._Work, "__del__", lambda self: clock.__setitem__(0, 2.0), raising=False)
    result = (replay_clean_ancilla(program, receipt, budget=Budget(max_seconds=1)) if replay else
              check_clean_ancilla(program, 1, budget=Budget(max_seconds=1)))
    assert clock[0] == 2.0
    assert result.status == "inconclusive" and result.certificate is None and result.witness is None


class _Str(str):
    pass


class _Int(int):
    pass


@pytest.mark.parametrize("field,value", [
    ("kind", _Str("x")), ("wires", (True,)), ("wires", (_Int(1),)),
    ("wires", [1]), ("slot", _Str("b0")), ("condition", _Str("b0")),
    ("source", _Str("b0")), ("value", True), ("value", _Int(1)),
    ("kind", "h"), ("wires", (2,)), ("condition", "b1"),
])
def test_strict_source_fields_refuse_malformed_frozen_operations(field, value):
    program = HybridProgram(1, 1).store("b0", 0).x(1)
    object.__setattr__(program.ops[-1], field, value)
    with pytest.raises((ValueError, TypeError, UnsupportedOperation)):
        check_clean_ancilla(program, 1)


@pytest.mark.parametrize("target", [True, _Int(1), 0, 2, -1])
def test_target_is_a_real_declared_ancilla(target):
    with pytest.raises(ValueError):
        check_clean_ancilla(HybridProgram(1, 1), target)


def test_snapshot_does_not_retain_mutable_builder_objects():
    program = HybridProgram(1, 1).cx(0, 1).cx(0, 1)
    guard, limits = ba._settings(None, None)
    work = ba._Work(guard, limits)
    frozen = ba._freeze(program, 1, work)
    object.__setattr__(program.ops[-1], "kind", "z")
    assert ba._effect(frozen, 1, work) == {}
    assert frozen.ops[-1].kind == "cx"


def test_source_bound_replay_recomputes_the_obligation(monkeypatch):
    program = HybridProgram(1, 1).cx(0, 1).cx(0, 1)
    receipt = check_clean_ancilla(program, 1).certificate
    assert replay_clean_ancilla(program, receipt).clean
    program.x(1)
    assert replay_clean_ancilla(program, receipt).status == "not_proved"
    # A forged hash matching the modified program cannot create a clean result.
    guard, limits = ba._settings(None, None)
    frozen = ba._freeze(program, 1, ba._Work(guard, limits))
    forged = replace(receipt, source_sha256=frozen.sha256, operations=3)
    result = replay_clean_ancilla(program, forged)
    assert result.status == "not_clean" and result.certificate is None


@pytest.mark.parametrize("field,value", [("data", True), ("target", 0), ("operations", -1),
                                        ("ancillas", _Int(1)), ("theorem", "v2"),
                                        ("source_sha256", "a" * 63), ("extra", 1)])
def test_edited_certificate_schema_is_not_a_proof(field, value):
    program = HybridProgram(1, 1)
    document = check_clean_ancilla(program, 1).certificate.to_dict()
    document[field] = value
    assert replay_clean_ancilla(program, document).status == "not_proved"


def test_incomplete_certificate_and_wrong_exact_mapping_types_are_refused():
    program = HybridProgram(1, 1)
    document = check_clean_ancilla(program, 1).certificate.to_dict()
    del document["operations"]
    assert replay_clean_ancilla(program, document).status == "not_proved"
    assert replay_clean_ancilla(program, []).status == "not_proved"


def test_replay_can_pin_the_consumer_target():
    program = HybridProgram(1, 2).cx(0, 1).cx(0, 1)
    receipt = check_clean_ancilla(program, 1).certificate.to_dict()
    edited = {**receipt, "target": 2}
    assert replay_clean_ancilla(program, edited).clean  # re-proves the named obligation
    refused = replay_clean_ancilla(program, edited, target=1)
    assert refused.status == "not_proved" and refused.reason == "certificate_target_mismatch"
    assert replay_clean_ancilla(program, receipt, target=1).clean
    for bad in (True, -1, 1.0):
        assert replay_clean_ancilla(program, receipt, target=bad).status == "not_proved"
