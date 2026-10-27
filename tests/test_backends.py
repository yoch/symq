import random
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from symq import ANF, BACKENDS, Budget, Circuit, ResourceLimitExceeded, make_algebra, simulate
from symq.backends import AutoZDDAlgebra, PackedAlgebra, WireAdaptiveAlgebra, ZDDAlgebra
from symq.corpus import load_corpus
from symq.generators import random_circuit

CORPUS = Path(__file__).resolve().parents[1] / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json"
NAMES = sorted(BACKENDS)
SEEDS = range(40)


def concrete_outputs(circuit):
    """Per-wire truth tables from concrete execution only (independent of any algebra)."""
    tables = [0] * circuit.width
    for x in range(1 << circuit.width):
        y = circuit.run(x)
        for wire in range(circuit.width):
            if y >> wire & 1:
                tables[wire] |= 1 << x
    return tables


def anf_table(anf, width):
    return sum(anf.evaluate(x) << x for x in range(1 << width))


def degree_refusal(error):
    return error.resource == "degree" and error.observed > error.limit


def seeded_circuit(seed):
    rng = random.Random(seed)
    width = rng.randint(1, 7)
    return random_circuit(width, rng.randint(0, 40), rng, max_controls=4)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("seed", SEEDS)
def test_outputs_match_concrete_execution(name, seed):
    circuit = seeded_circuit(seed)
    algebra = make_algebra(name, circuit.width)
    try:
        outputs = [algebra.to_anf(v) for v in simulate(circuit, algebra)]
    except ResourceLimitExceeded as error:
        assert name == "packed" and degree_refusal(error)
        return
    assert outputs == list(circuit.symbolic())
    assert [anf_table(o, circuit.width) for o in outputs] == concrete_outputs(circuit)


anf_terms = st.sets(st.integers(min_value=0, max_value=63), max_size=24)


@pytest.mark.parametrize("name", NAMES)
@settings(max_examples=60, deadline=None)
@given(left=anf_terms, right=anf_terms, third=anf_terms)
def test_ring_operations_match_reference(name, left, right, third):
    if name == "packed":
        left, right, third = ({m for m in t if m.bit_count() <= 2} for t in (left, right, third))
    a, b, c = (ANF(frozenset(t)) for t in (left, right, third))
    algebra = make_algebra(name, 6)
    x, y, z = (algebra.from_anf(v) for v in (a, b, c))
    assert algebra.to_anf(x) == a
    assert algebra.to_anf(algebra.xor(x, y)) == a ^ b
    if name == "packed" and (a * b * c).degree > 2:
        with pytest.raises(ResourceLimitExceeded) as info:
            algebra.product([x, y, z])
        assert degree_refusal(info.value)
    else:
        assert algebra.to_anf(algebra.product([x, y, z])) == a * b * c
    assert algebra.to_anf(algebra.product([])) == ANF.constant(1)
    assert algebra.equal(algebra.from_anf(a ^ b), algebra.xor(x, y))
    assert algebra.is_zero(algebra.xor(x, x))
    witness = algebra.min_monomial(x)
    assert (witness is None) == (not left)
    if witness is not None:
        assert a.evaluate(witness) == 1


@pytest.mark.parametrize("name", NAMES)
def test_xor_does_not_mutate_inputs(name):
    algebra = make_algebra(name, 3)
    x = algebra.from_anf(ANF.from_terms([1, 2]))
    y = algebra.from_anf(ANF.from_terms([2, 4]))
    algebra.xor(x, y)
    algebra.product([x, y])
    assert algebra.to_anf(x) == ANF.from_terms([1, 2])
    assert algebra.to_anf(y) == ANF.from_terms([2, 4])


@pytest.mark.parametrize("name", NAMES)
def test_out_of_width_anf_rejected(name):
    with pytest.raises(ValueError):
        make_algebra(name, 2).from_anf(ANF.variable(5))


def test_unknown_backend_rejected():
    with pytest.raises(ValueError, match="unknown backend"):
        make_algebra("cudd", 2)


def blowup_circuit(k=5):
    """The last wire accumulates prod_i (x_i + x_{i+k}): 2**k monomials, no cancellation."""
    c = Circuit(2 * k + 1)
    for i in range(k):
        c.cx(i + k, i)
    return c.mcx(*range(k), 2 * k)


@pytest.mark.parametrize("name", ["reference", "sparse", "sparse-copy", "packed-fallback"])
def test_term_budget_raises(name):
    circuit = blowup_circuit()
    unbounded = make_algebra(name, circuit.width)
    assert unbounded.terms(simulate(circuit, unbounded)[-1]) > 16
    with pytest.raises(ResourceLimitExceeded) as info:
        simulate(circuit, make_algebra(name, circuit.width, Budget(max_terms=16)))
    assert info.value.resource == "terms"


@pytest.mark.parametrize(
    ("name", "options"),
    [
        ("zdd", {}),
        ("adaptive-wire", {"product_threshold": 1, "promote_threshold": 1}),
        ("auto-zdd", {"switch_terms": 1}),
    ],
)
def test_node_budget_raises(name, options):
    circuit = random_circuit(10, 60, random.Random(3), max_controls=4)
    with pytest.raises(ResourceLimitExceeded) as info:
        simulate(circuit, make_algebra(name, 10, Budget(max_nodes=8), **options))
    assert info.value.resource == "nodes"


