"""Pinned GF24 full-input transcript proof, immutable application and refusal tests.

No SAT is used at 72 wires; the bounded degree-two packed ANF engine
decides equality of the *actual local reversible gate streams*.
"""
from __future__ import annotations

import random
from dataclasses import replace

import pytest

from symq import Budget, Circuit
from symq.errors import ResourceLimitExceeded
from symq.generators.gf2n import emit, karatsuba, schoolbook, tower_multiplier
from symq.labs.classical_transcript import (
    Common,
    Program,
    Slot,
    UnprovedSubstitution,
    digest,
    verify_transcript,
)
from symq.labs.gf24_verified_rewrite import (
    GF24AppliedRewrite,
    GF24GateWeights,
    apply_gf24_rewrite,
    replay_gf24_rewrite,
)

pytestmark = pytest.mark.slow

WIDTH = 76
WIRES = tuple(range(2, 74))
SPAN_INPUTS = (74, 75)
PROOF_BUDGET = Budget(max_seconds=40, max_terms=4000)


def _context() -> tuple[Circuit, tuple[int, int]]:
    old = emit(24, karatsuba(24), strategy="pivot-scheduled").circuit
    mapped = [(gate.name, tuple(WIRES[q] for q in gate.qubits)) for gate in old.gates]
    prefix = Circuit(WIDTH).cx(0, 2).cx(6, 74).cx(6, 74).cx(75, 14)
    block = Circuit(WIDTH)
    for name, qubits in mapped:
        block.append(name, *qubits)
    suffix = Circuit(WIDTH).cx(73, 1).ccx(14, 39, 75).cx(75, 0)
    source = Circuit(WIDTH, prefix.gates + block.gates + suffix.gates)
    span = (len(prefix.gates), len(prefix.gates) + len(block.gates))
    return source, span


def test_gf24_packed_contextual_total_permutation_and_frozen_apply():
    source, span = _context()
    applied = apply_gf24_rewrite(
        source, span, wires=WIRES, preserved=SPAN_INPUTS,
        weights=GF24GateWeights(ccx=32, cx=1), budget=PROOF_BUDGET,
    )
    assert type(applied) is GF24AppliedRewrite
    assert applied.theorem == "classical-total-permutation-packed-anf"
    assert applied.proof.backend == "packed"
    assert applied.proof.equivalent
    assert applied.proof.slots == applied.proof.unique_lemmas == 1
    assert applied.original_sha256 == digest(Program.freeze(source))
    assert applied.candidate_sha256 == digest(applied.candidate)
    assert (applied.cost.before_ccx, applied.cost.before_cx) == (162, 1856)
    assert (applied.cost.after_ccx, applied.cost.after_cx) == (99, 2646)
    assert (applied.cost.before_weighted, applied.cost.after_weighted,
            applied.cost.delta) == (7040, 5814, -1226)

    rng = random.Random(20261101)
    expected = applied.candidate.circuit()
    for x in [0, (1 << WIDTH) - 1, *[rng.getrandbits(WIDTH) for _ in range(32)]]:
        assert source.run(x) == expected.run(x)

    # The caller's mutable original is irrelevant after freezing.
    source.x(1)
    assert digest(applied.candidate) == applied.candidate_sha256
    with pytest.raises(ValueError, match="differs"):
        replay_gf24_rewrite(applied, source, budget=PROOF_BUDGET)


def test_fresh_replay_rejects_altered_weights_and_fake_hash():
    source, span = _context()
    real = apply_gf24_rewrite(
        source, span, wires=WIRES, weights=GF24GateWeights(ccx=32, cx=1),
        budget=PROOF_BUDGET,
    )
    replayed = replay_gf24_rewrite(real, source, budget=PROOF_BUDGET)
    assert replayed.candidate_sha256 == real.candidate_sha256
    assert replayed.proof.backend == "packed"

    forged_cost = replace(real.cost, delta=-99999)
    forged = replace(real, cost=forged_cost)
    with pytest.raises(ValueError, match="differs"):
        replay_gf24_rewrite(forged, source, budget=PROOF_BUDGET)
    with pytest.raises(ValueError, match="fingerprints disagree"):
        replace(real, candidate_sha256="0" * 64)


