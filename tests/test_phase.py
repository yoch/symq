import random

import pytest

from symq import UnsupportedOperation
from symq.phase import PhaseProgram, check_phase_equivalence, phase_semantics
from symq.phase_oracle import outcome_independent_unitary, run_program


def random_program(rng, data, ancillas, ops):
    p = PhaseProgram(data, ancillas)
    for _ in range(ops):
        kind = rng.choice(["mcx", "mcx", "mcz", "hmr", "mcz_if"])
        if kind == "hmr":
            p.hmr(rng.randrange(p.width))
            continue
        k = rng.randint(1, min(3, p.width))
        qubits = rng.sample(range(p.width), k)
        if kind == "mcz_if" and p.measurements:
            p.mcz_if(rng.randrange(p.measurements), *qubits)
        elif kind == "mcx":
            p.mcx(*qubits)
        else:
            p.mcz(*qubits)
    return p


def predicted(semantics, x, outcomes):
    assignment = x | outcomes << semantics.data
    basis = sum(f.evaluate(assignment) << w for w, f in enumerate(semantics.outputs))
    return {basis: -1 if semantics.phase.evaluate(assignment) else 1}


@pytest.mark.parametrize("seed", range(150))
def test_semantics_match_oracle_on_all_inputs_and_outcomes(seed):
    rng = random.Random(seed)
    program = random_program(rng, rng.randint(1, 3), rng.randint(0, 2), rng.randint(0, 14))
    semantics = phase_semantics(program)
    for x in range(1 << program.data):
        for m in range(1 << program.measurements):
            assert run_program(program, x, m) == predicted(semantics, x, m)


def logical_and(correction=(0, 1), measure=True):
    """target ^= x0·x1 through an ancilla AND, uncomputed by X-basis measurement."""
    p = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
    if measure:
        m = p.hmr(3)
        if correction:
            p.cz_if(m, *correction)
    return p


def test_measurement_based_uncomputation_meets_obligations():
    program = logical_and()
    assert phase_semantics(program).violations() == []
    result = check_phase_equivalence(program, PhaseProgram(3).ccx(0, 1, 2))
    assert result.equivalent and result.up_to_global_phase
    table = outcome_independent_unitary(program)
    assert table == {x: (x ^ (4 if x & 3 == 3 else 0), 1) for x in range(8)}


@pytest.mark.parametrize(
    ("program", "obligation"),
    [
        (logical_and(correction=None), "O2"),
        (logical_and(correction=(0, 2)), "O2"),
        (logical_and(measure=False), "O1"),
    ],
)
def test_broken_uncomputation_is_rejected_and_oracle_agrees(program, obligation):
    violations = phase_semantics(program).violations()
    assert violations and violations[0].startswith(obligation)
    assert outcome_independent_unitary(program) is None
    result = check_phase_equivalence(program, PhaseProgram(3).ccx(0, 1, 2))
    assert not result.equivalent and result.violations


def test_global_phase_is_reported_separately():
    minus_identity = PhaseProgram(1).x(0).z(0).x(0).z(0)
    result = check_phase_equivalence(minus_identity, PhaseProgram(1))
    assert not result.equivalent and result.up_to_global_phase
    assert {s for x in (0, 1) for s in outcome_independent_unitary(minus_identity)[x][1:]} == {-1}


def test_phase_difference_has_a_validated_witness():
    left, right = PhaseProgram(2).cz(0, 1), PhaseProgram(2).z(0)
    result = check_phase_equivalence(left, right)
    assert not result.equivalent and not result.up_to_global_phase
    assert run_program(left, result.witness, 0) != run_program(right, result.witness, 0)


def test_output_difference_has_a_validated_witness():
    left, right = PhaseProgram(2).cx(0, 1), PhaseProgram(2).x(1)
    result = check_phase_equivalence(left, right)
    assert not result.equivalent
    assert run_program(left, result.witness, 0) != run_program(right, result.witness, 0)


@pytest.mark.parametrize("name", ["h", "s", "t", "y", "sdg", "rz", "measure", "reset"])
def test_out_of_fragment_gates_rejected(name):
    with pytest.raises(UnsupportedOperation):
        PhaseProgram(2).append(name, 0)


def test_feed_forward_needs_an_earlier_outcome():
    with pytest.raises(ValueError):
        PhaseProgram(2).cz_if(0, 0, 1)


def test_data_counts_must_match():
    with pytest.raises(ValueError):
        check_phase_equivalence(PhaseProgram(2), PhaseProgram(3))


def with_and_gadget(program, rng):
    """Same unitary: add and remove x_a·x_b on a fresh ancilla through HMR."""
    a, b = rng.sample(range(program.data), 2)
    out = PhaseProgram(program.data, program.ancillas + 1, list(program.ops))
    ancilla = out.width - 1
    out.ccx(a, b, ancilla)
    out.cz(ancilla, rng.randrange(program.data))
    m = out.hmr(ancilla)
    out.cz_if(m, a, b)
    return out


@pytest.mark.parametrize("seed", range(80))
def test_equivalence_verdicts_match_oracle(seed):
    rng = random.Random(seed)
    data = rng.randint(2, 3)
    base = PhaseProgram(data)
    for _ in range(rng.randint(0, 8)):
        qubits = rng.sample(range(data), rng.randint(1, data))
        (base.mcx if rng.random() < 0.6 else base.mcz)(*qubits)
    other = with_and_gadget(base, rng) if rng.random() < 0.5 else random_program(
        rng, data, rng.randint(0, 1), rng.randint(0, 8))
    left_table = outcome_independent_unitary(base)
    right_table = outcome_independent_unitary(other)
    result = check_phase_equivalence(base, other)
    if right_table is None:
        assert result.violations and not result.equivalent
        return
    assert not result.violations
    assert result.equivalent == (left_table == right_table)
    flipped = {x: (y, -s) for x, (y, s) in right_table.items()}
    assert result.up_to_global_phase == (left_table in (right_table, flipped))
    if result.witness is not None:
        assert left_table[result.witness] != right_table[result.witness]


@pytest.mark.parametrize("seed", range(200))
def test_obligations_hold_exactly_when_oracle_sees_a_clean_unitary(seed):
    rng = random.Random(seed)
    program = random_program(rng, rng.randint(1, 3), rng.randint(0, 2), rng.randint(0, 12))
    clean = not phase_semantics(program).violations()
    table = outcome_independent_unitary(program)
    assert clean == (table is not None)
    if table is not None:
        assert len({y for y, _ in table.values()}) == len(table)
