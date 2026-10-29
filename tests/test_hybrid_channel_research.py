"""Independent exact Kraus tests for the tiny hybrid CPTP-channel oracle."""

import random
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "hybrid_channel"))

from oracle import (HOp, HybridProgram, coherence_image, coherence_instrument,
                    same_channel, same_instrument)

from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded


def _reference(program: HybridProgram, x: int, y: int, observed_slots=None):
    """Independent *ket-vector* Kraus expansion, not density-entry updates.

    A branch owns ket and bra vectors (in this tiny pilot they start as unit
    vectors). A projective measurement or reset is implemented via a separate
    Kraus vector map on each side; the channel sums all outer products at end.
    """
    program.validate()
    branches = [({x: 1}, {y: 1}, {}, Fraction(1))]

    def transformed(vector, fn):
        out = {}
        for k, amplitude in vector.items():
            target, sign = fn(k)
            out[target] = out.get(target, 0) + amplitude * sign
        return {k: v for k, v in out.items() if v}

    for op in program.ops:
        following = []
        for ket, bra, classical, weight in branches:
            if op.kind == "store":
                saved = dict(classical)
                saved[op.slot] = op.value
                following.append((ket, bra, saved, weight))
                continue
            if op.kind == "invert":
                saved = dict(classical)
                cond = op.condition
                active = not cond or bool(saved[cond.removeprefix("!")]
                                           ^ int(cond.startswith("!")))
                saved[op.slot] ^= int(active)
                following.append((ket, bra, saved, weight))
                continue
            if op.kind == "oxor":
                saved = dict(classical)
                saved[op.slot] ^= saved[op.source]
                following.append((ket, bra, saved, weight))
                continue
            if op.kind == "hmr":
                bit = 1 << op.wires[0]
                for outcome in (0, 1):
                    def km(s, outcome=outcome, bit=bit):
                        return s & ~bit, (-1 if outcome and s & bit else 1)

                    kv = transformed(ket, km)
                    bv = transformed(bra, km)
                    if kv and bv:
                        saved = dict(classical)
                        saved[op.slot] = outcome
                        following.append((kv, bv, saved, weight / 2))
                continue
            if op.kind in {"measure_z", "reset"}:
                bit = 1 << op.wires[0]
                for result in (0, 1):
                    def project(s, result=result, bit=bit, kind=op.kind):
                        if int(bool(s & bit)) != result:
                            return s, 0
                        if kind == "reset":
                            return s & ~bit, 1
                        return s, 1

                    kv = transformed(ket, project)
                    bv = transformed(bra, project)
                    if kv and bv:
                        saved = dict(classical)
                        if op.kind == "measure_z":
                            saved[op.slot] = result
                        following.append((kv, bv, saved, weight))
                continue
            active = True
            if op.condition is not None:
                token = op.condition
                invert = token.startswith("!")
                active = bool(classical[token.removeprefix("!")] ^ int(invert))
            if not active:
                following.append((ket, bra, classical, weight))
                continue

            def gate(s, operation=op):
                qs = operation.wires
                if operation.kind in {"x", "cx", "ccx", "mcx"}:
                    *controls, target = qs
                    if all((s >> q) & 1 for q in controls):
                        return s ^ (1 << target), 1
                    return s, 1
                if operation.kind == "swap":
                    a, b = qs
                    return (s ^ ((1 << a) | (1 << b)), 1) if (
                        ((s >> a) ^ (s >> b)) & 1) else (s, 1)
                if operation.kind == "cswap":
                    c, a, b = qs
                    return (s ^ ((1 << a) | (1 << b)), 1) if (
                        (s >> c & 1) and (((s >> a) ^ (s >> b)) & 1)) else (s, 1)
                if operation.kind in {"z", "cz", "ccz"}:
                    return s, (-1 if all(s >> q & 1 for q in qs) else 1)
                if operation.kind == "neg":
                    return s, -1
                raise AssertionError(operation.kind)

            following.append((transformed(ket, gate), transformed(bra, gate),
                              classical, weight))
        branches = following

    if observed_slots is not None:
        # Independent ket-vector Kraus reference, grouped by observed classical record.
        grouped = {}
        for ket, bra, classical, weight in branches:
            record = tuple(classical[s] for s in observed_slots)
            out = grouped.setdefault(record, {})
            for s, ca in ket.items():
                for u, cb in bra.items():
                    key = s, u
                    out[key] = out.get(key, Fraction(0)) + weight * ca * cb
        return {record: {pair: value for pair, value in out.items() if value}
                for record, out in grouped.items()
                if any(out.values())}
    result = {}
    for ket, bra, _, weight in branches:
        for s, ca in ket.items():
            for u, cb in bra.items():
                key = s, u
                result[key] = result.get(key, Fraction(0)) + weight * ca * cb
    return {key: value for key, value in result.items() if value}


