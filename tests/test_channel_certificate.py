"""Exact one-copy certificates against independent outcome/Kraus enumeration."""
from __future__ import annotations

import copy
import json
import random
import time
from dataclasses import replace
from pathlib import Path

import pytest
from testkit.scalar_channel import channel_matrix

from symq.circuit import UnsupportedOperation
from symq.experimental.channel import check_channel
from symq.kickmix import load_kmx
from symq.labs.channel_certificate import (
    CertificateLimits,
    discover_certificate,
    verify_certificate,
)
from symq.labs.qualtran import load_qualtran_fixture
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, VerificationSession

ROOT = Path(__file__).resolve().parents[1]


def _program(data, signatures, phase=()):
    """Real gates computing each ANF into one clean measured scratch wire."""
    result = PhaseProgram(data, 1)
    for signature in signatures:
        for mask in signature:
            result.mcx(*(i for i in range(data) if mask >> i & 1), data)
        result.hmr(data)
    for mask in phase:
        if mask:
            result.mcz(*(i for i in range(data) if mask >> i & 1))
        else:
            # A global minus sign with the scratch wire returned to zero.
            result.x(data).z(data).x(data)
    return result


def _pair(phase=(3,)):
    return _program(3, [(1,), (2,)]), _program(3, [(1,), (2,), (3,)], phase)


def _certificate(left, right):
    result = discover_certificate(left, right)
    assert result.equivalent, result.reason
    assert result.certificate is not None
    return result.certificate


@pytest.mark.parametrize("table", range(16))
def test_every_two_feature_phase_on_nonlinearly_redundant_signature(table):
    phase = tuple(mask for mask in range(4) if table >> mask & 1)
    left, right = _pair(phase)
    certificate = _certificate(left, right)
    assert len(certificate.left_selectors) == 2
    assert certificate.right_reconstruction[-1] == (3,)
    assert verify_certificate(left, right, certificate).equivalent
    assert verify_certificate(left, right, json.loads(json.dumps(certificate.to_dict()))).equivalent
    # All matrix units, including off-diagonal coherences and retained ancillas.
    assert channel_matrix(left) == channel_matrix(right)


def test_nonlinear_bijection_needs_a_nonlinear_inverse():
    left = _program(4, [(1,), (2,), (4,)])
    right = _program(4, [(1,), (2,), (3, 4)], (3,))
    result = discover_certificate(left, right)
    assert result.equivalent
    assert result.certificate.signature_from_right[-1] == (3, 4)
    assert channel_matrix(left) == channel_matrix(right)
    limited = discover_certificate(left, right, degree=1)
    assert limited.outcome == "not_proved"
    assert limited.certificate is None


def test_left_redundancies_constant_outcomes_and_global_phase():
    left = _program(3, [(0,), (), (1,), (2,), (3,)])
    right = _program(3, [(1,), (2,)], (0, 3))
    certificate = _certificate(left, right)
    assert certificate.left_selectors == (2, 3)
    assert channel_matrix(left) == channel_matrix(right)


def test_fully_corrected_feedback_has_an_empty_signature():
    left = PhaseProgram(3, 1)
    right = PhaseProgram(3, 1).ccx(0, 1, 3)
    event = right.hmr(3)
    right.cz_if(event, 0, 1)
    certificate = _certificate(left, right)
    assert certificate.left_selectors == ()
    assert certificate.right_reconstruction == ((),)
    assert channel_matrix(left) == channel_matrix(right)


def test_seeded_valid_programs_include_measured_data_and_arbitrary_feedback():
    rng = random.Random(20261101)
    for _ in range(24):
        left = PhaseProgram(2, 1)
        for _ in range(5):
            kind = rng.choice(("mcx", "mcz", "hmr", "mcz_if"))
            wires = rng.sample(range(3), rng.randint(1, 3))
            if kind == "hmr":
                left.hmr(wires[0])
            elif kind == "mcz_if" and left.measurements:
                left.mcz_if(rng.randrange(left.measurements), *wires)
            elif kind == "mcx":
                left.mcx(*wires)
            else:
                left.mcz(*wires)
        right = PhaseProgram(2, 1, list(left.ops)).cx(0, 2).cx(0, 2)
        assert discover_certificate(left, right).equivalent
        assert channel_matrix(left) == channel_matrix(right)