def test_negative_cost_policy_and_untrusted_wire_maps():
    source, span = _context()
    for wires in (WIRES[:-1], WIRES[:-1] + (WIRES[-2],),
                  tuple(list(WIRES[:-1]) + [WIDTH])):
        with pytest.raises(ValueError, match="72 unique"):
            apply_gf24_rewrite(
                source, span, wires=wires, weights=GF24GateWeights(ccx=32, cx=1),
            )
    with pytest.raises(ValueError, match="strict reduction"):
        apply_gf24_rewrite(
            source, span, wires=WIRES, weights=GF24GateWeights(ccx=1, cx=1),
        )
    with pytest.raises(ValueError, match="method"):
        apply_gf24_rewrite(
            source, span, wires=WIRES, method="unreviewed-search",
            weights=GF24GateWeights(ccx=32, cx=1),
        )
    for invalid in (GF24GateWeights, "32", 0):
        with pytest.raises(TypeError, match="GF24GateWeights"):
            apply_gf24_rewrite(source, span, wires=WIRES, weights=invalid)
    with pytest.raises(ValueError, match="resource limits"):
        apply_gf24_rewrite(
            source, span, wires=WIRES, weights=GF24GateWeights(ccx=32, cx=1),
            budget=Budget(max_seconds=30, max_bytes=1024),
        )


def test_negative_mutant_rejected_by_actual_gate_stream():
    source, span = _context()
    # A real mutant inside the original span: the proposed multiplier should
    # not be accepted even if its factor tensor is perfectly certified.
    mutated = Circuit(source.width, list(source.gates))
    target = next(i for i in range(*span) if mutated.gates[i].name == "ccx")
    del mutated.gates[target]
    with pytest.raises(UnprovedSubstitution):
        apply_gf24_rewrite(
            mutated, (span[0], span[1] - 1),
            wires=WIRES, weights=GF24GateWeights(ccx=32, cx=1),
            budget=PROOF_BUDGET,
        )


def test_preserved_cut_wires_are_separate_mandatory_obligations():
    source, span = _context()
    # Within the local block both reference and replacement must restore
    # the selected cut wires independently, not merely agree on them.
    mutated = Circuit(source.width, list(source.gates))
    mutated.gates.insert(span[1], Circuit(WIDTH).cx(2, 74).gates[0])
    with pytest.raises(UnprovedSubstitution):
        apply_gf24_rewrite(
            mutated, (span[0], span[1] + 1), wires=WIRES,
            preserved=(74,), weights=GF24GateWeights(ccx=32, cx=1),
            budget=PROOF_BUDGET,
        )


def test_polynomial_degree_guard_refuses_unadmitted_program():
    source, span = _context()
    # Generate a cubic after the original multiplication: output bit 50
    # contains quadratic factors, and multiplying it by input 2 is cubic.
    mutated = Circuit(source.width, list(source.gates))
    extra = Circuit(WIDTH).ccx(50, 2, 1).gates[0]
    mutated.gates.insert(span[1], extra)
    with pytest.raises(ResourceLimitExceeded, match="degree"):
        apply_gf24_rewrite(
            mutated, (span[0], span[1] + 1), wires=WIRES,
            weights=GF24GateWeights(ccx=32, cx=1), budget=PROOF_BUDGET,
        )


def test_exact_packed_and_zdd_agree_on_smaller_multiplier():
    ref = emit(4, schoolbook(4)).circuit
    cand = tower_multiplier(4, modulus=0x13)
    reference, candidate = Program.freeze(ref), Program.freeze(cand)
    slot = Slot(reference, candidate, tuple(range(12)))
    for engine in ("packed", "zdd"):
        checked = verify_transcript(
            ref, cand, (Common(()), slot, Common(())),
            reference_sha256=digest(reference), candidate_sha256=digest(candidate),
            backend=engine, budget=Budget(max_seconds=20),
        )
        assert checked.equivalent


@pytest.mark.parametrize("weights", [
    (True, 1), (1, False), (-1, 1), (0, 0), (2.0, 1),
])
def test_weight_validation_is_not_a_boolean_or_float_backdoor(weights):
    with pytest.raises(ValueError, match="weights"):
        GF24GateWeights(ccx=weights[0], cx=weights[1])