@pytest.mark.parametrize("name", NAMES)
def test_time_budget_raises(name):
    circuit = random_circuit(8, 2000, random.Random(5))
    algebra = make_algebra(name, 8, Budget(max_seconds=1e-9))
    with pytest.raises(ResourceLimitExceeded) as info:
        simulate(circuit, algebra)
    assert info.value.resource == "seconds"


def test_truthtable_width_refused():
    with pytest.raises(ResourceLimitExceeded):
        make_algebra("truthtable", 19)
    assert make_algebra("truthtable", 6, max_width=6).width == 6


def test_zdd_to_anf_respects_term_budget():
    circuit = blowup_circuit()
    algebra = make_algebra("zdd", circuit.width, Budget(max_terms=16))
    last = simulate(circuit, algebra)[-1]
    with pytest.raises(ResourceLimitExceeded):
        algebra.to_anf(last)


def test_budget_validation():
    with pytest.raises(ValueError):
        Budget(max_terms=0)
    with pytest.raises(ValueError):
        Budget(max_seconds=0)


def test_packed_refuses_cubic_and_fallback_recovers():
    circuit = Circuit(4).ccx(0, 1, 3).mcx(0, 1, 2, 3).ccx(0, 1, 3)
    with pytest.raises(ResourceLimitExceeded) as info:
        simulate(circuit, make_algebra("packed", 4))
    assert degree_refusal(info.value)
    fallback = make_algebra("packed-fallback", 4)
    outputs = simulate(circuit, fallback)
    assert [fallback.to_anf(v) for v in outputs] == list(circuit.symbolic())
    assert fallback.stats.conversions > 0
    assert PackedAlgebra(4).min_monomial(PackedAlgebra(4).variable(2)) == 0b100


def test_packed_succeeds_on_some_seeds():
    successes = 0
    for seed in SEEDS:
        circuit = seeded_circuit(seed)
        try:
            simulate(circuit, make_algebra("packed", circuit.width))
        except ResourceLimitExceeded:
            continue
        successes += 1
    assert 0 < successes < len(SEEDS)


@pytest.mark.parametrize("order", ["reversed", "shuffled"])
@pytest.mark.parametrize("seed", range(15))
def test_zdd_order_changes_size_not_result(order, seed):
    circuit = seeded_circuit(seed)
    permutation = list(range(circuit.width))[::-1]
    if order == "shuffled":
        random.Random(seed).shuffle(permutation)
    algebra = ZDDAlgebra(circuit.width, order=permutation)
    assert [algebra.to_anf(v) for v in simulate(circuit, algebra)] == list(circuit.symbolic())
    for value in simulate(circuit, algebra):
        witness = algebra.min_monomial(value)
        if witness is not None:
            assert algebra.to_anf(value).evaluate(witness) == 1


def test_zdd_product_keeps_intermediates_small():
    entry = next(e for e in load_corpus(CORPUS).entries if e.name == "rd84_313")
    circuit = entry.load()
    algebra = ZDDAlgebra(circuit.width, order=list(range(circuit.width))[::-1])
    simulate(circuit, algebra)
    assert algebra.node_count < 5_000


def test_zdd_order_must_be_permutation():
    with pytest.raises(ValueError):
        ZDDAlgebra(3, order=[0, 0, 1])


def test_auto_zdd_switch_is_whole_state_and_irreversible():
    circuit = blowup_circuit()
    algebra = AutoZDDAlgebra(circuit.width, switch_terms=8)
    outputs = simulate(circuit, algebra)
    assert all(isinstance(v, int) for v in outputs)
    assert algebra.switch_gate == len(circuit.gates) - 1
    assert algebra.stats.conversions == circuit.width
    assert [algebra.to_anf(v) for v in outputs] == list(circuit.symbolic())
    never = AutoZDDAlgebra(circuit.width)
    assert all(isinstance(v, set) for v in simulate(circuit, never))
    assert never.switch_gate is None


def test_zdd_is_canonical_and_shares_nodes():
    algebra = ZDDAlgebra(4)
    a = algebra.from_anf(ANF.from_terms([0b0011, 0b0100, 0]))
    b = algebra.xor(algebra.xor(algebra.from_anf(ANF.from_terms([0b0011])), algebra.one()),
                    algebra.variable(2))
    assert a == b
    assert algebra.size(a) <= algebra.node_count
    assert algebra.terms(a) == 3


@pytest.mark.parametrize("seed", SEEDS)
def test_adaptive_conversions_are_exact_and_accounted(seed):
    circuit = seeded_circuit(seed)
    eager = WireAdaptiveAlgebra(circuit.width, product_threshold=1, promote_threshold=1)
    lazy = WireAdaptiveAlgebra(circuit.width, product_threshold=10**9, promote_threshold=10**9)
    expected = list(circuit.symbolic())
    for algebra in (eager, lazy):
        assert [algebra.to_anf(v) for v in simulate(circuit, algebra)] == expected
    assert lazy.stats.conversions == 0
    if any(len(g.qubits) > 1 for g in circuit.gates):
        assert eager.stats.conversions > 0
        assert eager.stats.conversion_terms > 0
