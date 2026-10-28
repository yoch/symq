"""The affine encoder must agree with exhaustive execution, in every mode the contract allows.

This is the acceptance test of issue #69: no size claim matters until the encoding is proved to
decide the same predicate as the transition encoder and as concrete execution. Every case is
checked against ``Circuit.run`` on every input of small circuits, and against the existing SSA
encoder on the same instance.
"""
from __future__ import annotations

import random

import pytest

from symq import Budget, Circuit, Gate
from symq.generators import equivalent_variant, mutate, random_circuit
from symq.sat import Contract, available
from symq.sat.encoding import solver_available
from symq.sat.miter_xag import check_xag_equivalence

pytestmark = pytest.mark.skipif(not (available() and solver_available()),
                                reason="python-sat is not installed")


def exhaustive(left: Circuit, right: Circuit, contract: Contract | None = None) -> bool:
    """Reference: concrete execution on every legal input, no encoding involved."""
    contract = contract or Contract()
    for x in range(1 << left.width):
        if any(((x >> wire) & 1) != value for wire, value in contract.input_constants.items()):
            continue
        a, b = left.run(x), right.run(x)
        for left_wire, right_wire in pairs(contract, left.width):
            if ((a >> left_wire) & 1) != ((b >> right_wire) & 1):
                return False
        for wire in contract.restored_wires:
            initial = (x >> wire) & 1
            if ((a >> wire) & 1) != initial or ((b >> wire) & 1) != initial:
                return False
    return True


def pairs(contract: Contract, width: int) -> list[tuple[int, int]]:
    if contract.output_map:
        return sorted(contract.output_map.items())
    if contract.observed_outputs is not None:
        return [(wire, wire) for wire in contract.observed_outputs]
    return [(wire, wire) for wire in range(width)]


@pytest.mark.parametrize("seed", range(40))
def test_the_verdict_matches_exhaustive_execution(seed):
    rng = random.Random(seed)
    width = rng.randint(1, 6)
    left = random_circuit(width, rng.randint(0, 16), rng)
    right = (equivalent_variant(left, rng, steps=rng.randint(1, 6))
             if rng.random() < 0.5 else random_circuit(width, rng.randint(0, 16), rng))
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=20))
    assert verdict.outcome in ("equivalent", "different"), verdict
    expected = "equivalent" if exhaustive(left, right) else "different"
    assert verdict.outcome == expected, (seed, left.gates, right.gates)
    if verdict.outcome == "different":
        assert verdict.witness_checked, "a counterexample must be replayed"
        assert left.run(verdict.witness) != right.run(verdict.witness)


@pytest.mark.parametrize("seed", range(25))
def test_the_two_encoders_agree(seed):
    """The XAG and SSA encoders must decide the same predicate on the same instance."""
    from symq.sat import check_sat_equivalence

    rng = random.Random(1000 + seed)
    width = rng.randint(2, 6)
    left = random_circuit(width, rng.randint(1, 14), rng)
    right = (equivalent_variant(left, rng, steps=4) if rng.random() < 0.5
             else mutate(left, rng, "insert")[0])
    xag = check_xag_equivalence(left, right, budget=Budget(max_seconds=20))
    ssa = check_sat_equivalence(left, right, budget=Budget(max_seconds=20))
    assert xag.outcome == ssa.outcome, (seed, xag.outcome, ssa.outcome)


def test_the_four_gate_shapes():
    for circuit in (
        Circuit(1).x(0),
        Circuit(2).cx(0, 1),
        Circuit(3).ccx(0, 1, 2),
        Circuit(5).mcx(0, 1, 2, 3, 4),
    ):
        assert check_xag_equivalence(circuit, circuit).outcome == "equivalent"


def test_a_rare_input_difference_is_found():
    width = 6
    left = Circuit(width)
    right = Circuit(width).mcx(*range(width))
    verdict = check_xag_equivalence(left, right)
    assert verdict.outcome == "different"
    assert all((verdict.witness >> wire) & 1 for wire in range(width - 1))


def test_constant_inputs_narrow_the_domain():
    left = Circuit(2)
    right = Circuit(2).cx(0, 1)
    assert check_xag_equivalence(left, right).outcome == "different"
    contract = Contract(input_constants={0: 0})
    assert check_xag_equivalence(left, right, contract).outcome == "equivalent"
    assert exhaustive(left, right, contract)


def test_observed_outputs_and_restored_wires():
    clean = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    dirty = Circuit(3).ccx(0, 1, 2)
    identity = Circuit(3)
    contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))
    assert check_xag_equivalence(clean, identity, contract).outcome == "equivalent"
    assert check_xag_equivalence(dirty, identity, contract).outcome == "different"
    assert exhaustive(clean, identity, contract)
    assert not exhaustive(dirty, identity, contract)


def test_a_wire_permutation_can_be_declared():
    left = Circuit(2).cx(0, 1).cx(1, 0)
    right = Circuit(2).cx(1, 0).cx(0, 1)
    contract = Contract(output_map={0: 1, 1: 0})
    verdict = check_xag_equivalence(left, right, contract)
    assert verdict.outcome == ("equivalent" if exhaustive(left, right, contract) else "different")


