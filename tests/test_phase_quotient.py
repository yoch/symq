"""Phase certificates checked against scalar Boolean evaluation, including refusals."""
from __future__ import annotations

import copy
import random
import time
from dataclasses import replace

import pytest

from symq import Circuit, Gate
from symq.anf import ANF
from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.labs.phase_quotient import (
    PhaseQuotientCertificate,
    certificate_from_dict,
    certificate_to_dict,
    check_prefix_phase,
    replay_prefix_phase,
    verify_phase_identity,
)
from symq.resources import Budget, VerificationSession


def _product_certificate(k=3, constant=0):
    # z-ab = (1-2ab) lift(z XOR ab), including the -2abz cross term.
    modulus = 1 << k
    delta = {3: modulus - 1, 4: 1}
    if constant:
        delta[0] = constant
    multiplier = ((0, 1), (3, modulus - 2)) if k > 1 else ((0, 1),)
    return PhaseQuotientCertificate(3, k, tuple(sorted(delta.items())),
                                    (ANF(frozenset({3, 4})),), (multiplier,), constant)


def _eval(terms, assignment, modulus):
    return sum(coefficient for mask, coefficient in terms
               if (assignment & mask) == mask) % modulus


def _mobius(values, width, modulus):
    # Independent truth-table -> multilinear coefficients; valid over composite Z/M.
    coefficients = list(values)
    for bit in range(width):
        for mask in range(1 << width):
            if mask >> bit & 1:
                coefficients[mask] -= coefficients[mask ^ (1 << bit)]
    return tuple((mask, c % modulus) for mask, c in enumerate(coefficients) if c % modulus)


def _from_values(width, k, invariants, multipliers, constant=0):
    modulus = 1 << k
    values = [
        (constant + sum(_eval(q, x, modulus) * inv.evaluate(x)
                        for inv, q in zip(invariants, multipliers))) % modulus
        for x in range(1 << width)
    ]
    return PhaseQuotientCertificate(width, k, _mobius(values, width, modulus),
                                    tuple(invariants), tuple(multipliers), constant)


@pytest.mark.parametrize("k", [1, 2, 3, 4, 8, 64])
def test_exact_lift_is_required_over_each_dyadic_ring(k):
    certificate = _product_certificate(k)
    assert verify_phase_identity(certificate)
    for x in range(8):
        z, a, b = (x >> 2) & 1, x & 1, (x >> 1) & 1
        assert _eval(certificate.delta, x, 1 << k) == (z - a * b) % (1 << k)
    if k > 1:
        # Naively treating Boolean XOR as addition gives 2 at a=b=z=1.
        wrong_delta = ((3, 1), (4, 1))
        wrong = replace(certificate, delta=wrong_delta)
        assert not verify_phase_identity(wrong)
        assert _eval(wrong_delta, 7, 1 << k) == 2


def test_prove_relation_on_prefix_and_keep_dirty_inputs_arbitrary():
    prefix = Circuit(3).ccx(0, 1, 2)
    certificate = _product_certificate()
    result = check_prefix_phase(prefix, certificate, initial_constants=((2, 0),))
    assert result.outcome == "proved"
    assert result.constant == 0
    assert result.to_dict()["theorem"] == "dyadic_phase_constant_on_prefix_image"
    assert result.to_dict()["candidate_authorized"] is False
    for x in range(4):
        assert _eval(certificate.delta, prefix.run(x), 8) == 0

    dirty = check_prefix_phase(prefix, certificate)
    assert dirty.outcome == "not_proved"
    assert dirty.constant is None
    assert dirty.violating_invariant == 0
    assert dirty.witness is not None
    assert certificate.invariants[0].evaluate(prefix.run(dirty.witness)) == 1
    assert _eval(certificate.delta, prefix.run(dirty.witness), 8) != 0


def test_known_one_input_is_replayed_with_its_actual_value():
    certificate = PhaseQuotientCertificate(2, 3, ((0, 1), (1, 7)),
                                          (ANF(frozenset({0, 1})),), (((0, 1),),))
    prefix = Circuit(2)
    good = check_prefix_phase(prefix, certificate, initial_constants=((0, 1),))
    assert good.outcome == "proved"
    bad = check_prefix_phase(prefix.x(0), certificate, initial_constants=((0, 1),))
    assert bad.outcome == "not_proved"
    assert bad.witness == 1
    assert bad.witness & 1 == 1
    assert prefix.run(bad.witness) & 1 == 0