def test_seeded_two_event_pairs_match_the_independent_channel_oracle():
    # With at most two selected features, the degree-two dictionary contains
    # every Boolean feature function. This bounded subfamily is complete.
    rng = random.Random(904937)
    accepted = 0
    for _ in range(128):
        polynomials = [tuple(mask for mask in range(4) if rng.getrandbits(1))
                       for _ in range(5)]
        left = _program(2, polynomials[:2])
        right = _program(2, polynomials[2:4], polynomials[4])
        expected = channel_matrix(left) == channel_matrix(right)
        result = discover_certificate(left, right)
        assert result.equivalent == expected
        assert result.outcome in {"equivalent", "not_proved"}
        accepted += result.equivalent
    assert 0 < accepted < 128


@pytest.mark.parametrize("mutation", ["extra_leak", "lost_reverse", "phase", "output"])
def test_inequivalent_mutants_never_become_negative_verdicts(mutation):
    if mutation == "extra_leak":
        left, right = _program(3, [(1,)]), _program(3, [(1,), (2,)])
    elif mutation == "lost_reverse":
        left, right = _program(3, [(1,), (2,)]), _program(3, [(1,)])
    elif mutation == "phase":
        left, right = _pair((4,))  # spectator phase remains visible
    else:
        left, right = _pair()
        right.x(2)
    assert channel_matrix(left) != channel_matrix(right)
    result = discover_certificate(left, right)
    assert result.outcome == "not_proved"
    assert result.certificate is None


def test_reversed_dependency_is_checked_even_with_correct_source_digests():
    left = _program(3, [(1,), (2,)])
    right = _program(3, [(1,)])
    lcert, rcert = _certificate(left, left), _certificate(right, right)
    forged = replace(
        lcert, right_sha256=rcert.right_sha256,
        right_reconstruction=((1,),), signature_from_right=((1,), ()),
    )
    result = verify_certificate(left, right, forged)
    assert result.outcome == "not_proved"
    assert "reverse reconstruction" in result.reason


def test_omitting_a_coordinate_cannot_remove_leakage_or_an_output():
    left, right = _pair()
    cert = _certificate(left, right)
    assert verify_certificate(left, right, replace(
        cert, right_reconstruction=cert.right_reconstruction[:-1],
    )).outcome == "not_proved"
    # A dirty final ancilla matters to the full-channel contract.
    right.x(3)
    new_pin = _certificate(right, right).right_sha256
    result = verify_certificate(left, right, replace(cert, right_sha256=new_pin))
    assert result.outcome == "not_proved"
    assert "full output" in result.reason


def test_canonical_source_binding_is_rechecked_after_program_changes():
    left, right = _pair()
    cert = _certificate(left, right)
    right.x(2).x(2)  # Same channel, different source: rediscovery is required.
    result = verify_certificate(left, right, cert)
    assert result.outcome == "not_proved"
    assert "digest" in result.reason
    assert discover_certificate(left, right).equivalent


def test_every_reconstruction_and_phase_coordinate_is_checked():
    left, right = _pair()
    doc = _certificate(left, right).to_dict()
    count = 0
    for field in ("left_reconstruction", "right_reconstruction", "signature_from_right"):
        for index in range(len(doc[field])):
            mutant = copy.deepcopy(doc)
            terms = set(mutant[field][index])
            terms.symmetric_difference_update((0,))
            mutant[field][index] = sorted(terms)
            assert verify_certificate(left, right, mutant).outcome == "not_proved"
            count += 1
    mutant = copy.deepcopy(doc)
    mutant["phase_function"] = sorted(set(mutant["phase_function"]) ^ {0})
    assert verify_certificate(left, right, mutant).outcome == "not_proved"
    assert count == 7


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 1.0), ("schema_version", 2),
    ("theorem", "reduced_channel"), ("left_sha256", "0" * 64),
    ("right_sha256", "g" * 64), ("left_selectors", [True, 1]),
    ("left_selectors", [0, 0]), ("left_selectors", [-1, 1]),
    ("left_selectors", [0, 200]), ("left_selectors", (0, 1)),
    ("phase_function", [True]), ("phase_function", [1.0]),
    ("phase_function", [-1]), ("phase_function", [3, 3]),
    ("phase_function", [3, 0]), ("phase_function", [4]),
    ("phase_function", [1 << 256]), ("phase_function", None),
    ("left_reconstruction", None), ("signature_from_right", [None]),
])
def test_malformed_or_out_of_frame_certificates_fail_closed(field, value):
    left, right = _pair()
    document = _certificate(left, right).to_dict()
    document[field] = value
    result = verify_certificate(left, right, document)
    assert result.outcome == "not_proved"
    assert result.certificate is None