def test_a_long_xor_chain_keeps_its_semantics():
    """A linear circuit of 40 CX gates must stay exact, however long its affine forms get."""
    circuit = Circuit(8)
    for step in range(40):
        circuit.cx(step % 8, (step * 3 + 1) % 8)
    assert check_xag_equivalence(circuit, Circuit(8, list(circuit.gates))).outcome == "equivalent"
    mutant = Circuit(8, [*circuit.gates, Gate("x", (7,))])
    assert check_xag_equivalence(circuit, mutant).outcome == "different"


def test_an_invalid_gate_is_refused():
    from types import SimpleNamespace

    valid = Circuit(1).x(0)
    corrupted = Circuit(1)
    corrupted.gates.append(SimpleNamespace(name="z", qubits=(0,)))
    with pytest.raises(TypeError):
        check_xag_equivalence(valid, corrupted)


def test_an_inconclusive_run_is_not_a_verdict():
    rng = random.Random(9)
    left = random_circuit(6, 30, rng)
    right = random_circuit(6, 30, rng)
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=1e-6))
    if verdict.outcome == "inconclusive":
        assert verdict.equivalent is None


def test_an_expired_budget_is_inconclusive_not_a_verdict(monkeypatch):
    """The budget must be enforced, not merely honoured when convenient.

    The previous test only checked ``if verdict.outcome == "inconclusive"``, so it passed whatever
    happened. Here the *encoding* is made slow enough to cross a tiny deadline, and the verdict
    must be ``inconclusive`` with a budget reason and no boolean answer.
    """
    from symq.sat import miter_xag

    real_build = miter_xag.build_xag_miter

    def slow_build(*args, **kwargs):
        import time

        time.sleep(0.02)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(miter_xag, "build_xag_miter", slow_build)
    left = Circuit(3).cx(0, 1).ccx(0, 1, 2)
    right = Circuit(3).cx(0, 1).ccx(0, 1, 2)
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=0.005))
    assert verdict.outcome == "inconclusive"
    assert verdict.equivalent is None
    assert verdict.seconds >= 0.02, "the full encoding duration must be accounted"
    assert "budget" in verdict.detail or "clock" in verdict.detail

@pytest.mark.parametrize("encoder_name", ["ssa", "xag"])
def test_slow_encoding_is_charged_before_the_shared_driver(monkeypatch, encoder_name):
    """Both entry points must debit the same entry-time clock before building their CNF."""
    import time

    from symq.sat import check_sat_equivalence, miter, miter_xag

    module = miter if encoder_name == "ssa" else miter_xag
    fn = check_sat_equivalence if encoder_name == "ssa" else check_xag_equivalence
    symbol = "build_miter" if encoder_name == "ssa" else "build_xag_miter"
    actual = getattr(module, symbol)

    def slow_builder(*args, **kwargs):
        time.sleep(0.025)
        return actual(*args, **kwargs)

    monkeypatch.setattr(module, symbol, slow_builder)
    circuit = Circuit(2).cx(0, 1)
    verdict = fn(circuit, Circuit(2, list(circuit.gates)),
                 budget=Budget(max_seconds=0.005))
    assert verdict.outcome == "inconclusive", verdict
    assert "encoding" in verdict.detail
    assert verdict.seconds >= 0.025


def test_late_unsat_cannot_be_certified_as_within_budget(monkeypatch):
    """Even a solver that ignores its interrupt cannot return an in-budget UNSAT verdict."""
    import time

    from symq.sat import miter

    class SlowUnsat:
        def interrupt(self):
            return None

        def conf_budget(self, _limit):
            return None

        def solve_limited(self, *, expect_interrupt):
            time.sleep(0.025)
            return False

        def delete(self):
            return None

    class SlowFactory:
        name = "synthetic"

        def __call__(self, **_kwargs):
            return SlowUnsat()

    monkeypatch.setattr(miter, "_solver_factory", lambda: SlowFactory())
    left = Circuit(2).cx(0, 1)
    verdict = check_xag_equivalence(left, Circuit(2, list(left.gates)),
                                    budget=Budget(max_seconds=0.005))
    assert verdict.outcome == "inconclusive"
    assert verdict.equivalent is None
    assert verdict.seconds >= 0.025


def test_verdict_seconds_include_model_extraction_and_solver_cleanup(monkeypatch):
    """A non-equivalent witness and the solver's cleanup must both count toward elapsed."""
    import time

    from symq.sat import miter

    actual = miter._solver_factory()

    class SlowModelFactory:
        name = actual.name

        def __call__(self, **kwargs):
            real = actual(**kwargs)

            class Wrapped:
                def __getattr__(self, name):
                    return getattr(real, name)

                def get_model(self):
                    time.sleep(0.025)
                    return real.get_model()

                def delete(self):
                    time.sleep(0.025)
                    return real.delete()

            return Wrapped()

    monkeypatch.setattr(miter, "_solver_factory", lambda: SlowModelFactory())
    left = Circuit(3).ccx(0, 1, 2)
    right = Circuit(3, [*left.gates, Gate("x", (2,))])
    verdict = check_xag_equivalence(left, right, budget=Budget(max_seconds=2))
    assert verdict.outcome == "different" and verdict.witness_checked
    assert verdict.seconds >= 0.05
    assert left.run(verdict.witness) != right.run(verdict.witness)
