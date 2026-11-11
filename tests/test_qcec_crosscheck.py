"""SymQ's verdicts against MQT QCEC, an implementation that shares no code with SymQ.

A wrong ``equivalent`` is the worst thing this library can return. The differential tests of the
required check compare SymQ's engines with each other or with exhaustive execution, which stops
at about twenty wires (``tests/test_external.py`` compares with QCEC, PolyBoRi and CUDD too, in
the advisory job). QCEC decides the same question for reversible circuits (are two permutation
unitaries equal?) with decision diagrams written by other people, and it scales past
enumeration.

The CI job ``qcec-crosscheck`` installs ``mqt.qcec`` and requires these tests together with the
C core and the SAT solver: there a missing one is an error, not a skip. Elsewhere the file is
skipped with the reason.

What a pass means: on these generated pairs, ``zdd``, ``zdd-native`` and the SAT miter each
answer and give QCEC's answer (``sparse`` may refuse the widest ones), and every ``different``
comes with an input on which the circuits really differ. It is a sample, not a proof; a
disagreement would be a defect in SymQ or in QCEC, to be investigated either way. The translation
to QCEC's circuit type is checked gate by gate, so that a wrong translation cannot make both
tools agree on the wrong pair.
QCEC is configured (``symq.external.qcec.CONFIGURATION``) to run only its complete alternating
checker, so its verdicts here are proofs, not the outcome of random simulation.
"""
from __future__ import annotations

import random

import pytest

from symq import Budget, Circuit, ResourceLimitExceeded, check_equivalence
from symq.generators import MUTATIONS, equivalent_variant, mutate, random_circuit
from symq.generators.arithmetic import cuccaro_adder

pytestmark = [pytest.mark.qcec, pytest.mark.native, pytest.mark.sat]
"""All three: a cross-check from which the C core or the SAT miter is silently absent compares
less than it says. ``SYMQ_TEST_REQUIRE`` turns each missing capability into an error."""

BUDGETS = {
    # A ZDD is bounded by its nodes: a compact diagram may stand for millions of monomials.
    "zdd": Budget(max_seconds=60.0, max_nodes=2_000_000),
    "zdd-native": Budget(max_seconds=60.0, max_nodes=2_000_000),
    "sparse": Budget(max_seconds=60.0, max_terms=2_000_000),
}
QCEC_TIMEOUT = 120.0
SYMBOLIC = tuple(BUDGETS)
"""General-purpose symbolic engines. ``linear`` and ``packed`` have degree limits and are
compared with the others in ``tests/test_cross_engine.py``."""
MAY_REFUSE = {"sparse"}
"""The explicit term list is exponential on wide adders; every other engine must answer."""
NATIVE_WIDTH = 64


def qcec(left: Circuit, right: Circuit) -> bool:
    from symq.external import qcec_check

    result = qcec_check(left, right, timeout=QCEC_TIMEOUT)
    assert result.equivalent is not None, f"QCEC gave no proof: {result.verdict}"
    return result.equivalent


def symq_verdicts(left: Circuit, right: Circuit) -> dict[str, bool]:
    """``engine -> equivalent`` for every engine; witnesses are replayed here.

    An engine outside ``MAY_REFUSE`` that does not answer fails the test: a comparison that
    quietly loses an engine is weaker than it claims.
    """
    from symq.sat import check_sat_equivalence

    verdicts: dict[str, bool] = {}
    for backend in SYMBOLIC:
        if backend == "zdd-native" and left.width > NATIVE_WIDTH:
            continue  # a documented limit of that engine, not a refusal
        order = "auto" if backend.startswith("zdd") else None  # as ``symq check`` does
        try:
            result = check_equivalence(left, right, backend=backend, budget=BUDGETS[backend],
                                       order=order)
        except ResourceLimitExceeded:
            assert backend in MAY_REFUSE, f"{backend} refused a {left.width}-wire pair"
            continue
        if not result.equivalent:
            assert result.witness is not None
            assert left.run(result.witness) != right.run(result.witness), backend
        verdicts[backend] = result.equivalent
    verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=60.0))
    assert verdict.outcome in ("equivalent", "different"), f"SAT gave no verdict: {verdict}"
    if verdict.outcome == "different":
        assert verdict.witness is not None
        assert left.run(verdict.witness) != right.run(verdict.witness)
    verdicts["sat"] = verdict.outcome == "equivalent"
    return verdicts


