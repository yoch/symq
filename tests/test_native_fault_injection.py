"""Every allocation of the C core is made to fail, one at a time, and nothing may break.

The native core is the only part of SymQ that can crash the interpreter instead of raising. Its
tests cover budgets, invalid arguments and threads, but until this file none of them made an
allocation fail: every ``if (p == NULL)`` branch of ``_zdd.c`` was unexecuted code.

``tools/sanitize_native.py`` builds the core with ``-DSYMQ_FAULT_INJECT`` under AddressSanitizer
and UndefinedBehaviorSanitizer. In that build ``_zdd._fault_inject(k, sticky)`` makes the k-th
allocation of the module fail (and, in sticky mode, every later one, as under real exhaustion).
For each scenario below the allocations are counted, then the scenario is replayed once per
allocation and per mode. The properties are:

* the call raises ``MemoryError`` -- under the sanitizers, a use-after-free, a double free, a
  write past a buffer that was not grown or a NULL dereference aborts the run instead;
* afterwards, with the hooks disarmed, **the same manager** still gives the reference result:
  a failed operation must leave the tables consistent;
* a fresh manager gives the reference result.

The package build has no hooks, so these tests are skipped there, with that reason; the
sanitizer job requires them (``SYMQ_TEST_REQUIRE=native,fault_injection``).
"""
from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from symq import Circuit, check_equivalence
from symq.backends import NativeZDDAlgebra, NativeZDDWideAlgebra
from symq.generators import mutate, random_circuit
from symq.phase import PhaseProgram

pytestmark = [pytest.mark.native, pytest.mark.fault_injection]


def hooks():
    from symq.backends import _zdd

    return _zdd


def narrow_circuit() -> Circuit:
    return random_circuit(8, 30, random.Random(1), max_controls=3)


def wide_circuit(width: int = 100) -> Circuit:
    """Small polynomials on both sides of the 64-variable word boundary."""
    circuit = Circuit(width)
    for first in range(0, width - 2, 3):
        circuit.ccx(first, first + 1, first + 2)
    return circuit.cx(width - 1, 0).cx(62, 65).ccx(63, 64, 66).mcx(1, 64, 70, 99, 5)


def busy_circuit() -> Circuit:
    """Enough distinct products for the operation cache to outgrow its first table."""
    return random_circuit(10, 45, random.Random(7), max_controls=4)


PREFIX_CHAIN = frozenset((1 << length) - 1 for length in range(1, 91))
"""x0 + x0*x1 + ... : a diagram 90 levels deep whose every node has two live children."""


def anfs(algebra, values) -> tuple:
    return tuple(algebra.to_anf(value) for value in values)


def polynomial(algebra) -> int:
    """x0*x1 + x2*x3*x4 + x5 + 1, built through the public operations."""
    variable = algebra.variable
    value = algebra.product([variable(0), variable(1)])
    value = algebra.xor(value, algebra.product([variable(2), variable(3), variable(4)]))
    return algebra.xor(algebra.xor(value, variable(5)), algebra.one())


def hmr_program() -> PhaseProgram:
    program = PhaseProgram(3, 2)
    program.ccx(0, 1, 3).cx(2, 4)
    first = program.hmr(3)
    program.cz_if(first, 0, 1)
    second = program.hmr(4)
    program.cz_if(second, 2, 0)
    return program


@dataclass(frozen=True)
class Scenario:
    """``setup`` builds a manager and inputs without faults; ``operate`` runs under them.

    ``operate`` returns plain comparable values (ANFs, counts), never node ids: after a failed
    attempt the same polynomial may live at another id.
    """

    name: str
    setup: Callable[[], Any]
    operate: Callable[[Any], Any]


def _simulate(algebra_factory, circuit_factory) -> Scenario:
    def operate(algebra):
        return anfs(algebra, algebra.simulate(circuit_factory()))

    return Scenario("", algebra_factory, operate)


def _named(name: str, scenario: Scenario) -> Scenario:
    return Scenario(name, scenario.setup, scenario.operate)