def test_nonzero_constant_is_reported_and_never_authorizes_controlled_rewrite():
    certificate = _product_certificate(constant=5)
    result = check_prefix_phase(Circuit(3).ccx(0, 1, 2), certificate,
                                initial_constants=((2, 0),))
    assert result.outcome == "proved" and result.constant == 5
    assert result.to_dict()["candidate_authorized"] is False


def test_invalid_identity_is_not_an_inequivalence_verdict():
    certificate = replace(_product_certificate(), multipliers=((),))
    result = check_prefix_phase(Circuit(3).ccx(0, 1, 2), certificate,
                                initial_constants=((2, 0),))
    # The phase is still zero on this prefix image, but this particular certificate fails.
    assert result.outcome == "not_proved"
    assert result.reason == "polynomial identity mismatch"
    assert result.witness is None


def test_nonempty_domain_is_required_and_unused_false_relations_are_not_certified():
    impossible = PhaseQuotientCertificate(1, 3, (), (ANF.constant(1),), ((),))
    assert verify_phase_identity(impossible)  # Conditional algebra alone is vacuous.
    result = check_prefix_phase(Circuit(1), impossible)
    assert result.outcome == "not_proved"
    assert result.witness == 0
    with pytest.raises(ValueError, match="distinct"):
        check_prefix_phase(Circuit(3), _product_certificate(),
                           initial_constants=((2, 0), (2, 1)))


def test_all_two_variable_boolean_relations_against_modular_truth_tables():
    # Every two-variable Boolean relation and every Boolean coefficient vector
    # (embedded in Z/8); the oracle never uses the checker's polynomial operations.
    for relation_bits in range(16):
        relation = ANF(frozenset(m for m in range(4) if relation_bits >> m & 1))
        for q_bits in range(16):
            multiplier = tuple((m, 1) for m in range(4) if q_bits >> m & 1)
            certificate = _from_values(2, 3, (relation,), (multiplier,), constant=3)
            assert verify_phase_identity(certificate)
            for x in range(4):
                assert _eval(certificate.delta, x, 8) == (
                    3 + relation.evaluate(x) * _eval(multiplier, x, 8)) % 8
            changed = dict(certificate.delta)
            changed[0] = (changed.get(0, 0) + 1) % 8
            mutant = replace(certificate, delta=tuple(sorted((m, c) for m, c in changed.items()
                                                             if c)))
            assert not verify_phase_identity(mutant)


def test_seeded_multirelation_certificates_and_mutants_against_scalar_oracle():
    rng = random.Random(20261101)
    for width in range(1, 5):
        for _ in range(40):
            k = rng.randrange(1, 5)
            modulus = 1 << k
            invariants = tuple(ANF(frozenset(m for m in range(1 << width)
                                            if rng.randrange(4) == 0)) for _ in range(3))
            multipliers = tuple(tuple((m, c) for m in range(1 << width)
                                      if (c := rng.randrange(modulus))) for _ in range(3))
            certificate = _from_values(width, k, invariants, multipliers,
                                        rng.randrange(modulus))
            assert verify_phase_identity(certificate)
            mutation = dict(certificate.delta)
            mask = rng.randrange(1 << width)
            mutation[mask] = (mutation.get(mask, 0) + 1) % modulus
            mutant = replace(certificate, delta=tuple(sorted((m, c) for m, c in mutation.items()
                                                             if c)))
            assert not verify_phase_identity(mutant)