def agree(left: Circuit, right: Circuit, label: str) -> bool:
    """Assert that SymQ and QCEC agree on the pair, and return the common verdict."""
    theirs = qcec(left, right)
    ours = symq_verdicts(left, right)
    required = {"zdd", "sat"} | ({"zdd-native"} if left.width <= NATIVE_WIDTH else set())
    assert required <= set(ours), f"{label}: missing engines {required - set(ours)}"
    assert set(ours.values()) == {theirs}, f"{label}: SymQ {ours}, QCEC {theirs}"
    return theirs


def _pairs(circuit: Circuit, seed: str):
    """An equivalent rewrite of ``circuit`` and one mutant of each kind."""
    rng = random.Random(seed)
    yield "variant", equivalent_variant(circuit, rng, steps=2 * len(circuit.gates) + 4)
    for kind in MUTATIONS:
        try:
            mutant, applied = mutate(circuit, rng, kind=kind)
        except ValueError:
            continue  # this kind does not apply to this circuit (nothing to delete, ...)
        yield applied, mutant


@pytest.mark.parametrize("seed", range(24))
def test_random_circuits_get_the_verdict_of_qcec(seed):
    rng = random.Random(f"qcec-random-{seed}")
    width = rng.randint(2, 9)
    circuit = random_circuit(width, rng.randint(1, 30), rng, max_controls=min(4, width - 1))
    seen = set()
    for label, other in _pairs(circuit, f"qcec-random-pairs-{seed}"):
        verdict = agree(circuit, other, f"seed {seed}, {label}")
        seen.add(verdict)
        # Small enough to check both tools against plain execution.
        exhaustive = all(circuit.run(x) == other.run(x) for x in range(1 << width))
        assert verdict == exhaustive, f"seed {seed}, {label}: both tools are wrong"
    assert True in seen  # the sound rewrite is always there


@pytest.mark.parametrize(("bits", "controlled"), [
    (bits, controlled) for bits in (1, 2, 3, 5, 8) for controlled in (False, True)])
def test_adders_get_the_verdict_of_qcec(bits, controlled):
    """Arithmetic circuits, up to 19 wires: the family where the engines differ most in cost."""
    adder = cuccaro_adder(bits, controlled=controlled)
    verdicts = [agree(adder, other, f"adder {bits} {controlled}, {label}")
                for label, other in _pairs(adder, f"qcec-adder-{bits}-{controlled}")]
    assert verdicts[0] is True  # the sound rewrite
    assert False in verdicts, "no mutant of an adder was found different: the test has no power"


@pytest.mark.parametrize("bits", [10, 12, 14])
def test_adders_beyond_enumeration_get_the_verdict_of_qcec(bits):
    """22 to 30 wires: no exhaustive oracle exists here, QCEC is the only independent one.

    The mutants are of every kind and at random positions. A single fixed mutant on the last
    wire would leave most gates and most outputs unconstrained: an engine that mishandled
    Toffolis on wide circuits would do so on both sides and still separate that one mutant.

    Wider adders are not mutated this way: QCEC itself does not conclude within two minutes on
    some mid-circuit mutants of the 34- and 50-wire adders (measured while writing this test).
    """
    adder = cuccaro_adder(bits)
    verdicts = []
    for round_ in range(3):
        for label, other in _pairs(adder, f"qcec-wide-{bits}-{round_}"):
            verdicts.append(agree(adder, other, f"adder {bits}, round {round_}, {label}"))
    assert verdicts.count(True) >= 3 and verdicts.count(False) >= 3 * (len(MUTATIONS) - 1)


@pytest.mark.parametrize("bits", [16, 24])
def test_the_widest_adders_get_the_verdict_of_qcec_on_a_rewrite_and_a_trailing_mutant(bits):
    """34 and 50 wires, where QCEC only concludes on easy pairs: a sound rewrite, and one extra
    CX after the adder. This constrains little (see the test above for why) and says so."""
    adder = cuccaro_adder(bits)
    rng = random.Random(f"qcec-widest-{bits}")
    assert agree(adder, equivalent_variant(adder, rng, steps=40), f"adder {bits}") is True
    broken = Circuit(adder.width, list(adder.gates)).cx(1, adder.width - 1)
    assert agree(adder, broken, f"adder {bits}, extra CX") is False


