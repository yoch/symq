"""Ancilla obligations with an arbitrary initial target and arbitrary classical inputs.

``with_inputs`` must build exactly the adapter a caller writes by hand (a hidden data wire
swapped into the target, hidden data wires measured into the input slots), and both
clean-ancilla engines must then agree with an independent interpreter that runs the
caller's own program from every initial target value and every input value.

The interpreter below shares no code with SymQ. On a computational-basis input every
operation of the grammar maps a basis state to a basis state, up to a phase, except HMR,
whose outcome is uniform and which leaves its wire at 0; so the error probability of a
basis input is an exact finite average. A clean-ancilla effect is a positive operator, so
it is zero exactly when every basis input has error probability zero.
"""
from __future__ import annotations

import random
from fractions import Fraction
from itertools import product

import pytest

from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.ancilla_inputs import with_inputs
from symq.labs.backward_ancilla import check_clean_ancilla, replay_clean_ancilla
from symq.labs.shift_diagonal_ancilla import check_shift_diagonal

ENGINES = {
    "pauli": lambda program, target: check_clean_ancilla(program, target),
    "shift_diagonal": lambda program, target: check_shift_diagonal(program, target),
}


# ---------------------------------------------------------------- independent interpreter

def _holds(condition, slots):
    if condition is None:
        return True
    name = condition.removeprefix("!")
    return bool(slots[name]) != condition.startswith("!")


def _error_probability(ops, width, target, bits, slots):
    """Probability that ``target`` ends at 1, from basis state ``bits`` and ``slots``."""
    states = [(bits, dict(slots), Fraction(1))]
    for op in ops:
        following = []
        for state, table, weight in states:
            kind, wires = op.kind, op.wires
            if kind == "store":
                table = {**table, op.slot: op.value}
            elif kind == "invert":
                table = {**table, op.slot: table[op.slot] ^ int(_holds(op.condition, table))}
            elif kind == "oxor":
                table = {**table, op.slot: table[op.slot] ^ table[op.source]}
            elif kind == "measure_z":
                table = {**table, op.slot: state >> wires[0] & 1}
            elif kind == "hmr":
                for outcome in (0, 1):
                    following.append((state & ~(1 << wires[0]), {**table, op.slot: outcome},
                                      weight / 2))
                continue
            elif kind == "reset":
                state &= ~(1 << wires[0])
            elif _holds(op.condition, table):
                if kind in {"x", "cx", "ccx", "mcx"}:
                    if all(state >> c & 1 for c in wires[:-1]):
                        state ^= 1 << wires[-1]
                elif kind in {"swap", "cswap"}:
                    *controls, a, b = wires
                    if all(state >> c & 1 for c in controls) and (state >> a & 1) != (state >> b & 1):
                        state ^= (1 << a) | (1 << b)
                # z, cz, ccz and neg only change a phase: no effect on a basis probability.
            following.append((state, table, weight))
        states = following
    assert all(s < 1 << width for s, _, _ in states)
    return sum((w for s, _, w in states if s >> target & 1), Fraction(0))


def _worst_case(data, ancillas, ops, target, inputs, arbitrary):
    """Every data basis input, initial target value and input value: errors found."""
    width = data + ancillas
    errors = {}
    for x, t0, values in product(range(1 << data), (0, 1) if arbitrary else (0,),
                                 product((0, 1), repeat=len(inputs))):
        bits = x | (t0 << target)
        p = _error_probability(ops, width, target, bits, dict(zip(inputs, values)))
        if p:
            errors[x, t0, values] = p
    return errors


# ---------------------------------------------------------------- the reduction itself

def test_the_reduction_is_the_adapter_written_by_hand():
    """The adapter a user wrote for a real program, rebuilt on a small one."""
    ops = [HOp("cx", (0, 2), condition="b3"), HOp("hmr", (2,), slot="b1"),
           HOp("cx", (1, 2), condition="b1"), HOp("cx", (1, 2), condition="b1")]
    program, layout = with_inputs(2, 1, ops, 2, initial_target="arbitrary",
                                  classical_inputs=("b3",))
    by_hand = HybridProgram(4, 1, [
        HOp("swap", (2, 4)), HOp("measure_z", (3,), slot="b3"),
        HOp("cx", (0, 4), condition="b3"), HOp("hmr", (4,), slot="b1"),
        HOp("cx", (1, 4), condition="b1"), HOp("cx", (1, 4), condition="b1")])
    assert program_to_dict(program) == program_to_dict(by_hand)
    assert layout.reduced_target == 4 and layout.hidden == 2
    assert layout.explain(0b1101) == {"data": 0b01, "initial_target": 1,
                                      "classical_inputs": {"b3": 1}}


def test_without_inputs_the_program_is_unchanged():
    ops = [HOp("cx", (0, 1)), HOp("cx", (0, 1))]
    program, layout = with_inputs(1, 1, ops, 1)
    assert program_to_dict(program) == program_to_dict(HybridProgram(1, 1, ops))
    assert layout.reduced_target == 1 and layout.explain(1)["initial_target"] is None