def test_seeded_prefix_obligations_against_all_legal_scalar_inputs():
    rng = random.Random(20261102)
    for width in range(2, 6):
        for _ in range(12):
            prefix = Circuit(width)
            for _ in range(8):
                wires = rng.sample(range(width), rng.randrange(1, min(3, width) + 1))
                prefix.append({1: "x", 2: "cx", 3: "ccx"}[len(wires)], *wires)
            wire, bit = rng.randrange(width), rng.randrange(2)
            inverse = prefix.inverse().symbolic()[wire] ^ ANF.constant(bit)
            certificate = _from_values(width, 3, (inverse,), (((0, 3),),), constant=2)
            result = check_prefix_phase(prefix, certificate, initial_constants=((wire, bit),))
            assert result.outcome == "proved"
            for x in range(1 << width):
                if x >> wire & 1 == bit:
                    assert _eval(certificate.delta, prefix.run(x), 8) == 2
            wrong = check_prefix_phase(prefix, certificate, initial_constants=((wire, bit ^ 1),))
            assert wrong.outcome == "not_proved"
            assert wrong.witness is not None
            assert wrong.witness >> wire & 1 == bit ^ 1
            assert inverse.evaluate(prefix.run(wrong.witness)) == 1


def test_roundtrip_and_replay_bind_source_certificate_and_contract():
    certificate = _product_certificate()
    encoded = certificate_to_dict(certificate)
    assert certificate_from_dict(encoded) == certificate
    prefix = Circuit(3).ccx(0, 1, 2)
    constants = ((2, 0),)
    result = check_prefix_phase(prefix, certificate, initial_constants=constants)
    receipt = result.to_dict()
    assert replay_prefix_phase(prefix, certificate, receipt,
                                initial_constants=constants) == result
    # Same function, different gate stream: proof provenance cannot be relabelled.
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_prefix_phase(prefix.x(0).x(0), certificate, receipt,
                             initial_constants=constants)
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_prefix_phase(Circuit(3).ccx(0, 1, 2), certificate, receipt)
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_prefix_phase(Circuit(3).ccx(0, 1, 2), _product_certificate(constant=1), receipt,
                             initial_constants=constants)
    for field, replacement in [("schema_version", True), ("constant", False),
                               ("theorem", "full_channel"), ("candidate_authorized", True),
                               ("witness", 0), ("prefix_sha256", "0" * 64)]:
        mutated = {**receipt, field: replacement}
        with pytest.raises(ValueError, match="receipt mismatch"):
            replay_prefix_phase(Circuit(3).ccx(0, 1, 2), certificate, mutated,
                                 initial_constants=constants)


@pytest.mark.parametrize("change", [
    {"width": True}, {"width": 0}, {"width": 257}, {"k": True}, {"k": 0}, {"k": 65},
    {"constant": True}, {"constant": -1}, {"constant": 8},
    {"delta": ((3, 0),)}, {"delta": ((3, -1),)}, {"delta": ((3, 8),)},
    {"delta": ((True, 1),)}, {"delta": ((3, True),)}, {"delta": ((8, 1),)},
    {"delta": ((4, 1), (3, 7))}, {"delta": ((3, 7), (3, 1))},
    {"delta": [(3, 7), (4, 1)]}, {"multipliers": ()},
    {"invariants": (ANF(frozenset({8})),)},
])
def test_malformed_certificate_never_yields_a_verdict(change):
    with pytest.raises((TypeError, ValueError)):
        verify_phase_identity(replace(_product_certificate(), **change))


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2), ("kind", "other"),
    ("invariants", [[4, 3]]), ("invariants", [[3, 3]]), ("invariants", [[True, 4]]),
    ("delta", [[3, 7, 1]]), ("multipliers", []), ("extra", 1),
])
def test_strict_json_rejects_ambiguous_or_extended_data(field, value):
    data = copy.deepcopy(certificate_to_dict(_product_certificate()))
    data[field] = value
    with pytest.raises(ValueError):
        certificate_from_dict(data)


@pytest.mark.parametrize("constants", [((2, True),), ((True, 0),), ((3, 0),),
                                        ((2, 0), (2, 0)), [(2, 0)]])
def test_invalid_initial_constants_are_not_weakened(constants):
    with pytest.raises(ValueError):
        check_prefix_phase(Circuit(3), _product_certificate(), initial_constants=constants)


def test_prefix_is_revalidated_even_after_frozen_gate_tampering():
    prefix = Circuit(3).ccx(0, 1, 2)
    object.__setattr__(prefix.gates[0], "name", "h")
    with pytest.raises(UnsupportedOperation):
        check_prefix_phase(prefix, _product_certificate(), initial_constants=((2, 0),))


