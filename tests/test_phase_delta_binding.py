"""Program phase differences bound to proven prefix images, against an independent oracle."""
from __future__ import annotations

import random
import time
from dataclasses import replace
from fractions import Fraction

import pytest

from symq import Circuit, Gate
from symq.anf import ANF
from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.labs import phase_delta_binding as binding
from symq.labs.dyadic_phase import DyadicGate, DyadicPhaseProgram
from symq.labs.phase_delta_binding import (
    PhaseDifference,
    ProgramPhaseResult,
    check_program_phase_difference,
    extract_phase_difference,
    replay_program_phase_difference,
)
from symq.labs.phase_quotient import PhaseQuotientCertificate, check_prefix_phase
from symq.resources import Budget
from tests.testkit import phase_delta_oracle as oracle

AND = ANF(frozenset({3, 4}))  # z XOR ab on wires a=0, b=1, z=2


def P(width, k=3):
    return DyadicPhaseProgram(width, k=k)


def _prefix():
    return Circuit(3).ccx(0, 1, 2)


def _global(program, wire, angle=Fraction(1, 8)):
    # (1 - w) + w = 1: a global phase on every input, written with a data wire.
    return program.x(wire).phase(wire, angle).x(wire).phase(wire, angle)


def _pair():
    # On the image z = ab, so Z(z) equals CZ(a, b); the right side adds a global -1/8 turn.
    return P(3).z(2), _global(P(3).cz(0, 1), 0)


def _certificate(left, right, k=None, constant=None, invariants=(AND,), multipliers=None):
    found = extract_phase_difference(left, right)
    k = found.k if k is None else k
    if multipliers is None:
        multipliers = (((0, 1 << (k - 1)),),)
    if constant is None:
        constant = dict(found.delta).get(0, 0)
    return PhaseQuotientCertificate(found.width, k, found.delta, invariants, multipliers,
                                    constant)


def _universal(prefix, left, right, constants, constant=None):
    k = max(left.k, right.k)
    table = oracle.phase_table(left, right, k)
    reached = sorted(oracle.image(prefix, constants))
    constant = table[reached[0]] if constant is None else constant
    delta, invariant, multiplier = oracle.universal_certificate(prefix, left, right, constants,
                                                                k, constant)
    return PhaseQuotientCertificate(prefix.width, k, delta, (ANF(invariant),), (multiplier,),
                                    constant)


def _check(prefix, left, right, certificate, constants=((2, 0),), **kwargs):
    return check_program_phase_difference(prefix, left, right, certificate,
                                          initial_constants=constants, **kwargs)


def test_global_phase_on_prefix_image_is_proved_and_replayed():
    left, right = _pair()
    certificate = _certificate(left, right)
    assert certificate.constant == 7 and certificate.delta == ((0, 7), (3, 4), (4, 4))
    result = _check(_prefix(), left, right, certificate)
    assert result.outcome == "proved" and result.obligation is None
    assert result.constant == 7 and result.k == 3 and result.width == 3
    assert result.output_scope == "all_cut_inputs"
    receipt = result.to_dict()
    assert receipt["theorem"] == "dyadic_programs_global_phase_on_prefix_image"
    assert receipt["candidate_authorized"] is False
    assert receipt["controlled_use_authorized"] is False
    assert replay_program_phase_difference(_prefix(), left, right, certificate, receipt,
                                           initial_constants=((2, 0),)) == result
    truth = oracle.compare(_prefix(), left, right, ((2, 0),))
    assert truth["output_mismatches"] == 0 and truth["global_turn"] == Fraction(7, 8)
    # Without the clean ancilla the inherited invariant fails on a replayed legal input.
    dirty = check_program_phase_difference(_prefix(), left, right, certificate)
    assert dirty.outcome == "not_proved" and dirty.obligation == "prefix_phase"
    assert dirty.violating_invariant == 0 and dirty.constant is None
    assert len(oracle.compare(_prefix(), left, right, ())["phase_turns"]) > 1


