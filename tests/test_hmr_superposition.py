"""``2^{-M/2}`` in the Kraus action, and why the uniform-outcome sentence is restricted.

``PHASE_HMR_SPEC.md`` states the factor and restricts the uniform-probability claim to
computational-basis inputs. On a basis input the oracle's integer amplitudes give the expected
``2^{-M}`` per outcome. On a general superposition the same Kraus operator can be
deterministic: ``H|+> = |0>``, so the theorem cannot be read as a statement about every
outcome of every input. That second half is a two-line calculation over ``C^2``, kept here so
the restriction is executable rather than prose.
"""
from __future__ import annotations

import pytest

from symq.phase import PhaseProgram
from symq.phase_oracle import run_program

DATA = 1
ANCILLA = 1
INV_SQRT2 = 2 ** -0.5


def norm(program: PhaseProgram, data: int, outcomes: int) -> int:
    """Sum of absolute integer amplitudes; the oracle omits the ``2^{-M/2}`` factor."""
    return sum(abs(a) for a in run_program(program, data, outcomes).values())


def hmr_probabilities(amplitudes: tuple[complex, complex]) -> tuple[float, float]:
    """Outcome probabilities of a Hadamard followed by a measurement on one qubit."""
    zero, one = amplitudes
    outcome_0 = INV_SQRT2 * (zero + one)
    outcome_1 = INV_SQRT2 * (zero - one)
    return abs(outcome_0) ** 2, abs(outcome_1) ** 2


def test_a_basis_input_has_uniform_outcomes_after_normalisation():
    program = PhaseProgram(data=DATA, ancillas=ANCILLA)
    program.hmr(0)
    norms = [norm(program, 0, m) for m in range(1 << program.measurements)]
    assert norms == [1, 1]
    probabilities = [n * n / 2 ** program.measurements for n in norms]
    assert probabilities == [0.5, 0.5]
    assert abs(sum(probabilities) - 1.0) < 1e-12


def test_hmr_of_a_superposition_is_deterministic():
    """``H|+> = |0>``: outcome 0 with probability 1, outcome 1 with probability 0."""
    probabilities = hmr_probabilities((INV_SQRT2, INV_SQRT2))
    assert probabilities[0] == pytest.approx(1.0)
    assert probabilities[1] == pytest.approx(0.0, abs=1e-15)


def test_hmr_of_a_basis_state_is_a_fair_coin():
    """The uniformity claim does hold on basis inputs, which is all the specification says."""
    probabilities = hmr_probabilities((1.0, 0.0))
    assert probabilities == (pytest.approx(0.5), pytest.approx(0.5))


def test_the_oracle_resolves_every_outcome_of_every_input():
    program = PhaseProgram(data=DATA, ancillas=ANCILLA)
    program.hmr(0)
    for x in range(1 << DATA):
        for outcomes in range(1 << program.measurements):
            assert norm(program, x, outcomes) >= 1