def test_reset_of_entangled_ancilla_loses_coherence_not_data_basis_values():
    changed = HybridProgram(1, 1).cx(0, 1).reset(1)
    identity = HybridProgram(1, 1)
    assert coherence_image(changed, 0, 0) == {(0, 0): Fraction(1)}
    assert coherence_image(changed, 1, 1) == {(1, 1): Fraction(1)}
    assert coherence_image(changed, 0, 1) == {}
    assert coherence_image(identity, 0, 1) == {(0, 1): Fraction(1)}
    verdict = same_channel(changed, identity, budget=Budget(max_seconds=5))
    assert not verdict.equivalent and verdict.witness == (0, 1)
    assert not same_channel(changed, identity, trace_ancillas=True).equivalent
    assert _reference(changed, 0, 1) == {}


def test_true_reset_equals_z_measurement_then_classical_conditional_x():
    direct = HybridProgram(1, 1).cx(0, 1).reset(1)
    explicit = HybridProgram(1, 1).cx(0, 1).measure_z(1, "b0").x(1, condition="b0")
    verdict = same_channel(direct, explicit)
    assert verdict.equivalent and verdict.checked_pairs == 4
    for x in range(2):
        for y in range(2):
            assert coherence_image(direct, x, y) == _reference(explicit, x, y)


def test_hmr_outcome_controlled_value_gate_changes_mixture():
    noisy = HybridProgram(1, 1).hmr(1, "b0").x(0, condition="b0")
    identity = HybridProgram(1, 1)
    assert coherence_image(noisy, 0, 0) == {
        (0, 0): Fraction(1, 2), (1, 1): Fraction(1, 2),
    }
    assert _reference(noisy, 0, 0) == coherence_image(noisy, 0, 0)
    assert not same_channel(noisy, identity).equivalent


def test_temporary_and_release_full_quantum_channel_and_bad_phase():
    source = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0").cz(
        0, 1, condition="b0")
    reference = HybridProgram(3, 1).ccx(0, 1, 2)
    incorrect = HybridProgram(3, 1).ccx(0, 1, 3).cx(3, 2).hmr(3, "b0")
    assert same_channel(source, reference).equivalent
    verdict = same_channel(incorrect, reference)
    assert not verdict.equivalent and verdict.witness is not None
    assert _reference(incorrect, *verdict.witness) != _reference(
        reference, *verdict.witness)


def test_common_hmr_fragment_matches_independent_existing_kraus_oracle():
    """A distinct exact implementation is already shipped in SymQ research."""
    sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))
    import channel

    ours = HybridProgram(2, 1).ccx(0, 1, 2).hmr(2, "b0").cz(0, 1, condition="b0")
    old = PhaseProgram(2, 1).ccx(0, 1, 2)
    m = old.hmr(2)
    old.cz_if(m, 0, 1)
    for x in range(4):
        for y in range(4):
            assert coherence_image(ours, x, y) == channel.coherence_image(
                old, x, y, trace_ancillas=False)


def test_classical_slot_reuse_distinguishes_fresh_events_and_xor():
    # The second measurement overrides b0; the first remains an independent event.
    reused = HybridProgram(1, 1).hmr(1, "b0").x(1).hmr(1, "b0")
    reused.x(0, condition="b0")
    xor = HybridProgram(1, 1).hmr(1, "b0").x(1).hmr(1, "b1")
    xor.oxor("b0", "b1").x(0, condition="b0")
    for p in (reused, xor):
        for x in (0, 1):
            for y in (0, 1):
                assert coherence_image(p, x, y) == _reference(p, x, y)


def test_classical_xor_wrong_parity_is_observably_different():
    correct = HybridProgram(1).measure_z(0, "b0").store("b1", 1)
    correct.oxor("b1", "b0").x(0, condition="b1")  # output is one
    wrong = HybridProgram(1).measure_z(0, "b0").x(0, condition="b0")
    assert not same_channel(correct, wrong).equivalent
    assert coherence_image(correct, 0, 0) == {(1, 1): Fraction(1)}
    assert coherence_image(correct, 1, 1) == {(1, 1): Fraction(1)}
    assert coherence_image(wrong, 0, 0) == {(0, 0): Fraction(1)}


def test_full_and_reduced_output_channels_are_different_theorems():
    a = HybridProgram(1, 1).cx(0, 1)
    b = HybridProgram(1, 1).cx(0, 1).x(1)
    assert not same_channel(a, b).equivalent
    assert same_channel(a, b, trace_ancillas=True).equivalent