def test_expected_constant_is_pinned_by_check_and_by_replay():
    left, right = _pair()
    certificate = _certificate(left, right)
    pinned = _check(_prefix(), left, right, certificate, expected_constant=7)
    assert pinned.outcome == "proved" and pinned.expected_constant == 7
    wrong = _check(_prefix(), left, right, certificate, expected_constant=1)
    assert wrong.outcome == "not_proved" and wrong.obligation == "expected_constant"
    assert wrong.constant is None
    receipt = _check(_prefix(), left, right, certificate).to_dict()
    for pin in (7, 1):
        with pytest.raises(ValueError, match="receipt mismatch"):
            replay_program_phase_difference(_prefix(), left, right, certificate, receipt,
                                            initial_constants=((2, 0),), expected_constant=pin)
    assert replay_program_phase_difference(
        _prefix(), left, right, certificate, pinned.to_dict(), initial_constants=((2, 0),),
        expected_constant=7) == pinned
    for value in (True, -1, 8, 1.0):
        with pytest.raises(ValueError, match="expected_constant"):
            _check(_prefix(), left, right, certificate, expected_constant=value)


def test_stale_delta_for_another_right_program_is_refused():
    left, right = _pair()
    stale_right = P(3).cz(0, 1)  # A valid neighbour: its delta differs by the global turn.
    stale = _certificate(left, stale_right)
    assert check_prefix_phase(_prefix(), stale, initial_constants=((2, 0),)).outcome == "proved"
    result = _check(_prefix(), left, right, stale)
    assert result.outcome == "not_proved" and result.obligation == "phase_difference"
    assert "delta differs" in result.reason and result.constant is None
    # A stale constant certificate cannot vouch for an input-dependent actual phase.
    moving = P(3).cz(0, 1).t(0)
    assert len(oracle.compare(_prefix(), left, moving, ((2, 0),))["phase_turns"]) == 2
    refused = _check(_prefix(), left, moving, stale)
    assert refused.outcome == "not_proved" and refused.obligation == "phase_difference"
    # Even with the right constant, the delta must be the programs' own, not a relabelled one.
    swapped = _check(_prefix(), right, left, _certificate(left, right))
    assert swapped.outcome == "not_proved" and swapped.obligation == "phase_difference"


def test_equal_phases_with_different_outputs_are_refused_with_a_replayed_witness():
    left = P(3).z(2)
    right = P(3).z(2).cx(2, 0)
    certificate = _certificate(left, right, constant=0, invariants=(), multipliers=())
    assert certificate.delta == ()
    result = _check(_prefix(), left, right, certificate)
    assert result.outcome == "not_proved" and result.obligation == "outputs"
    assert result.output_index == 0 and result.delta_sha256 is None
    x = result.witness
    assert x is not None and x >> 2 & 1 == 0
    cut = oracle.run_prefix(_prefix(), x)
    assert oracle.run_program(left, cut)[0] != oracle.run_program(right, cut)[0]


def test_outputs_need_only_agree_on_the_prefix_image():
    prefix = Circuit(4).ccx(0, 1, 2)
    left = P(4).z(2)
    # Toggles wire 3 iff a*b*(not z), which never happens after the prefix with z = 0.
    right = P(4).cz(0, 1).x(2).mcx(0, 1, 2, 3).x(2)
    certificate = _certificate(left, right)
    proved = _check(prefix, left, right, certificate)
    assert proved.outcome == "proved" and proved.output_scope == "prefix_image"
    dirty = check_program_phase_difference(prefix, left, right, certificate)
    assert dirty.outcome == "not_proved" and dirty.obligation == "outputs"
    assert dirty.output_index == 3
    cut = oracle.run_prefix(prefix, dirty.witness)
    assert oracle.run_program(left, cut)[0] != oracle.run_program(right, cut)[0]
    assert oracle.compare(prefix, left, right, ())["output_mismatches"] > 0


