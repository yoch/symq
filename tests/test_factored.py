"""Channel equivalence of the HMR fragment, checked against a density-matrix oracle."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "innovation" / "2026-10-28" / "prototype"))
sys.path.insert(0, str(ROOT / "src"))

import channel
import factored

from symq.phase import PhaseProgram, check_phase_equivalence, phase_semantics
from symq.phase_oracle import outcome_independent_unitary, run_program


def random_program(rng: random.Random, data: int, ancillas: int, ops: int) -> PhaseProgram:
    program = PhaseProgram(data, ancillas)
    for _ in range(ops):
        kind = rng.choice(["mcx", "mcx", "mcz", "hmr", "mcz_if"])
        if kind == "hmr":
            program.hmr(rng.randrange(program.width))
            continue
        count = rng.randint(1, min(3, program.width))
        qubits = rng.sample(range(program.width), count)
        if kind == "mcz_if" and program.measurements:
            program.mcz_if(rng.randrange(program.measurements), *qubits)
        elif kind == "mcx":
            program.mcx(*qubits)
        else:
            program.mcz(*qubits)
    return program


def test_the_state_vector_oracle_agrees_with_the_unnormalised_kraus_operators():
    rng = random.Random(11)
    for _ in range(30):
        program = random_program(rng, rng.randint(1, 2), rng.randint(0, 1),
                                 rng.randint(1, 7))
        for x in range(1 << program.data):
            for outcomes in range(1 << program.measurements):
                operator = channel.kraus_operator(program, outcomes)
                column = {basis: value for (basis, source), value in operator.items()
                          if source == x}
                expected = run_program(program, x, outcomes)
                assert column == expected, (program.ops, x, outcomes)


def test_every_channel_is_trace_preserving():
    """``sum_m K_m^dagger K_m = I`` on the data wires, for every program of the fragment."""
    rng = random.Random(15)
    for _ in range(40):
        program = random_program(rng, rng.randint(1, 2), rng.randint(0, 1),
                                 rng.randint(1, 7))
        assert channel.is_trace_preserving(program), program.ops


def test_channel_acts_on_data_wires_only():
    """With the ancillas traced out, the channel is a map on the data wires."""
    program = PhaseProgram(2, 1).ccx(0, 1, 2)
    program.hmr(2)
    matrix = channel.channel_matrix(program, trace_ancillas=True)
    limit = 1 << program.data
    for x, y, u, v in matrix:
        assert x < limit and y < limit and u < limit and v < limit


def test_the_factorisation_reproduces_the_full_phase():
    rng = random.Random(12)
    for _ in range(60):
        program = random_program(rng, rng.randint(1, 2), rng.randint(0, 1),
                                 rng.randint(1, 9))
        form = factored.factor(program)
        expected = phase_semantics(program)
        for x in range(1 << program.data):
            for outcomes in range(1 << program.measurements):
                claim = form.phi0.evaluate(x)
                for index, coefficient in enumerate(form.g):
                    claim ^= ((outcomes >> index) & 1) * coefficient.evaluate(x)
                assert claim == expected.phase.evaluate(x | outcomes << program.data)


def test_channel_criterion_matches_the_density_matrix_oracle():
    rng = random.Random(13)
    for _ in range(150):
        data = rng.randint(1, 2)
        ancillas = rng.randint(0, 1)
        left = random_program(rng, data, ancillas, rng.randint(1, 7))
        right = (random_program(rng, data, ancillas, rng.randint(1, 7))
                 if rng.random() < 0.85 else left)
        verdict = factored.equivalent_channel(left, right)
        assert verdict.equivalent == channel.same_channel(left, right), (
            left.ops, right.ops, verdict)


def test_an_outcome_only_phase_on_an_ancilla_keeps_the_channel():
    """Issue #50's example: ``X`` and ``hmr`` on a *scratch* wire only add ``(-1)^m``."""
    program = PhaseProgram(2, 1).x(2)
    program.hmr(2)
    identity = PhaseProgram(2, 1)
    assert check_phase_equivalence(program, identity).violations
    verdict = factored.equivalent_channel(program, identity)
    assert verdict.equivalent, verdict
    assert channel.same_channel(program, identity)


