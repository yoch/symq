"""Oracle-backed tests for isolated Z8 phase-polynomial research (issue #80)."""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "phase8"))
from phase8 import Program8, check_equivalence, eval_phase, lift_anf, symbolic

from symq.anf import ANF
from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram, phase_semantics
from symq.resources import Budget, ResourceLimitExceeded


def random_program(rng: random.Random, width: int, gates: int) -> Program8:
    p = Program8(width)
    names = ["x", "cx", "ccx", "mcx", "t", "tdg", "s", "sdg", "z", "cz", "ccz"]
    for _ in range(gates):
        name = rng.choice(names)
        arity = {"x": 1, "cx": 2, "ccx": 3, "mcx": min(4, width),
                 "t": 1, "tdg": 1, "s": 1, "sdg": 1, "z": 1, "cz": 2, "ccz": 3}[name]
        if arity > width or (name == "mcx" and width < 2):
            continue
        p.append(name, *rng.sample(range(width), arity))
    return p


@pytest.mark.parametrize("seed", range(70))
def test_symbolic_matches_independent_integer_oracle(seed):
    rng = random.Random(2026102800 + seed)
    width = rng.randint(1, 5)
    p = random_program(rng, width, rng.randint(0, 15))
    sem = symbolic(p, Budget(max_terms=100_000, max_seconds=10))
    for x in range(1 << width):
        assert sem.run(x) == p.run(x), (seed, x, p.gates)


def test_parity_lift_preserves_minus_two_cross_term():
    value = ANF.variable(0) ^ ANF.variable(1)
    lift = lift_anf(value)
    assert lift == {1: 1, 2: 1, 3: 6}  # x XOR y = x + y - 2xy (mod 8)
    assert all(eval_phase(lift, x) == value.evaluate(x) for x in range(4))


def test_t_after_cx_is_not_two_independent_t_gates():
    left = Program8(2).cx(0, 1).t(1)
    right = Program8(2).t(0).t(1).cx(0, 1)
    result = check_equivalence(left, right)
    assert result.status == "different"
    assert result.witness is not None
    assert left.run(result.witness)[1] != right.run(result.witness)[1]


def test_global_phase_is_exactly_detected():
    # X T X T acts as omega I; no H or ancilla is involved.
    left = Program8(1).x(0).t(0).x(0).t(0)
    right = Program8(1)
    verdict = check_equivalence(left, right)
    assert verdict.status == "global_phase"
    assert verdict.global_phase_exponent == 1
    assert all(left.run(x) == (x, 1) for x in range(2))


def test_phase_identities_and_reversible_mutants():
    identity = Program8(2)
    assert check_equivalence(Program8(2).t(1).tdg(1), identity).status == "equal"
    assert check_equivalence(Program8(2).s(0).s(0), Program8(2).z(0)).status == "equal"
    assert check_equivalence(Program8(2).t(0), Program8(2).tdg(0)).status == "different"
    assert check_equivalence(Program8(2).cx(0, 1), identity).status == "different"


def test_mod8_agrees_with_existing_sign_phase_fragment():
    small = Program8(3).x(0).cx(0, 1).ccx(0, 1, 2).cz(0, 2).z(1)
    old = PhaseProgram(3).x(0).cx(0, 1).ccx(0, 1, 2).cz(0, 2).z(1)
    a, b = symbolic(small), phase_semantics(old)
    for x in range(8):
        out, phase = a.run(x)
        expected_out = sum(p.evaluate(x) << i for i, p in enumerate(b.outputs))
        expected_phase = 4 * b.phase.evaluate(x)
        assert (out, phase) == (expected_out, expected_phase)


def test_unsupported_gates_and_post_mutation_fail_closed():
    with pytest.raises(UnsupportedOperation):
        Program8(1).append("h", 0)
    with pytest.raises(UnsupportedOperation):
        Program8(1).append("measure", 0)
    with pytest.raises(UnsupportedOperation):
        Program8(2).append("cx", 0, 0)
    p = Program8(2).t(0)
    p.gates.append(object())
    with pytest.raises(UnsupportedOperation):
        symbolic(p)


def test_symbolic_term_guard_refuses_instead_of_approximating():
    with pytest.raises(ResourceLimitExceeded):
        symbolic(Program8(2).cx(0, 1).t(1), Budget(max_terms=2))


def test_nonconstant_phase_witness_is_independent_of_constant_offset():
    # The global offset must not disguise a relative phase difference.
    a = Program8(2).x(0).t(0).x(0).t(0).t(1)
    b = Program8(2)
    result = check_equivalence(a, b)
    assert result.status == "different"
    assert result.witness is not None
    assert (a.run(result.witness)[1] - b.run(result.witness)[1]) % 8 != 1


def test_equivalence_spends_one_shared_deadline_on_both_programs():
    """Two symbolic passes cannot each restart the caller's wall-clock budget."""
    import time
    from unittest.mock import patch

    real = symbolic

    def delayed(program, budget=None, *, _guard=None):
        time.sleep(0.02)
        return real(program, budget, _guard=_guard)

    with patch.object(sys.modules["phase8"], "symbolic", delayed):
        with pytest.raises(ResourceLimitExceeded, match="seconds"):
            check_equivalence(Program8(1), Program8(1), Budget(max_seconds=0.025))