def test_negative_full_turn_and_mixed_k_angles_are_canonicalized():
    left = P(2, k=3).phase(0, Fraction(-1, 8)).phase(1, 1).phase(1, -3)
    right = P(2, k=4).phase(0, Fraction(7, 8)).phase(1, Fraction(17, 16)).phase(1, Fraction(-1, 16))
    found = extract_phase_difference(left, right)
    assert found == PhaseDifference(2, 4, ())
    assert extract_phase_difference(P(2, k=3).t(0), P(2, k=4)) == PhaseDifference(2, 4, ((1, 2),))
    assert extract_phase_difference(P(2, k=4), P(2, k=3).t(0)) == PhaseDifference(2, 4, ((1, 14),))
    empty = PhaseQuotientCertificate(2, 4, (), (), (), 0)
    assert check_program_phase_difference(Circuit(2), left, right, empty).outcome == "proved"
    # The same delta written for min(k) is a different statement and is refused.
    coarse = PhaseQuotientCertificate(2, 3, (), (), (), 0)
    refused = check_program_phase_difference(Circuit(2), left, right, coarse)
    assert refused.outcome == "not_proved" and "modulus" in refused.reason
    # A fine phase visible only at k = 4 must survive scaling.
    fine = P(2, k=4).phase(0, Fraction(1, 16))
    assert extract_phase_difference(fine, P(2, k=3)) == PhaseDifference(2, 4, ((1, 1),))
    assert check_program_phase_difference(Circuit(2), fine, P(2, k=3),
                                          empty).outcome == "not_proved"


def test_mutating_the_prefix_or_programs_after_the_proof_breaks_replay():
    left, right = _pair()
    certificate = _certificate(left, right)
    prefix = _prefix()
    receipt = _check(prefix, left, right, certificate).to_dict()
    for changed in (_prefix().x(0).x(0), Circuit(3).ccx(1, 0, 2)):
        with pytest.raises(ValueError, match="receipt mismatch"):
            replay_program_phase_difference(changed, left, right, certificate, receipt,
                                            initial_constants=((2, 0),))
    prefix.gates.append(Gate("x", (0,)))
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_program_phase_difference(prefix, left, right, certificate, receipt,
                                        initial_constants=((2, 0),))
    # Programs are bound by their own gate streams, even when semantically unchanged.
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_program_phase_difference(_prefix(), left, _global(P(3).cz(0, 1), 1),
                                        certificate, receipt, initial_constants=((2, 0),))
    right.gates.append(DyadicGate("z", (2,)))
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_program_phase_difference(_prefix(), left, right, certificate, receipt,
                                        initial_constants=((2, 0),))


def test_inputs_are_detached_before_any_obligation(monkeypatch):
    left, right = _pair()
    certificate = _certificate(left, right)
    prefix = _prefix()
    expected = _check(_prefix(), *_pair(), certificate)
    actual = binding.check_prefix_phase

    def tamper(*args, **kwargs):
        prefix.gates.clear()
        right.gates.append(DyadicGate("t", (0,)))
        left.gates.clear()
        return actual(*args, **kwargs)

    monkeypatch.setattr(binding, "check_prefix_phase", tamper)
    assert _check(prefix, left, right, certificate) == expected