def _collected_equivalence(_state):
    circuit = narrow_circuit()
    mutant = mutate(circuit, random.Random(3), "delete")[0]
    result = check_equivalence(circuit, mutant, backend="zdd-native",
                               backend_options={"collect_every": 4})
    return result.equivalent, result.witness


def _prepared(width: int = 8):
    algebra = NativeZDDAlgebra(width)
    return algebra, polynomial(algebra)


def _wide_outputs():
    algebra = NativeZDDWideAlgebra(100)
    return algebra, algebra.simulate(wide_circuit())


def _deep_polynomial():
    algebra = NativeZDDWideAlgebra(100)
    return algebra, algebra.from_terms(PREFIX_CHAIN)


def _clone(state):
    algebra, value = state
    fresh, roots = algebra.manager.clone_roots((value,))
    return tuple(fresh.anf(root) for root in roots)


def _hmr(algebra):
    state, phase, coefficients = algebra.simulate_hmr(hmr_program())
    return anfs(algebra, state), algebra.to_anf(phase), anfs(algebra, coefficients)


SCENARIOS = [
    Scenario("create a manager", lambda: None, lambda _state: NativeZDDAlgebra(8).node_count),
    Scenario("create a wide manager", lambda: None,
             lambda _state: NativeZDDWideAlgebra(100).node_count),
    Scenario("create a manager with a custom order and a lossy cache", lambda: None,
             lambda _state: NativeZDDAlgebra(8, order=[7, 6, 5, 4, 3, 2, 1, 0],
                                             cache_limit=16).node_count),
    _named("simulate", _simulate(lambda: NativeZDDAlgebra(8), narrow_circuit)),
    _named("simulate with a lossy cache",
           _simulate(lambda: NativeZDDAlgebra(8, cache_limit=16), narrow_circuit)),
    _named("simulate beyond 64 variables",
           _simulate(lambda: NativeZDDWideAlgebra(100), wide_circuit)),
    Scenario("equivalence with collection", lambda: None, _collected_equivalence),
    Scenario("ring operations", lambda: NativeZDDAlgebra(8),
             lambda algebra: algebra.to_anf(polynomial(algebra))),
    Scenario("terms, size and ANF export", _prepared,
             lambda state: (state[0].terms(state[1]), state[0].size(state[1]),
                            state[0].to_anf(state[1]))),
    Scenario("build from terms", lambda: NativeZDDAlgebra(8),
             lambda algebra: algebra.to_anf(algebra.from_terms({0, 3, 5, 9, 28, 200, 255}))),
    Scenario("minimum monomial", _prepared,
             lambda state: state[0].min_monomial(state[1])),
    Scenario("minimum monomial beyond 64 variables", _wide_outputs,
             lambda state: tuple(state[0].min_monomial(value) for value in state[1][60:70])),
    Scenario("rename a batch", _prepared,
             lambda state: anfs(state[0], state[0].rename_many(
                 [state[1], state[0].variable(6)], [1, 2, 3, 4, 5, 6, 7, 0]))),
    Scenario("copy live roots to a fresh manager", _prepared, _clone),
    Scenario("count live nodes", _prepared,
             lambda state: state[0].reachable_union([state[1], state[0].variable(7)])),
    Scenario("rename one root, order preserving", _prepared,
             lambda state: state[0].to_anf(state[0].manager.rename(
                 state[1], [1, 2, 3, 4, 5, 6, 7, 0]))),
    Scenario("rename one root onto a shared level (substitution)", _prepared,
             lambda state: state[0].to_anf(state[0].manager.rename(
                 state[1], [0, 0, 2, 3, 4, 5, 6, 7]))),
    _named("simulate until the lossless cache grows",
           _simulate(lambda: NativeZDDAlgebra(10), busy_circuit)),
    _named("simulate until a lossy cache grows",
           _simulate(lambda: NativeZDDAlgebra(10, cache_limit=1 << 14), busy_circuit)),
    Scenario("export an ANF deeper than the initial traversal stack", _deep_polynomial,
             lambda state: state[0].to_anf(state[1])),
    Scenario("sign-phase HMR simulation", lambda: NativeZDDAlgebra(8), _hmr),
]


