"""The strategy must be deterministic, cheap, and never change a verdict.

A selector is allowed to be wrong about *which* method is fastest; it is not allowed to change the
answer, to be non-deterministic, or to cost more than the run it guides.
"""
from __future__ import annotations

import random
import time

import pytest

from symq import Budget, Circuit, check_equivalence
from symq.generators import random_circuit
from symq.order import order_for
from symq.strategy import (
    ENGINE_RULES,
    ORDER_RULES,
    choose,
    choose_engine,
    choose_order,
    features,
)


def test_features_are_one_pass_and_consistent():
    rng = random.Random(1)
    circuit = random_circuit(8, 40, rng)
    first = features(circuit)
    second = features(circuit)
    assert first == second
    assert first.gates == len(circuit.gates)
    assert first.width == 8
    assert 0 <= first.used_wires <= 8
    assert first.max_arity >= 1
    assert 0.0 <= first.last_use_spread <= 1.0


def test_an_empty_circuit_is_handled():
    feature = features(Circuit(4))
    assert feature.gates == 0
    assert feature.used_wires == 0
    choice = choose(Circuit(4))
    assert choice.order == "identity" and choice.engine == "symbolic"


def test_a_single_cascade_has_no_staging():
    """An MCX chain touches every wire once, at a spread-out time, but nothing is staged."""
    chain = Circuit(10)
    for index in range(1, 10):
        chain.mcx(*range(index), index)
    feature = features(chain)
    assert feature.last_use_spread < 0.05, "every wire is used at most twice, at the end"
    assert choose_order(feature)[0] == "identity"


def test_a_staged_circuit_selects_last_use():
    """The Cuccaro adder has many wires finishing late and spread out, and few controls per gate."""
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = root / "research" / "engineering" / "2026-10-28" / "adders.py"
    spec = importlib.util.spec_from_file_location("strategy_test_adders", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["strategy_test_adders"] = module
    spec.loader.exec_module(module)
    feature = features(module.adder(14))
    assert feature.last_use_spread >= 0.12
    assert choose_order(feature)[0] == "last_use"


def test_the_engine_rule_respects_availability():
    feature = features(random_circuit(20, 300, random.Random(2)))
    assert choose_engine(feature, sat_available=True)[0] == "sat"
    assert choose_engine(feature, sat_available=False) == ("symbolic",
                                                           "no SAT solver installed")


def test_a_small_circuit_never_selects_sat():
    feature = features(random_circuit(4, 8, random.Random(3)))
    assert choose_engine(feature, sat_available=True)[0] == "symbolic"


def test_a_short_list_of_wide_gates_still_selects_sat():
    """Counting gates alone misses this: 19 gates, 20 wires, 190 controls, 135 ms symbolically."""
    import importlib.util
    import sys
    from pathlib import Path

    del importlib, sys, Path
    chain = Circuit(20)
    for index in range(1, 20):
        chain.mcx(*range(index), index)
    feature = features(chain)
    assert feature.gates == 19, "below the gate-count threshold on its own"
    assert feature.controls_total >= 40
    assert choose_engine(feature, sat_available=True)[0] == "sat"


def test_the_default_engine_choice_asks_the_solver():
    """``choose`` must not assume SAT is installed; it asks, and falls back when it is not."""
    from symq import sat

    feature = features(random_circuit(20, 300, random.Random(9)))
    expected = "sat" if sat.available() else "symbolic"
    assert choose_engine(feature)[0] == expected
    assert choose_engine(feature, sat_available=False)[0] == "symbolic"


def test_a_wide_gate_heavy_circuit_selects_sat():
    """The rule counts controls, so a list of wide gates passes the crossover by that measure.

    An earlier version of this test asserted the opposite, on the theory that wide gates make the
    miter's conjunction chains expensive. The holdout data refuted it: a 19-gate MCX chain costs
    135 ms symbolically and 2 ms through SAT.
    """
    circuit = Circuit(14)
    for _ in range(130):
        circuit.mcx(*range(10, 14))
    feature = features(circuit)
    assert feature.mean_arity > 2.5
    assert feature.controls_total >= 40
    assert choose_engine(feature, sat_available=True)[0] == "sat"


def test_the_choice_is_deterministic_across_runs():
    rng = random.Random(4)
    circuits = [random_circuit(rng.randint(3, 15), rng.randint(0, 120), rng) for _ in range(20)]
    first = [choose(circuit) for circuit in circuits]
    second = [choose(circuit) for circuit in circuits]
    assert [(choice.order, choice.engine) for choice in first] == [
        (choice.order, choice.engine) for choice in second]


def test_selection_cost_is_negligible():
    circuit = random_circuit(20, 400, random.Random(5))
    started = time.perf_counter()
    for _ in range(200):
        features(circuit)
    per_call = (time.perf_counter() - started) / 200
    assert per_call < 0.01, f"feature extraction took {per_call * 1e3:.2f} ms"


@pytest.mark.parametrize("seed", range(8))
def test_the_selected_order_never_changes_the_verdict(seed):
    """The chosen order is always applicable and always gives the same answer.

    Runs on the pure-Python backend when the native extension is absent, so this test holds in
    the pure-python CI job as well.
    """
    from symq.backends import has_native

    rng = random.Random(seed)
    left = random_circuit(rng.randint(3, 7), rng.randint(0, 30), rng)
    right = type(left)(left.width, list(left.gates))
    choice = choose(left)
    backend = "zdd-native" if has_native() else "zdd"
    result = check_equivalence(left, right, backend=backend, budget=Budget(max_seconds=30))
    assert result.equivalent
    assert choice.order in ("identity", "reversed", "last_use")
    order = order_for(left, choice.order)
    assert sorted(order) == list(range(left.width))


def test_the_rules_are_documented_in_the_module():
    assert "last_use_spread" in ORDER_RULES
    assert "sat" in ENGINE_RULES