def test_gate_name_subclass_cannot_disagree_with_its_serialized_operation():
    class MasqueradingName(str):
        def __hash__(self):
            return hash("x")

        def __eq__(self, other):
            return other == "x"

    certificate = PhaseQuotientCertificate(1, 3, ((1, 1),),
                                          (ANF(frozenset({0, 1})),), (((0, 7),),), constant=1)
    valid = check_prefix_phase(Circuit(1).x(0), certificate, initial_constants=((0, 0),))
    assert valid.outcome == "proved"
    prefix = Circuit(1, [Gate(MasqueradingName("h"), (0,))])
    with pytest.raises(ValueError, match="plain strings and tuples"):
        check_prefix_phase(prefix, certificate, initial_constants=((0, 0),))
    gate = Gate("x", (0,))
    object.__setattr__(gate, "qubits", [0])
    with pytest.raises(ValueError, match="plain strings and tuples"):
        check_prefix_phase(Circuit(1, [gate]), certificate, initial_constants=((0, 0),))


def test_empty_certificate_establishes_only_a_constant_phase():
    certificate = PhaseQuotientCertificate(2, 3, ((0, 6),), (), (), constant=6)
    assert verify_phase_identity(certificate)
    result = check_prefix_phase(Circuit(2).cx(0, 1), certificate)
    assert result.outcome == "proved" and result.constant == 6


def test_resource_guards_cover_inputs_lifts_and_whole_call():
    with pytest.raises(ResourceLimitExceeded):
        verify_phase_identity(_product_certificate(), Budget(max_terms=6))
    parity = ANF(frozenset({1, 2, 4, 8}))
    # Identical lifts cancel eventually, but each has 15 terms modulo 16.
    cancellation = PhaseQuotientCertificate(4, 4, (), (parity, parity),
                                            (((0, 1),), ((0, 15),)))
    assert verify_phase_identity(cancellation)
    with pytest.raises(ResourceLimitExceeded):
        verify_phase_identity(cancellation, Budget(max_terms=12))
    with pytest.raises(ResourceLimitExceeded):
        certificate_from_dict(certificate_to_dict(cancellation), Budget(max_terms=11))
    with pytest.raises(ResourceLimitExceeded):
        check_prefix_phase(Circuit(3), _product_certificate(),
                           Budget(absolute_deadline=time.perf_counter() - 1))
    with pytest.raises(ResourceLimitExceeded), VerificationSession(Budget(max_terms=6)):
        verify_phase_identity(_product_certificate(), Budget(max_terms=1000))
    for budget in (Budget(max_nodes=100), Budget(max_bytes=1000)):
        with pytest.raises(ValueError, match="max_nodes/max_bytes"):
            verify_phase_identity(_product_certificate(), budget)


def test_mid_computation_deadline_cannot_return_a_partial_proof(monkeypatch):
    from symq.resources import Guard

    original = Guard.check_time
    checks = 0

    def interrupt(self):
        nonlocal checks
        checks += 1
        if checks == 30:
            raise ResourceLimitExceeded("seconds", 1, 2)
        original(self)

    monkeypatch.setattr(Guard, "check_time", interrupt)
    with pytest.raises(ResourceLimitExceeded):
        check_prefix_phase(Circuit(3).ccx(0, 1, 2), _product_certificate(),
                           initial_constants=((2, 0),))


def test_authenticated_public_prefix_and_adverse_cases_have_scalar_evidence():
    from benchmarks.phase_quotient import run

    evidence = run(repetitions=1)
    assert evidence["fixture"]["commit"] == "638777fac4379bc62e2a1e4a52cf1a1753895d48"
    assert evidence["fixture"]["license"] == "Apache-2.0"
    assert [row["outcome"] for row in evidence["cases"]] == [
        "proved", "not_proved", "not_proved", "not_proved",
    ]
    positive = evidence["cases"][0]
    assert positive["oracle"] == {"inputs": 256, "invariant_violations": 0,
                                   "phase_differences": 0, "phases": [0]}
    for row in evidence["cases"][1:]:
        assert row["oracle"]["phase_differences"] > 0
        assert row["receipt"]["candidate_authorized"] is False