def test_relabelled_wires_and_reordered_ancillas_are_refused():
    left, right = _pair()
    certificate = _certificate(left, right)
    relabelled = P(3).z(2).cx(0, 1).cx(1, 0).cx(0, 1)  # z(2) followed by SWAP(a, b)
    result = _check(_prefix(), left, relabelled, _certificate(left, relabelled, constant=0,
                                                              invariants=(), multipliers=()))
    assert result.outcome == "not_proved" and result.obligation == "outputs"
    # The ancilla constant on another wire is a different domain and a different receipt.
    receipt = _check(_prefix(), left, right, certificate).to_dict()
    moved = _check(_prefix(), left, right, certificate, constants=((0, 0),))
    assert moved.outcome == "not_proved"
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_program_phase_difference(_prefix(), left, right, certificate, receipt,
                                        initial_constants=((0, 0),))
    # Two ancillas; the right program reads them in the other order.
    prefix = Circuit(4).ccx(0, 1, 2).cx(0, 3)
    left4 = P(4).z(2).t(3)  # ancilla 2 holds ab, ancilla 3 holds a
    right4 = P(4).cz(0, 1).t(0)
    swapped = P(4).z(3).t(2)
    constants = ((2, 0), (3, 0))
    multipliers = (((0, 4),), ((0, 1), (1, 6)))  # 4*lift(z^ab) + (1-2a)*lift(w3^a)
    explicit = _certificate(left4, right4, invariants=(AND, ANF(frozenset({1, 8}))),
                            multipliers=multipliers)
    good = _check(prefix, left4, right4, explicit, constants)
    assert good.outcome == "proved" and good.constant == 0
    bad = _check(prefix, left4, swapped, _universal(prefix, left4, swapped, constants), constants)
    assert bad.outcome == "not_proved" and oracle.compare(prefix, left4, swapped,
                                                          constants)["global_turn"] is None
    with pytest.raises(ValueError, match="width"):
        _check(prefix, P(3).z(2), P(3), certificate)


def test_false_invariant_with_zero_multiplier_is_still_refused():
    left, right = _pair()
    base = _certificate(left, right)
    false_on_image = ANF(frozenset({1}))  # a = 0 is not true on the prefix image
    certificate = replace(base, invariants=base.invariants + (false_on_image,),
                          multipliers=base.multipliers + ((),))
    result = _check(_prefix(), left, right, certificate)
    assert result.outcome == "not_proved" and result.obligation == "prefix_phase"
    assert result.violating_invariant == 1
    assert false_on_image.evaluate(oracle.run_prefix(_prefix(), result.witness)) == 1


def test_forged_results_and_receipt_mutations_are_refused():
    left, right = _pair()
    certificate = _certificate(left, right)
    result = _check(_prefix(), left, right, certificate)
    receipt = result.to_dict()

    def replay(value, **kwargs):
        return replay_program_phase_difference(_prefix(), left, right, certificate, value,
                                               initial_constants=((2, 0),), **kwargs)

    with pytest.raises(ValueError, match="exact fields"):
        replay(result)
    with pytest.raises(ValueError, match="exact fields"):
        replay(type("Receipt", (dict,), {})(receipt))
    forged = replace(result, constant=3).to_dict()
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay(forged)
    refusal = _check(_prefix(), left, P(3).cz(0, 1).t(0), certificate)
    forged_proof = replace(refusal, outcome="proved", constant=7, obligation=None)
    with pytest.raises(ValueError, match="receipt mismatch"):
        replay_program_phase_difference(_prefix(), left, P(3).cz(0, 1).t(0), certificate,
                                        forged_proof.to_dict(), initial_constants=((2, 0),))
    mutations = [
        ("schema_version", True), ("schema_version", 2), ("kind", "other"),
        ("theorem", "full_channel"), ("candidate_authorized", True),
        ("controlled_use_authorized", True), ("outcome", "not_proved"), ("constant", 1),
        ("constant", 7.0), ("constant", True), ("k", 4), ("width", 4), ("witness", 0),
        ("obligation", "outputs"), ("output_scope", "prefix_image"), ("reason", "ok"),
        ("expected_constant", 7), ("initial_constants", []), ("initial_constants", [[2, 1]]),
        ("initial_constants", [(2, 0)]), ("prefix_sha256", "0" * 64),
        ("left_sha256", receipt["right_sha256"]), ("delta_sha256", None),
        ("certificate_sha256", "A" * 64), ("outcome", "inconclusive"), ("outcome", "maybe"),
    ]
    for field, value in mutations:
        with pytest.raises(ValueError):
            replay({**receipt, field: value})
    with pytest.raises(ValueError, match="exact fields"):
        replay({**receipt, "extra": 1})
    with pytest.raises(ValueError, match="exact fields"):
        replay({key: value for key, value in receipt.items() if key != "witness"})
    assert replay(dict(receipt)) == result