@pytest.mark.parametrize("controls", range(1, 17))
def test_a_gate_with_any_number_of_controls_gets_the_verdict_of_qcec(controls):
    """One MCX with 1 to 16 controls: against itself, with a control dropped, and conjugated."""
    width = controls + 2
    target = controls
    full = Circuit(width).mcx(*range(controls), target)
    assert agree(full, Circuit(width).mcx(*range(controls), target), "same MCX") is True
    if controls > 1:
        fewer = Circuit(width).mcx(*range(1, controls), target)
        assert agree(full, fewer, "dropped control") is False
    # Conjugating the target by a CX from the spare wire changes the function.
    spare = width - 1
    conjugated = Circuit(width).cx(spare, 0).mcx(*range(controls), target).cx(spare, 0)
    assert agree(full, conjugated, "conjugated control") is False


@pytest.mark.parametrize("seed", range(12))
def test_circuits_with_many_controls_get_the_verdict_of_qcec(seed):
    """Random circuits whose gates take up to all the other wires as controls."""
    rng = random.Random(f"qcec-controls-{seed}")
    width = rng.randint(7, 13)
    circuit = random_circuit(width, rng.randint(4, 16), rng, max_controls=width - 1)
    assert max(len(gate.qubits) for gate in circuit.gates) >= 5
    for label, other in _pairs(circuit, f"qcec-controls-pairs-{seed}"):
        verdict = agree(circuit, other, f"controls seed {seed}, {label}")
        exhaustive = all(circuit.run(x) == other.run(x) for x in range(1 << width))
        assert verdict == exhaustive, f"controls seed {seed}, {label}: both tools are wrong"


@pytest.mark.parametrize("seed", range(20))
def test_the_translation_to_qcec_keeps_every_gate(seed):
    """Gate by gate: same number of gates, each an X with the same controls and target.

    Without this a translation that dropped a control would be applied to both circuits of a
    pair, and SymQ and QCEC could then agree about a pair that is not the one SymQ checked.
    """
    from symq.external import to_quantum_computation

    rng = random.Random(f"qcec-translation-{seed}")
    width = rng.randint(1, 20)
    circuit = random_circuit(width, rng.randint(0, 40), rng, max_controls=max(0, width - 1))
    computation = to_quantum_computation(circuit)
    assert computation.num_qubits == circuit.width
    operations = list(computation)
    assert len(operations) == len(circuit.gates)
    for gate, operation in zip(circuit.gates, operations):
        *controls, target = gate.qubits
        assert operation.name == "x"
        assert list(operation.targets) == [target]
        assert sorted(control.qubit for control in operation.controls) == sorted(controls)
        assert all(control.type_.name == "Pos" for control in operation.controls)


def test_the_comparison_is_not_vacuous(monkeypatch):
    """If an engine lied, ``agree`` would fail: check it with an engine made to lie."""
    import symq.external

    real = symq.external.qcec_check

    def lying(left, right, *, timeout=0.0):
        result = real(left, right, timeout=timeout)
        return type(result)(verdict=result.verdict, equivalent=not result.equivalent,
                            check_seconds=result.check_seconds,
                            preprocessing_seconds=result.preprocessing_seconds)

    monkeypatch.setattr(symq.external, "qcec_check", lying)
    adder = cuccaro_adder(2)
    with pytest.raises(AssertionError, match="SymQ"):
        agree(adder, adder, "identical circuits")


def test_engines_that_all_ignored_toffolis_on_wide_circuits_would_be_caught(monkeypatch):
    """The defect a single trailing mutant cannot see: every SymQ engine wrong in the same way.

    SymQ's side is made to drop every Toffoli of circuits of 20 wires or more, before any
    engine sees them. Both circuits of a pair lose the same gates, so a sound rewrite stays
    equivalent and a late mutant stays different; only mutants of every kind, at random
    positions, expose it.
    """
    import sys

    # This very module object: pytest may have imported the file under another name than
    # ``tests.test_qcec_crosscheck``, and patching a second copy would change nothing.
    module = sys.modules[__name__]
    real = module.symq_verdicts

    def without_toffolis(circuit: Circuit) -> Circuit:
        if circuit.width < 20:
            return circuit
        return Circuit(circuit.width, [gate for gate in circuit.gates if len(gate.qubits) != 3])

    monkeypatch.setattr(module, "symq_verdicts",
                        lambda left, right: real(without_toffolis(left), without_toffolis(right)))
    adder = cuccaro_adder(10)
    disagreements = 0
    for label, other in _pairs(adder, "qcec-wide-10-0"):
        try:
            agree(adder, other, label)
        except AssertionError:
            disagreements += 1
    assert disagreements >= 1
