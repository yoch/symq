"""SymQ's verdicts against MQT QCEC, an implementation that shares no code with SymQ.

A wrong ``equivalent`` is the worst thing this library can return. Every other differential test
compares SymQ's engines with each other or with exhaustive execution, which stops at about twenty
wires. QCEC decides the same question for reversible circuits (are two permutation unitaries
equal?) with decision diagrams written by other people, and it scales past enumeration.

The CI job ``qcec-crosscheck`` installs ``mqt.qcec`` and requires these tests: there a missing
QCEC is an error, not a skip. Elsewhere they are skipped with the reason.

What a pass means: on these generated pairs, every SymQ engine that answers gives QCEC's answer,
and every ``different`` comes with an input on which the circuits really differ. It is a sample,
not a proof; a disagreement would be a defect in SymQ or in QCEC, to be investigated either way.
QCEC is configured (``symq.external.qcec.CONFIGURATION``) to run only its complete alternating
checker, so its verdicts here are proofs, not the outcome of random simulation.
"""
from __future__ import annotations

import random

import pytest

from symq import Budget, Circuit, ResourceLimitExceeded, check_equivalence, has_native
from symq.generators import MUTATIONS, equivalent_variant, mutate, random_circuit
from symq.generators.arithmetic import cuccaro_adder

pytestmark = pytest.mark.qcec

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


def qcec(left: Circuit, right: Circuit) -> bool:
    from symq.external import qcec_check

    result = qcec_check(left, right, timeout=QCEC_TIMEOUT)
    assert result.equivalent is not None, f"QCEC gave no proof: {result.verdict}"
    return result.equivalent


def symq_verdicts(left: Circuit, right: Circuit) -> dict[str, bool]:
    """``engine -> equivalent`` for every engine that answers; witnesses are replayed here."""
    from symq.sat import available, check_sat_equivalence

    verdicts: dict[str, bool] = {}
    for backend in SYMBOLIC:
        if backend == "zdd-native" and (not has_native() or left.width > 64):
            continue
        order = "auto" if backend.startswith("zdd") else None  # as ``symq check`` does
        try:
            result = check_equivalence(left, right, backend=backend, budget=BUDGETS[backend],
                                       order=order)
        except ResourceLimitExceeded:
            continue  # a refusal is allowed; a wrong answer is not
        if not result.equivalent:
            assert result.witness is not None
            assert left.run(result.witness) != right.run(result.witness), backend
        verdicts[backend] = result.equivalent
    if available():
        verdict = check_sat_equivalence(left, right, budget=Budget(max_seconds=60.0))
        if verdict.outcome in ("equivalent", "different"):
            if verdict.outcome == "different":
                assert verdict.witness is not None
                assert left.run(verdict.witness) != right.run(verdict.witness)
            verdicts["sat"] = verdict.outcome == "equivalent"
    return verdicts


def agree(left: Circuit, right: Circuit, label: str) -> bool:
    """Assert that SymQ and QCEC agree on the pair, and return the common verdict."""
    theirs = qcec(left, right)
    ours = symq_verdicts(left, right)
    assert ours.keys() & set(SYMBOLIC), f"{label}: no symbolic engine answered ({ours})"
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
        if width <= 9:  # small enough to check both tools against plain execution
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


@pytest.mark.parametrize("bits", [12, 16, 24])
def test_wide_adders_beyond_enumeration_get_the_verdict_of_qcec(bits):
    """26 to 50 wires: no exhaustive oracle exists here, QCEC is the only independent one."""
    adder = cuccaro_adder(bits)
    rng = random.Random(f"qcec-wide-{bits}")
    assert agree(adder, equivalent_variant(adder, rng, steps=40), f"wide adder {bits}") is True
    broken = Circuit(adder.width)
    for gate in adder.gates:
        broken.mcx(*gate.qubits)
    broken.cx(1, adder.width - 1)  # one extra CX after a permutation: different by construction
    assert agree(adder, broken, f"wide adder {bits}, extra CX") is False


def test_a_gate_with_many_controls_gets_the_verdict_of_qcec():
    """One MCX with 11 controls against the same gate with one control dropped."""
    width = 12
    full = Circuit(width).mcx(*range(width))
    fewer = Circuit(width).mcx(*range(1, width))
    assert agree(full, Circuit(width).mcx(*range(width)), "same MCX") is True
    assert agree(full, fewer, "dropped control") is False


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