@pytest.mark.parametrize("call, error", [
    (lambda: with_inputs(2, 1, [], 1), "declared ancillas"),
    (lambda: with_inputs(2, 1, [], 2, initial_target="dirty"), "initial_target"),
    (lambda: with_inputs(2, 1, [HOp("cx", (0, 2))], 2, classical_inputs=("b1",)), "read before"),
    (lambda: with_inputs(2, 1, [HOp("store", slot="b1", value=1), HOp("x", (2,), condition="b1")],
                         2, classical_inputs=("b1",)), "read before"),
    (lambda: with_inputs(2, 1, [HOp("measure_z", (0,), slot="b1"), HOp("x", (2,), condition="b1")],
                         2, classical_inputs=("b1",)), "read before"),
    (lambda: with_inputs(2, 1, [HOp("x", (2,), condition="b1")], 2,
                         classical_inputs=("b1", "b1")), "twice"),
    (lambda: with_inputs(2, 1, [HOp("x", (2,), condition="b01")], 2,
                         classical_inputs=("b01",)), "canonical"),
])
def test_malformed_requests_are_refused(call, error):
    with pytest.raises(ValueError, match=error):
        call()


def test_a_read_modify_write_counts_as_a_read():
    _, layout = with_inputs(2, 1, [HOp("invert", slot="b1"), HOp("x", (2,), condition="b1")],
                                  2, classical_inputs=("b1",))
    assert dict(layout.classical_inputs) == {"b1": 2}


def test_a_wire_outside_the_width_is_an_unsupported_operation():
    from symq.circuit import UnsupportedOperation

    with pytest.raises(UnsupportedOperation, match="outside the declared width"):
        with_inputs(2, 1, [HOp("cx", (0, 3))], 2)


def test_an_inconsistent_layout_is_refused():
    from symq.labs.ancilla_inputs import InputLayout

    with pytest.raises(ValueError, match="arbitrary"):
        InputLayout(2, 1, 2, "clean", 2, ())
    with pytest.raises(ValueError, match="follow the data"):
        InputLayout(2, 1, 2, "arbitrary", 5, ())


def test_an_undeclared_input_is_still_refused_by_the_program_itself():
    from symq.circuit import UnsupportedOperation

    with pytest.raises(UnsupportedOperation):
        with_inputs(2, 1, [HOp("x", (2,), condition="b1")], 2)


# ---------------------------------------------------------------- verdicts

CASES = {
    # name: (data, ancillas, ops, target, inputs, arbitrary target, clean?)
    "reset_clears_any_initial_content": (
        1, 1, [HOp("cx", (0, 1)), HOp("reset", (1,))], 1, (), True, True),
    "nothing_clears_the_initial_content": (
        1, 1, [HOp("cx", (0, 1)), HOp("cx", (0, 1))], 1, (), True, False),
    "hmr_then_paired_corrections": (
        2, 1, [HOp("cx", (0, 2), condition="b3"), HOp("hmr", (2,), slot="b1"),
               HOp("cx", (1, 2), condition="b1"), HOp("cx", (1, 2), condition="b1")],
        2, ("b3",), True, True),
    "initial_hmr_omitted": (
        2, 1, [HOp("cx", (0, 2), condition="b3"),
               HOp("cx", (1, 2), condition="b3"), HOp("cx", (1, 2), condition="b3")],
        2, ("b3",), True, False),
    "last_conditional_cx_omitted": (
        2, 1, [HOp("cx", (0, 2), condition="b3"), HOp("hmr", (2,), slot="b1"),
               HOp("cx", (1, 2), condition="b1")],
        2, ("b3",), True, False),
    "input_toggles_twice": (
        2, 1, [HOp("cx", (0, 2), condition="b2"), HOp("x", (2,), condition="b5"),
               HOp("x", (2,), condition="b5"), HOp("cx", (0, 2), condition="b2")],
        2, ("b2", "b5"), False, True),
    "input_toggles_once": (
        2, 1, [HOp("cx", (0, 2), condition="!b2"), HOp("x", (2,), condition="b5")],
        2, ("b2", "b5"), False, False),
}


@pytest.mark.parametrize("engine", sorted(ENGINES))
@pytest.mark.parametrize("name", sorted(CASES))
def test_engines_agree_with_the_independent_interpreter(engine, name):
    data, ancillas, ops, target, inputs, arbitrary, clean = CASES[name]
    errors = _worst_case(data, ancillas, ops, target, inputs, arbitrary)
    assert (not errors) == clean, errors
    program, layout = with_inputs(data, ancillas, ops, target,
                                  initial_target="arbitrary" if arbitrary else "clean",
                                  classical_inputs=inputs)
    result = ENGINES[engine](program, layout.reduced_target)
    assert result.status == ("clean" if clean else "not_clean")
    if clean:
        return
    assignment = result.witness.assignment if engine == "pauli" else result.assignment
    probability = result.witness.probability if engine == "pauli" else result.probability
    seen = layout.explain(assignment)
    key = (seen["data"], seen["initial_target"] or 0,
           tuple(seen["classical_inputs"][slot] for slot in inputs))
    assert errors[key] == probability > 0