def test_hmr_on_a_data_wire_is_a_reset_and_not_the_identity():
    """The same instructions on a data wire destroy information: the channel must change."""
    program = PhaseProgram(1, 0).x(0)
    program.hmr(0)
    identity = PhaseProgram(1, 0)
    assert not factored.equivalent_channel(program, identity).equivalent
    assert not channel.same_channel(program, identity)


def test_a_non_constant_outcome_coefficient_does_change_the_channel():
    program = PhaseProgram(1, 0)
    program.hmr(0)
    program.mcz_if(0, 0)
    identity = PhaseProgram(1, 0)
    verdict = factored.equivalent_channel(program, identity)
    assert not verdict.equivalent
    assert not channel.same_channel(program, identity)


def test_logical_and_uncomputation_equals_the_reversible_circuit():
    program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    outcome = program.hmr(3)
    program.cz_if(outcome, 0, 1)
    specification = PhaseProgram(3, 1).ccx(0, 1, 2)
    assert factored.equivalent_channel(program, specification).equivalent
    assert channel.same_channel(program, specification)
    assert outcome_independent_unitary(program) is not None


def test_the_factorised_map_has_the_expected_closed_form():
    """Check (CH) directly on a program with a non-constant ``g``."""
    program = PhaseProgram(2, 1).ccx(0, 1, 2)
    program.hmr(2)
    form = factored.factor(program)
    width = program.data
    for x in range(1 << width):
        for y in range(1 << width):
            image = channel.coherence_image(program, x, y)
            same = all(a.evaluate(x) == a.evaluate(y) for a in form.g)
            sign = (-1) ** (form.phi0.evaluate(x) ^ form.phi0.evaluate(y))
            target_x = sum(value.evaluate(x) << wire
                           for wire, value in enumerate(form.outputs[:width]))
            target_y = sum(value.evaluate(y) << wire
                           for wire, value in enumerate(form.outputs[:width]))
            if same:
                assert image == {(target_x, target_y): sign}, (x, y, image)
            else:
                assert image == {}, (x, y, image)


def test_invariant_f1_and_f2_hold_on_every_generated_program():
    rng = random.Random(14)
    for _ in range(80):
        program = random_program(rng, rng.randint(1, 2), rng.randint(0, 1),
                                 rng.randint(1, 8))
        form = factored.factor(program)
        mask = ((1 << form.measurements) - 1) << form.data
        for output in form.outputs:
            assert all(not monomial & mask for monomial in output.terms)
        assert all(not monomial & mask for monomial in form.phi0.terms)
        assert all(not monomial & mask for value in form.g for monomial in value.terms)


@pytest.mark.parametrize("seed", range(20))
def test_trace_preserving_unitary_programs_act_as_their_map(seed):
    rng = random.Random(2000 + seed)
    program = random_program(rng, 2, 1, rng.randint(2, 7))
    table = outcome_independent_unitary(program)
    if table is None:
        return
    data = program.data
    for x in range(1 << data):
        image = channel.coherence_image(program, x, x)
        assert len(image) == 1, image
        ((u, v), value), = image.items()
        assert u == v or u >> data == v >> data
        assert value == 1
    del table


@pytest.mark.parametrize("seed", range(20))
def test_outcome_independent_programs_act_as_their_reversible_map(seed):
    """O1+O2 programs are unitaries: every input basis state maps to one output of weight 1."""
    rng = random.Random(2000 + seed)
    program = random_program(rng, 2, 1, rng.randint(2, 7))
    table = outcome_independent_unitary(program)
    if table is None:
        return
    size = 1 << program.data
    for x in range(size):
        image = channel.coherence_image(program, x, x)
        assert len(image) == 1, image
        ((u, v), value), = image.items()
        assert u == v, (u, v)
        assert value == 1
        assert u & (size - 1) == table[x][0] & (size - 1)