@pytest.mark.parametrize("seed", range(40))
def test_small_random_programs_against_independent_vector_kraus(seed):
    rng = random.Random(202610290000 + seed)
    data = rng.randint(1, 2)
    anc = rng.randint(0, 1)
    width = data + anc
    p = HybridProgram(data, anc)
    slots = []
    for _ in range(6):
        kinds = ["x", "z", "hmr", "measure_z", "reset", "store"]
        if width >= 2:
            kinds += ["cx", "cz", "swap"]
        op = rng.choice(kinds)
        if op == "store":
            slot = f"b{rng.randrange(2)}"
            p.store(slot, rng.randrange(2))
            if slot not in slots:
                slots.append(slot)
        elif op in ("hmr", "measure_z"):
            slot = f"b{rng.randrange(2)}"
            getattr(p, op)(rng.randrange(width), slot)
            if slot not in slots:
                slots.append(slot)
        elif op == "reset":
            p.reset(rng.randrange(width))
        else:
            arity = 2 if op in {"cx", "cz", "swap"} else 1
            wires = rng.sample(range(width), arity)
            condition = rng.choice(slots) if slots and rng.randrange(2) else None
            getattr(p, op)(*wires, condition=condition)
        if slots and rng.randrange(5) == 0:
            p.invert(rng.choice(slots))
        if len(slots) > 1 and rng.randrange(5) == 0:
            a, b = rng.sample(slots, 2)
            p.oxor(a, b)
    for x in range(1 << data):
        for y in range(1 << data):
            assert coherence_image(p, x, y) == _reference(p, x, y), (
                seed, x, y, p.ops)


@pytest.mark.parametrize("mutant", [
    lambda p: p.x(0, condition="b0"),
    lambda p: p.hmr(0, "b0")._add("reset", (1,), condition="b0"),
    lambda p: p.hmr(0, "b0").measure_z(0, "b1").cx(1, 0, condition="b2"),
    lambda p: p.cx(0, 0),
    lambda p: p.mcx(0),
    lambda p: p.store("b0", 2),
    lambda p: p.oxor("b0", "b1"),
])
def test_invalid_operations_fail_closed(mutant):
    with pytest.raises((ValueError, UnsupportedOperation)):
        mutant(HybridProgram(1, 1))


def test_invalid_mutated_ir_and_width_or_event_resources():
    program = HybridProgram(1)
    program.ops.append(HOp("h", (0,)))
    with pytest.raises(UnsupportedOperation):
        coherence_image(program, 0, 0)
    too_wide = HybridProgram(1, 6)
    with pytest.raises(ResourceLimitExceeded, match="width"):
        coherence_image(too_wide, 0, 0)
    many = HybridProgram(1, 1)
    for _ in range(9):
        many.hmr(1, "b0")
    with pytest.raises(ResourceLimitExceeded, match="events"):
        coherence_image(many, 0, 0)
    with pytest.raises(ResourceLimitExceeded, match="terms"):
        coherence_image(HybridProgram(1, 1).hmr(1, "b0"), 0, 0,
                        budget=Budget(max_terms=1), max_branches=2, max_events=1)
    with pytest.raises(ValueError, match="max_nodes"):
        coherence_image(HybridProgram(1), 0, 0, budget=Budget(max_nodes=1))
    with pytest.raises(ValueError):
        coherence_image(HybridProgram(1), 0, 2)


def test_budget_inconclusive_never_becomes_channel_equality():
    with pytest.raises(ResourceLimitExceeded):
        same_channel(
            HybridProgram(1, 1).hmr(1, "b0"),
            HybridProgram(1, 1),
            max_branches=1,
        )
    with pytest.raises(ResourceLimitExceeded, match="seconds"):
        same_channel(HybridProgram(1, 1), HybridProgram(1, 1),
                     budget=Budget(max_seconds=1e-9))



def test_observed_classical_instrument_is_stronger_than_discarded_channel():
    observed = HybridProgram(1).measure_z(0, "b0")
    hidden = HybridProgram(1).measure_z(0, "b0").store("b0", 0)
    assert same_channel(observed, hidden).equivalent
    mismatch = same_instrument(observed, hidden, observed_slots=("b0",))
    assert not mismatch.equivalent and mismatch.witness is not None
    x, y = mismatch.witness
    assert coherence_instrument(observed, x, y, observed_slots=("b0",)) != (
        coherence_instrument(hidden, x, y, observed_slots=("b0",))
    )
    assert same_instrument(observed, observed, observed_slots=("b0",)).equivalent


def test_instrument_matches_independent_ket_kraus_for_reused_slots_and_value_feedback():
    p = HybridProgram(2, 1).cx(0, 2).hmr(2, "b0")
    p.x(1, condition="b0").measure_z(1, "b1").oxor("b0", "b1")
    for x in range(1 << p.data):
        for y in range(1 << p.data):
            result = coherence_instrument(p, x, y, observed_slots=("b0", "b1"))
            reference = _reference(p, x, y, observed_slots=("b0", "b1"))
            assert result == reference
    assert same_instrument(p, p, observed_slots=("b0", "b1")).equivalent


def test_instrument_fail_closed_on_hidden_slot_and_budget():
    p = HybridProgram(1).hmr(0, "b0")
    for slots in ((), ("b0", "b0"), ("b9",), ("invalid",)):
        with pytest.raises(UnsupportedOperation):
            coherence_instrument(p, 0, 1, observed_slots=slots)
    with pytest.raises(ResourceLimitExceeded):
        same_instrument(p, p, observed_slots=("b0",),
                        budget=Budget(max_seconds=1e-12))
    with pytest.raises(ValueError, match="max_nodes"):
        coherence_instrument(p, 0, 0, observed_slots=("b0",),
                             budget=Budget(max_nodes=1))