def _program_with_forged_gate(field, value):
    program = P(3).z(2)
    object.__setattr__(program.gates[0], field, value)
    return program


class _Name(str):
    def __eq__(self, other):
        return other == "z"

    def __hash__(self):
        return hash("z")


class _Turn(Fraction):
    pass


@pytest.mark.parametrize("make", [
    lambda: type("Sub", (DyadicPhaseProgram,), {})(3),
    lambda: _program_with_forged_gate("name", _Name("h")),
    lambda: _program_with_forged_gate("wires", [2]),
    lambda: _program_with_forged_gate("wires", (True,)),
    lambda: _program_with_forged_gate("name", "h"),
    lambda: _program_with_forged_gate("angle", Fraction(1, 2)),
    lambda: _forged_angle(True),
    lambda: _forged_angle(_Turn(1, 8)),
    lambda: _forged_angle(1.0),
    lambda: _forged_angle(Fraction(1, 16)),
])
def test_forged_or_unsupported_programs_never_yield_a_verdict(make):
    program = make()
    left, right = _pair()
    with pytest.raises((TypeError, ValueError, UnsupportedOperation)):
        _check(_prefix(), left, program, _certificate(left, right))


def _forged_angle(value):
    program = P(3).phase(2, Fraction(1, 8))
    object.__setattr__(program.gates[0], "angle", value)
    return program


def test_strict_program_containers_and_widths():
    left, right = _pair()
    certificate = _certificate(left, right)
    for field, value in [("width", True), ("k", True), ("k", 65), ("gates", tuple(right.gates))]:
        forged = _pair()[1]
        object.__setattr__(forged, field, value)
        with pytest.raises((TypeError, ValueError)):
            _check(_prefix(), left, forged, certificate)
    with pytest.raises(TypeError):
        _check(_prefix(), left, "program", certificate)
    with pytest.raises(TypeError):
        _check(_prefix(), left, right, certificate.__dict__)
    with pytest.raises(ValueError):
        _check(_prefix(), left, right, certificate, constants=[(2, 0)])
    with pytest.raises(ValueError):
        _check(Circuit(4).ccx(0, 1, 2), left, right, certificate)


def test_budget_exhaustion_is_inconclusive_and_never_replayable():
    left, right = _pair()
    certificate = _certificate(left, right)
    small = _check(_prefix(), left, right, certificate, budget=Budget(max_terms=2))
    assert small.outcome == "inconclusive" and small.obligation == "resources"
    assert small.constant is None and "terms limit" in small.reason
    expired = _check(_prefix(), left, right, certificate,
                     budget=Budget(absolute_deadline=time.perf_counter() - 1))
    assert expired.outcome == "inconclusive" and expired.prefix_sha256 is None
    with pytest.raises(ValueError, match="no replayable claim"):
        replay_program_phase_difference(_prefix(), left, right, certificate, small.to_dict(),
                                        initial_constants=((2, 0),))
    receipt = _check(_prefix(), left, right, certificate).to_dict()
    with pytest.raises(ResourceLimitExceeded):
        replay_program_phase_difference(_prefix(), left, right, certificate, receipt,
                                        initial_constants=((2, 0),), budget=Budget(max_terms=2))
    for budget in (Budget(max_nodes=10), Budget(max_bytes=10)):
        with pytest.raises(ValueError, match="max_nodes/max_bytes"):
            _check(_prefix(), left, right, certificate, budget=budget)


