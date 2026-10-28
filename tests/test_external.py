import random
from pathlib import Path

import pytest

from symq import Circuit, check_equivalence, make_algebra, simulate
from symq.corpus import load_corpus
from symq.external import EXTERNAL_BACKENDS, UNAVAILABLE, qcec_check, versions
from symq.generators import equivalent_variant, mutate, random_circuit

CORPUS = Path(__file__).resolve().parents[1] / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json"
ALGEBRAS = ["polybori", "cudd-bdd", "cudd-zdd"]


def external(name):
    if name not in EXTERNAL_BACKENDS:
        pytest.skip(f"{name} unavailable: {UNAVAILABLE.get(name)}")
    return EXTERNAL_BACKENDS[name]


def supported_corpus():
    return [e for e in load_corpus(CORPUS).entries if e.supported]


def test_availability_is_reported_for_every_tool():
    for name in ALGEBRAS:
        assert (name in EXTERNAL_BACKENDS) != (name in UNAVAILABLE)
    assert (qcec_check is None) == ("qcec" in UNAVAILABLE)
    assert set(versions()) == {"passagemath-brial", "dd", "mqt.qcec", "mqt.core"}


@pytest.mark.parametrize("name", ALGEBRAS)
@pytest.mark.parametrize("seed", range(60))
def test_external_algebra_matches_exact_anf(name, seed):
    algebra_class = external(name)
    circuit = random_circuit(6, 10, random.Random(seed))
    algebra = make_algebra(algebra_class, circuit.width)
    outputs = simulate(circuit, algebra)
    expected = list(circuit.symbolic())
    assert [algebra.to_anf(v) for v in outputs] == expected
    assert all(algebra.equal(algebra.from_anf(a), v) for a, v in zip(expected, outputs))


@pytest.mark.parametrize("reordering", (False, True))
@pytest.mark.parametrize("name", ["cudd-bdd", "cudd-zdd"])
def test_cudd_to_anf_survives_node_reuse(name, reordering):
    """The memo of ``to_anf`` was keyed by node id while the cofactors it created were released:
    CUDD reused freed nodes for other functions and the memo returned their transforms."""
    algebra = external(name)(16, reordering=reordering)
    circuit = random_circuit(16, 100, random.Random(7), max_controls=2)
    outputs = simulate(circuit, algebra)
    reference = make_algebra("zdd", circuit.width)
    expected = [reference.to_anf(v) for v in simulate(circuit, reference)]
    assert [algebra.to_anf(v) for v in outputs] == expected


@pytest.mark.parametrize("name", ALGEBRAS)
def test_external_equality_on_independently_built_values(name):
    algebra = make_algebra(external(name), 3)
    x0, x1, x2 = (algebra.variable(i) for i in range(3))
    left = algebra.xor(algebra.product([x0, x1]), x2)
    right = algebra.xor(x2, algebra.product([x1, x0]))
    assert algebra.equal(left, right) and algebra.equal(right, left)
    assert not algebra.equal(left, algebra.xor(right, algebra.one()))
    assert not algebra.equal(left, x2)
    assert algebra.equal(algebra.xor(left, right), algebra.zero())


@pytest.mark.parametrize("name", ALGEBRAS)
def test_external_algebra_matches_symq_on_the_corpus(name):
    algebra_class = external(name)
    for entry in supported_corpus():
        circuit = entry.load()
        reference = make_algebra("sparse", circuit.width)
        expected = [reference.to_anf(v) for v in simulate(circuit, reference)]
        algebra = make_algebra(algebra_class, circuit.width)
        outputs = simulate(circuit, algebra)
        assert [algebra.to_anf(v) for v in outputs] == expected, entry.name
        assert algebra.native_nodes(outputs) > 0


@pytest.mark.parametrize("name", ALGEBRAS)
def test_external_equivalence_verdicts_and_witnesses(name):
    algebra_class = external(name)
    for entry in supported_corpus():
        circuit = entry.load()
        rng = random.Random(entry.name)
        variant = equivalent_variant(circuit, rng, steps=len(circuit.gates))
        mutant, _ = mutate(circuit, rng, kind="insert")
        assert check_equivalence(circuit, variant, backend=algebra_class).equivalent
        ours = check_equivalence(circuit, mutant)
        theirs = check_equivalence(circuit, mutant, backend=algebra_class)
        assert not theirs.equivalent and theirs.backend == name
        assert theirs.output == ours.output
        assert circuit.run(theirs.witness) != mutant.run(theirs.witness)


def test_qcec_proves_equivalence_and_non_equivalence_on_the_corpus():
    if qcec_check is None:
        pytest.skip(f"qcec unavailable: {UNAVAILABLE.get('qcec')}")
    for entry in supported_corpus():
        circuit = entry.load()
        rng = random.Random(entry.name)
        variant = equivalent_variant(circuit, rng, steps=len(circuit.gates))
        mutant, _ = mutate(circuit, rng, kind="insert")
        assert qcec_check(circuit, variant).equivalent is True, entry.name
        result = qcec_check(circuit, mutant)
        assert result.equivalent is False and result.verdict == "not_equivalent", entry.name


def test_qcec_rejects_width_mismatch():
    if qcec_check is None:
        pytest.skip(f"qcec unavailable: {UNAVAILABLE.get('qcec')}")
    with pytest.raises(ValueError):
        qcec_check(Circuit(2).x(0), Circuit(3).x(0))



def test_qcec_explicit_portfolio_proves_only_full_classical():
    """Optional QCEC can prove a full permutation, not a partial or HMR contract."""
    if qcec_check is None:
        pytest.skip(f"qcec unavailable: {UNAVAILABLE.get('qcec')}")
    from symq.verification import verify_explicit

    reference = Circuit(3)
    equivalent = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    mutant = Circuit(3).ccx(0, 1, 2)

    good = verify_explicit(
        reference, equivalent, theorem="classical_full", engine="qcec",
    )
    bad = verify_explicit(
        reference, mutant, theorem="classical_full", engine="qcec",
    )
    assert good.certified and good.outcome == "equivalent"
    assert bad.outcome == "different" and not bad.certified
    assert bad.witness is None, "QCEC does not return a replayable witness here"
    with pytest.raises(ValueError, match="cannot establish"):
        verify_explicit(
            reference, mutant, theorem="classical_contract", engine="qcec",
        )