def test_the_report_probabilities_are_reproduced():
    """Omitting the initial HMR errs with probability 1; omitting the last correction, 1/2."""
    for name, expected in (("initial_hmr_omitted", 1), ("last_conditional_cx_omitted",
                                                         Fraction(1, 2))):
        data, ancillas, ops, target, inputs, arbitrary, _ = CASES[name]
        errors = _worst_case(data, ancillas, ops, target, inputs, arbitrary)
        assert max(errors.values()) == expected


def test_a_certificate_binds_the_reduced_program():
    data, ancillas, ops, target, inputs, _, _ = CASES["hmr_then_paired_corrections"]
    program, layout = with_inputs(data, ancillas, ops, target, initial_target="arbitrary",
                                  classical_inputs=inputs)
    result = check_clean_ancilla(program, layout.reduced_target)
    assert result.clean
    assert replay_clean_ancilla(program, result.certificate.to_dict()).clean
    # Negating one condition gives a program with the same widths and the same number of
    # operations: only the source hash tells them apart.
    negated = [*ops[:-1], HOp("cx", (1, 2), condition="!b1")]
    mutated, _ = with_inputs(data, ancillas, negated, target, initial_target="arbitrary",
                             classical_inputs=inputs)
    replayed = replay_clean_ancilla(mutated, result.certificate.to_dict())
    assert replayed.status == "not_proved" and replayed.reason == "certificate_source_mismatch"


def _seeded_program(rng):
    """A random program over the whole grammar, the target anywhere among 1-3 ancillas."""
    data, ancillas = rng.randint(1, 2), rng.randint(1, 3)
    width = data + ancillas
    target = rng.randrange(data, width)
    candidates = ["b4", "b5"]
    known = set(candidates)
    ops = []
    for _ in range(rng.randint(1, 7)):
        kind = rng.choice(("x", "cx", "ccx", "mcx", "swap", "cswap", "z", "cz", "reset", "hmr",
                           "measure_z", "store", "invert", "oxor", "cond"))
        wires = rng.sample(range(width), min(width, 3))
        if kind in {"hmr", "measure_z"}:
            slot = rng.choice(("b0", "b1", "b4"))
            ops.append(HOp(kind, (wires[0],), slot=slot))
            known.add(slot)
        elif kind == "reset":
            ops.append(HOp("reset", (wires[0],)))
        elif kind == "store":
            slot = rng.choice(("b2", "b5"))
            ops.append(HOp("store", slot=slot, value=rng.randint(0, 1)))
            known.add(slot)
        elif kind == "invert":
            ops.append(HOp("invert", slot=rng.choice(sorted(known))))
        elif kind == "oxor":
            ops.append(HOp("oxor", slot=rng.choice(sorted(known)), source=rng.choice(sorted(known))))
        elif kind == "cond":
            name = rng.choice(sorted(known))
            gate = rng.choice((("cx", 2), ("x", 1), ("cz", 2)))
            if len(wires) >= gate[1]:
                ops.append(HOp(gate[0], tuple(wires[:gate[1]]),
                               condition=("!" if rng.random() < 0.5 else "") + name))
        else:
            arity = {"x": 1, "cx": 2, "ccx": 3, "mcx": 3, "swap": 2, "cswap": 3,
                     "z": 1, "cz": 2}[kind]
            if len(wires) >= arity:
                ops.append(HOp(kind, tuple(wires[:arity])))
    first = {}
    for op in ops:
        for name in (op.condition, op.source):
            if name:
                first.setdefault(name.removeprefix("!"), "read")
        if op.kind in ("invert", "oxor"):
            first.setdefault(op.slot, "read")
        if op.kind in ("store", "hmr", "measure_z"):
            first.setdefault(op.slot, "write")
    inputs = tuple(slot for slot in candidates if first.get(slot) == "read")
    return data, ancillas, ops, target, inputs


def test_seeded_programs_agree_on_both_engines():
    """Several ancillas and the target at any position exercise the wire remapping."""
    rng = random.Random(20261112)
    checked = witnesses = 0
    for case in range(300):
        data, ancillas, ops, target, inputs = _seeded_program(rng)
        arbitrary = rng.random() < 0.5
        errors = _worst_case(data, ancillas, ops, target, inputs, arbitrary)
        program, layout = with_inputs(data, ancillas, ops, target,
                                      initial_target="arbitrary" if arbitrary else "clean",
                                      classical_inputs=inputs)
        for engine, check in ENGINES.items():
            result = check(program, layout.reduced_target)
            assert result.status == ("clean" if not errors else "not_clean"), (case, engine)
            if errors:
                assignment = result.witness.assignment if engine == "pauli" else result.assignment
                probability = (result.witness.probability if engine == "pauli"
                               else result.probability)
                seen = layout.explain(assignment)
                key = (seen["data"], seen["initial_target"] or 0,
                       tuple(seen["classical_inputs"][slot] for slot in inputs))
                assert errors[key] == probability > 0, (case, engine)
                witnesses += 1
            checked += 1
    assert checked == 600 and witnesses > 100