def test_every_interrupted_computation_is_inconclusive(monkeypatch):
    from symq.resources import Guard

    left, right = _pair()
    certificate = _certificate(left, right)
    original = Guard.check_time
    calls = 0

    def counting(self):
        nonlocal calls
        calls += 1
        original(self)

    monkeypatch.setattr(Guard, "check_time", counting)
    assert _check(_prefix(), left, right, certificate).outcome == "proved"
    total = calls
    stages = set()
    for stop in range(1, total + 1):
        count = 0

        def interrupt(self, stop=stop):
            nonlocal count
            count += 1
            if count == stop:
                raise ResourceLimitExceeded("seconds", 1, 2)
            original(self)

        monkeypatch.setattr(Guard, "check_time", interrupt)
        result = _check(_prefix(), left, right, certificate)
        assert result.outcome == "inconclusive" and result.constant is None, stop
        stages.add(result.reason.split(":")[0])
    assert stages >= {f"resource limit exceeded during {stage}"
                      for stage in ("inputs", "outputs", "phase_difference", "prefix_phase")}


_GATES = ("x", "cx", "ccx", "mcx", "t", "tdg", "s", "sdg", "z", "cz", "ccz", "phase")
_NEEDS = {"t": 3, "tdg": 3, "s": 2, "sdg": 2}  # least k representing the named angle


def _random_program(rng, width, k, length):
    program = P(width, k=k)
    for _ in range(length):
        name = rng.choice(_GATES)
        if _NEEDS.get(name, 1) > k or (name == "mcx" and width < 2):
            continue
        arity = (rng.randrange(2, width + 1) if name == "mcx"
                 else {"x": 1, "cx": 2, "ccx": 3, "cz": 2, "ccz": 3}.get(name, 1))
        if arity > width:
            continue
        wires = rng.sample(range(width), arity)
        if name == "phase":
            program.phase(wires[0], Fraction(rng.randrange(-20, 20), 1 << rng.randrange(k + 1)))
        else:
            program.append(name, *wires)
    return program


def _random_prefix(rng, width):
    prefix = Circuit(width)
    for _ in range(rng.randrange(1, 7)):
        arity = rng.randrange(1, min(3, width) + 1)
        prefix.append({1: "x", 2: "cx", 3: "ccx"}[arity], *rng.sample(range(width), arity))
    constants = tuple(sorted((q, rng.randrange(2))
                             for q in rng.sample(range(width), rng.randrange(width))))
    return prefix, constants


def _image_trivial(rng, prefix, constants, program):
    """Prepend gates acting as identity, or as a global phase, on the prefix image."""
    reached = oracle.image(prefix, constants)
    width = prefix.width
    vanishing = [m for m in range(1, 1 << width)
                 if m.bit_count() <= 3 and all(w & m != m for w in reached)]
    out = P(width, k=program.k)
    for _ in range(rng.randrange(1, 4)):
        choice = rng.randrange(3)
        if choice == 0 and vanishing:
            monomial = rng.choice(vanishing)
            wires = [q for q in range(width) if monomial >> q & 1]
            if len(wires) == 1:
                out.append(rng.choice([g for g in ("t", "s", "z", "tdg")
                                       if _NEEDS.get(g, 1) <= program.k]), *wires)
            elif len(wires) == 2:
                out.cz(*wires)
            else:
                out.ccz(*wires)
        elif choice == 1 and vanishing:
            monomial = rng.choice(vanishing)
            controls = [q for q in range(width) if monomial >> q & 1]
            targets = [q for q in range(width) if q not in controls]
            if targets:
                out.mcx(*controls, rng.choice(targets))
        else:
            _global(out, rng.randrange(width),
                    Fraction(rng.randrange(-8, 9), 1 << rng.randrange(program.k + 1)))
    out.gates.extend(program.gates)
    q = rng.randrange(width)
    # Global or cancelling tail: (1-q)/2 + q/2, then -3/2 + 3/2 and CZ twice.
    out.x(q).z(q).x(q).z(q).phase(q, Fraction(-3, 2)).phase(q, Fraction(3, 2))
    if width > 1:
        out.cz(q, (q + 1) % width).cz(q, (q + 1) % width)
    if rng.randrange(2):
        out = DyadicPhaseProgram(width, out.gates, program.k + 1)
    return out