def test_unknown_fields_missing_fields_and_forged_typed_versions_are_rejected():
    left, right = _pair()
    cert = _certificate(left, right)
    document = cert.to_dict()
    document["trace_ancillas"] = True
    assert verify_certificate(left, right, document).outcome == "not_proved"
    del document["trace_ancillas"]
    del document["signature_from_right"]
    assert verify_certificate(left, right, document).outcome == "not_proved"
    assert verify_certificate(left, right, replace(cert, schema_version=True)).outcome == "not_proved"
    with pytest.raises(TypeError):
        verify_certificate(left, right, cert, trace_ancillas=True)


@pytest.mark.parametrize("limits", [
    CertificateLimits(max_width=3), CertificateLimits(max_operations=1),
    CertificateLimits(max_events=1), CertificateLimits(max_dictionary_terms=2),
    CertificateLimits(max_certificate_terms=1), CertificateLimits(max_certificate_bytes=1),
])
def test_structural_resource_exhaustion_returns_no_certificate(limits):
    left, right = _pair()
    result = discover_certificate(left, right, limits=limits)
    assert result.outcome == "inconclusive"
    assert result.certificate is None


def test_checker_and_discovery_share_term_and_deadline_guards():
    left = PhaseProgram(2).cx(0, 1)
    result = discover_certificate(left, left, budget=Budget(max_terms=1))
    assert result.outcome == "inconclusive"
    left, right = _pair()
    cert = _certificate(left, right)
    expired = Budget(absolute_deadline=time.perf_counter() - 1)
    for call in (lambda: discover_certificate(left, right, budget=expired),
                 lambda: verify_certificate(left, right, cert, budget=expired)):
        result = call()
        assert result.outcome == "inconclusive"
        assert result.certificate is None
    result = verify_certificate(left, right, cert, limits=CertificateLimits(max_certificate_bytes=1))
    assert result.outcome == "inconclusive"


def test_wrong_budget_units_invalid_limits_and_degree_are_not_silently_ignored():
    left, right = _pair()
    for budget in (Budget(max_nodes=10), Budget(max_bytes=10)):
        with pytest.raises(ValueError, match="terms/time"):
            discover_certificate(left, right, budget=budget)
    for value in (True, 0, -1, 1.0):
        with pytest.raises(ValueError):
            CertificateLimits(max_events=value)
    for degree in (True, -1, 1.0):
        with pytest.raises(ValueError):
            discover_certificate(left, right, degree=degree)
    with VerificationSession(Budget(max_nodes=10)), pytest.raises(ValueError, match="terms/time"):
        discover_certificate(left, right)


def test_mutable_program_dimensions_and_unknown_grammar_are_validated():
    left, right = _pair()
    cert = _certificate(left, right)
    for name, value in (("data", True), ("ancillas", -1)):
        changed = copy.deepcopy(right)
        setattr(changed, name, value)
        with pytest.raises(ValueError):
            verify_certificate(left, changed, cert)
    changed = copy.deepcopy(right)
    changed.ops.append(Op("h", (0,)))
    with pytest.raises(UnsupportedOperation):
        verify_certificate(left, changed, cert)
    changed = copy.deepcopy(right)
    changed.ops.append(Op("hmr", (0,), False))
    with pytest.raises(UnsupportedOperation):
        verify_certificate(left, changed, cert)