def reference(scenario: Scenario) -> tuple[Any, int]:
    state = scenario.setup()
    hooks()._fault_inject(-1)
    expected = scenario.operate(state)
    return expected, hooks()._fault_calls()


def attempt(scenario: Scenario, index: int, sticky: bool) -> tuple[bool, Any, Any]:
    """Run the operation with allocation ``index`` failing; returns (failed, result, state)."""
    state = scenario.setup()
    hooks()._fault_inject(index, sticky)
    try:
        result = scenario.operate(state)
    except MemoryError:
        return True, None, state
    finally:
        hooks()._fault_inject(-1)
    return False, result, state


@pytest.fixture(autouse=True)
def disarmed():
    yield
    hooks()._fault_inject(-1)


def test_the_counter_counts_and_a_chosen_allocation_fails():
    hooks()._fault_inject(-1)
    NativeZDDAlgebra(4)
    created = hooks()._fault_calls()
    assert created >= 5  # nodes, hash table, cache, term counts, level map, order
    hooks()._fault_inject(0)
    with pytest.raises(MemoryError):
        NativeZDDAlgebra(4)
    hooks()._fault_inject(-1)
    assert NativeZDDAlgebra(4).node_count == 0


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
@pytest.mark.parametrize("sticky", [False, True], ids=["one failure", "exhaustion"])
def test_every_allocation_of_a_scenario_may_fail(scenario, sticky):
    expected, allocations = reference(scenario)
    assert allocations > 0, "the scenario allocates nothing: it tests no failure path"
    for index in range(allocations):
        failed, _result, state = attempt(scenario, index, sticky)
        # No allocation of the core is optional today: a failure that did not surface would mean
        # an unchecked NULL that happened to be survivable in this run.
        assert failed, f"allocation {index} failed but the call did not raise MemoryError"
        # The same manager, after the failure: consistent tables give the reference again.
        assert scenario.operate(state) == expected, f"allocation {index}: state not recovered"
    assert reference(scenario) == (expected, allocations)  # a fresh manager is unaffected


def test_a_sticky_failure_after_the_last_allocation_changes_nothing():
    """Arming beyond the allocations of a scenario must not fire: the index is exact."""
    scenario = next(scenario for scenario in SCENARIOS if scenario.name == "simulate")
    expected, allocations = reference(scenario)
    failed, result, _state = attempt(scenario, allocations, True)
    assert not failed and result == expected


def allocation_sites() -> dict[int, str]:
    """Source line and text of every allocation call of ``_zdd.c``, read from the file itself."""
    source = Path(hooks().__file__).with_name("_zdd.c").read_text(encoding="utf-8").splitlines()
    # The wrappers themselves call the real allocator; the sites start after the three macros.
    first = next(number for number, line in enumerate(source)
                 if line.startswith("#define realloc(")) + 1
    return {number + 1: line.strip() for number, line in enumerate(source)
            if number >= first and re.search(r"\b(malloc|calloc|realloc)\(", line)}


def test_every_allocation_site_of_the_source_was_made_to_fail():
    """The scenarios are only as good as the sites they reach: none may be left out.

    The instrumented build counts calls and injected failures per source line. Every line of
    ``_zdd.c`` that allocates must have failed at least once; a new allocation site added without
    a scenario that reaches it fails this test by name.
    """
    for scenario in SCENARIOS:
        _expected, allocations = reference(scenario)
        for index in range(allocations):
            attempt(scenario, index, False)
    sites = allocation_sites()
    assert len(sites) >= 50
    recorded = hooks()._fault_sites()
    assert set(recorded) <= set(sites), "an allocation was recorded on a line that has none"
    never_failed = {line: text for line, text in sites.items()
                    if recorded.get(line, (0, 0))[1] == 0}
    assert not never_failed, f"allocation sites never made to fail: {never_failed}"