def test_differential_against_exhaustive_oracle_with_complete_certificates():
    rng = random.Random(20261102)
    proved = refused = refused_outputs = nonzero = image_only = 0
    for width in range(2, 6):
        for trial in range(36):
            prefix, constants = _random_prefix(rng, width)
            k = rng.randrange(1, 5)
            left = _random_program(rng, width, k, rng.randrange(0, 8))
            if trial % 3 == 0:
                right = _random_program(rng, width, rng.randrange(1, 5), rng.randrange(0, 8))
            else:
                right = _image_trivial(rng, prefix, constants, left)
                if trial % 3 == 2:
                    right.gates.append(rng.choice([
                        DyadicGate("t" if right.k >= 3 else "z", (rng.randrange(width),)),
                        DyadicGate("cx", tuple(rng.sample(range(width), 2))),
                        DyadicGate("x", (rng.randrange(width),)),
                    ]))
            if trial % 2:
                left, right = right, left
            truth = oracle.compare(prefix, left, right, constants)
            certificate = _universal(prefix, left, right, constants)
            result = check_program_phase_difference(prefix, left, right, certificate,
                                                    initial_constants=constants)
            k = max(left.k, right.k)
            if truth["global_turn"] is not None:
                proved += 1
                assert result.outcome == "proved", (width, trial, result)
                assert Fraction(result.constant, 1 << k) == truth["global_turn"]
                nonzero += result.constant != 0
                image_only += result.output_scope == "prefix_image"
            else:
                refused += 1
                assert result.outcome == "not_proved", (width, trial, result)
                if truth["output_mismatches"]:
                    refused_outputs += 1
                    assert result.obligation == "outputs"
                    cut = oracle.run_prefix(prefix, result.witness)
                    assert oracle.run_program(left, cut)[0] != oracle.run_program(right, cut)[0]
                else:
                    assert result.obligation == "prefix_phase"
                    assert result.reason == "polynomial identity mismatch"
            assert replay_program_phase_difference(prefix, left, right, certificate,
                                                   result.to_dict(),
                                                   initial_constants=constants) == result
    # Seeded counts: 54 proved (44 nonzero c, 12 image-only outputs), 90 refused (73 on
    # outputs). The floors keep every side of the differential exercised.
    assert proved >= 50 and refused >= 60 and refused_outputs >= 30
    assert refused - refused_outputs >= 15 and nonzero >= 20 and image_only >= 5


def test_extracted_delta_matches_oracle_interpolation():
    rng = random.Random(152)
    for width in range(1, 6):
        for _ in range(30):
            left = _random_program(rng, width, rng.randrange(1, 6), rng.randrange(0, 10))
            right = _random_program(rng, width, rng.randrange(1, 6), rng.randrange(0, 10))
            k = max(left.k, right.k)
            expected = oracle.interpolate(oracle.phase_table(left, right, k), width, 1 << k)
            assert extract_phase_difference(left, right) == PhaseDifference(width, k, expected)


def test_result_dataclass_is_not_trusted_and_reports_inequivalence_honestly():
    # not_proved never carries a constant or claims inequivalence.
    left, right = _pair()
    certificate = replace(_certificate(left, right), multipliers=((),))
    result = _check(_prefix(), left, right, certificate)
    assert result.outcome == "not_proved" and result.reason == "polynomial identity mismatch"
    assert oracle.compare(_prefix(), left, right, ((2, 0),))["global_turn"] == Fraction(7, 8)
    assert isinstance(result, ProgramPhaseResult) and result.witness is None