def test_outcome_integer_subclasses_cannot_conceal_a_nonfresh_measurement():
    class FalseIndex(int):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

    good = PhaseProgram(1)
    good.hmr(0)
    bad = PhaseProgram(1, 0, [Op("hmr", (0,), FalseIndex(1))])
    # The legacy PhaseProgram validator accepts this deceptive integer subclass.
    # Using its underlying value in an independent outcome oracle changes the map.
    assert channel_matrix(good) != channel_matrix(bad)
    cert = _certificate(good, good)
    with pytest.raises(UnsupportedOperation, match="exact integers"):
        discover_certificate(good, bad)
    with pytest.raises(UnsupportedOperation, match="exact integers"):
        verify_certificate(good, bad, cert)

    feedback = PhaseProgram(1, 1).cx(0, 1)
    feedback.hmr(1)
    feedback.ops.append(Op("mcz_if", (0,), FalseIndex(0)))
    with pytest.raises(UnsupportedOperation, match="exact integers"):
        discover_certificate(feedback, feedback)


@pytest.mark.parametrize("entrypoint", ["verify", "discover"])
def test_semantic_cleanup_is_inside_the_final_deadline(entrypoint, monkeypatch):
    import symq.labs.channel_certificate as module

    program = PhaseProgram(1)
    certificate = _certificate(program, program)
    clock = [0.0]

    def release(self):
        # Deterministic analogue of a slow sparse-state destructor: time advances
        # only when temporary semantic states are released, after _check returns.
        clock[0] += 2.0

    monkeypatch.setattr(time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(module._Semantics, "__del__", release, raising=False)
    if entrypoint == "verify":
        result = verify_certificate(program, program, certificate, budget=Budget(max_seconds=1))
    else:
        result = discover_certificate(program, program, budget=Budget(max_seconds=1))
    assert clock[0] >= 4
    assert result.outcome == "inconclusive"
    assert result.certificate is None


@pytest.mark.parametrize("name", ["inc8", "qualtran_m1", "qualtran_m2"])
def test_public_corrected_examples_and_removed_feedback(name):
    if name == "inc8":
        right = load_kmx(ROOT / "benchmarks/corpus/kickmix/inc8.kmx").to_phase_program(range(8))
        left = PhaseProgram(8, right.ancillas)
        for target in reversed(range(8)):
            left.mcx(*range(target), target)
    else:
        degree = int(name[-1])
        path = ROOT / f"benchmarks/corpus/qualtran/gf2mul_mbuc_m{degree}.json"
        left, right = load_qualtran_fixture(path).programs()
    cert = _certificate(left, right)
    assert cert.left_selectors == ()
    assert all(not expression for expression in cert.right_reconstruction)
    assert check_channel(left, right, backend="zdd").equivalent
    mutant = PhaseProgram(right.data, right.ancillas, list(right.ops))
    index = max(i for i, op in enumerate(mutant.ops) if op.kind == "mcz_if")
    del mutant.ops[index]
    assert discover_certificate(left, mutant).outcome == "not_proved"
    assert not check_channel(left, mutant, backend="zdd").equivalent
    if name != "inc8":
        assert channel_matrix(left) == channel_matrix(right)
        assert channel_matrix(left) != channel_matrix(mutant)


def test_bounded_reproduction_includes_public_zero_signatures_and_all_failures():
    from benchmarks.channel_certificate import run

    report = run(repetitions=1)
    assert len(report["records"]) == 14
    for row in report["records"]:
        trial = row["trials"][0]
        assert trial["outcome"] == row["expected_search_outcome"]
        if trial["outcome"] == "equivalent":
            assert trial["fresh_check_outcome"] == "equivalent"
    assert {row["trials"][0]["selected_features"] for row in report["records"]
            if row["id"] in {"inc8", "qualtran_m1", "qualtran_m2"}} == {0}
    assert len(report["fixture_sha256"]) == 3
    assert "labs/channel_certificate.py" in report["package_python_source_sha256"]
