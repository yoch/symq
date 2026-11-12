"""Version-2 and shared table contracts up to 16 address bits (lot 4 of the 0.2.0 report).

Two constructions changed, each checked against a simple reference that stays in the code:

- the indicator of the admitted addresses is built by Shannon decomposition
  (``anchored_stream._allowed``) instead of one selector per admitted word
  (``_allowed_minterms``, still selectable as ``domain_style="minterms"``);
- the admitted words of a shared contract's predicate are computed on all words at once
  (``shared_table._admitted``) instead of one ``PredicateDomain.contains`` call per word.

Then the verdicts: the same as with the reference construction on random small cases, the
same as an independent density-matrix oracle on the smallest loaders, and the expected
status on a synthetic loader family at 12, 13, 14 and 16 bits, with development and
holdout seeds kept disjoint.
"""
from __future__ import annotations

import random

import pytest

from benchmarks.affine_table import physical_inputs
from symq.experimental.serialization import program_from_dict
from symq.experimental.table_xor import PredicateValues
from symq.labs.affine_table import verify_affine_table
from symq.labs.anchored_stream import Algebra, _allowed, _allowed_minterms, _contains
from symq.labs.shared_table import _admitted, _normalize, verify_shared_table
from symq.resources import Budget, Guard
from symq.sat.assumptions import And, Const, Eq, Not, Var, Xor
from tests.testkit import table_channel_oracle as oracle
from tests.testkit.affine_loader_cases import gen
from tests.testkit.wide_loader_cases import MUTANTS, case

BACKENDS = ["anf", pytest.param("sat", marks=pytest.mark.sat)]
DEV_SEEDS = (0, 1)
HOLDOUT_SEEDS = (1000, 1001)
"""Development seeds were used while writing the verifier change and the benchmark
(``benchmarks/table_domain.py``); the holdout seeds were not run before this test."""


def _guard():
    return Guard(Budget(max_seconds=60, max_terms=10**7))


def _algebra(backend):
    guard = _guard()
    if backend == "anf":
        return Algebra(guard, 10**8), guard
    from symq.labs.kraus_graph import Graph

    return Graph(guard, 10**6, 10**7), guard


def _same_function(w, left, right) -> bool:
    if isinstance(left, frozenset):
        return left == right  # ANF is canonical: equal functions have equal polynomials
    return w.witness(w.xor(left, right)) is None


# --- the indicator --------------------------------------------------------------------------

@pytest.mark.parametrize("backend", BACKENDS)
def test_the_shannon_indicator_is_the_minterm_indicator(backend):
    rng = random.Random("indicator")
    for _ in range(150):
        bits = rng.randrange(1, 9)
        density = rng.choice((0.0, 0.1, 0.5, 0.9, 1.0))
        values = sorted(v for v in range(1 << bits) if rng.random() < density)
        w, guard = _algebra(backend)
        wires = rng.sample(range(bits + 2), bits)  # words over any wires, in any order
        state = [w.var(q) for q in range(bits + 2)]
        fast = _allowed(wires, values, state, w, guard)
        slow = _allowed_minterms(wires, values, state, w)
        assert _same_function(w, fast, slow), (bits, values, wires)


def test_the_indicator_holds_exactly_on_its_words():
    """Evaluated, not only compared with the reference: a shared mistake cannot hide."""
    rng = random.Random("evaluate")
    for _ in range(60):
        bits = rng.randrange(1, 7)
        values = sorted(v for v in range(1 << bits) if rng.random() < 0.4)
        w, guard = _algebra("anf")
        state = [w.var(q) for q in range(bits)]
        indicator = _allowed(list(range(bits)), values, state, w, guard)
        for word in range(1 << bits):
            value = sum(all(word >> q & 1 for q in range(bits) if mask >> q & 1)
                        for mask in indicator) & 1
            assert value == (word in values)


def test_a_wide_interval_stays_small():
    w, guard = _algebra("anf")
    state = [w.var(q) for q in range(16)]
    upper = 40_000
    indicator = _allowed(list(range(16)), list(range(upper)), state, w, guard)
    assert len(indicator) < 1000 and w.products < 10_000


def test_membership_is_exact():
    values = [1, 4, 9, 16, 25]
    assert [_contains(values, x) for x in range(27)] == [x in values for x in range(27)]
    assert not _contains([], 0)


# --- the admitted words of a predicate ------------------------------------------------------

def _expression(rng, bits, depth):
    if depth == 0 or rng.random() < 0.25:
        if rng.random() < 0.15:
            return Const(rng.random() < 0.5)
        return Var(f"x.{rng.randrange(bits)}")
    kind = rng.choice((Not, And, Xor, Eq))
    if kind is Not:
        return Not(_expression(rng, bits, depth - 1))
    return kind(_expression(rng, bits, depth - 1), _expression(rng, bits, depth - 1))


def test_admitted_words_are_those_contains_admits():
    from symq.experimental.domains import PredicateDomain

    rng = random.Random("admitted")
    for _ in range(300):
        bits = rng.randrange(1, 11)
        domain = PredicateDomain(bits, _expression(rng, bits, rng.randrange(1, 6)))
        assert _admitted(domain, _guard()) == [w for w in range(1 << bits) if domain.contains(w)]
    for bits in (1, 5, 12):
        for upper in sorted({1, min(3, 1 << bits), max(1, (1 << bits) - 1), 1 << bits}):
            domain = PredicateValues.below(bits, upper).domain
            assert _admitted(domain, _guard()) == list(range(upper))


def test_a_shared_identity_at_16_bits_admits_every_word_of_its_interval():
    loader = case(16, 0)
    _document, normalized, *_ = _normalize(loader.contract(), _guard())
    assert normalized["legal_addresses"] == list(range(loader.upper))


# --- verdicts: the reference construction ---------------------------------------------------

@pytest.mark.parametrize("backend", BACKENDS)
def test_both_domain_constructions_reach_the_same_verdict(backend):
    rng = random.Random(f"verdicts/{backend}")
    for _ in range(80):
        source, contract, *_ = gen(rng)
        results = [verify_affine_table(source, contract, backend=backend, domain_style=style)
                   for style in ("shannon", "minterms")]
        # ANF is canonical, so even the witness is the same; SAT may pick another valid one.
        keys = ("status", "obligation", "witness") if backend == "anf" else ("status", "obligation")
        shannon, minterms = ({k: r[k] for k in keys} for r in results)
        assert shannon == minterms
    for width in (4, 6, 8):
        for mutant in (None, *MUTANTS):
            loader = case(width, 7, mutant)
            _document, normalized, *_ = _normalize(loader.contract(), _guard())
            statuses = {verify_affine_table(loader.source(), normalized, backend=backend,
                                            domain_style=style)["status"]
                        for style in ("shannon", "minterms")}
            assert statuses == {loader.expected}, (width, mutant)


def test_an_unknown_domain_style_is_refused():
    loader = case(4, 0)
    _document, normalized, *_ = _normalize(loader.contract(), _guard())
    with pytest.raises(ValueError, match="domain_style"):
        verify_affine_table(loader.source(), normalized, domain_style="list")


# --- verdicts: an independent oracle --------------------------------------------------------

@pytest.mark.parametrize("mutant", [None, *MUTANTS])
def test_the_smallest_loaders_agree_with_the_density_oracle(mutant):
    loader = case(4, 3, mutant, target_bits=2, terms_per_target=2)
    _document, spec, *_ = _normalize(loader.contract(), _guard())
    verdict = verify_shared_table(loader.source(), loader.contract())["status"]
    program = program_from_dict(loader.source())
    address = tuple(spec["address_wires"])
    target = tuple(spec["target_wires"])
    states = [x for x in physical_inputs(spec)]
    table = tuple(spec["table"])
    differs = oracle.first_difference(program, states, address, target, table) is not None
    assert verdict == ("not_proved" if differs else "equivalent")
    assert verdict == loader.expected


# --- qualification at 12 to 16 bits ---------------------------------------------------------

def test_development_and_holdout_seeds_are_disjoint():
    assert not set(DEV_SEEDS) & set(HOLDOUT_SEEDS)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("width", [12, 13, 14, 16])
@pytest.mark.parametrize("seed", DEV_SEEDS + HOLDOUT_SEEDS)
def test_the_wide_family_gets_its_expected_verdicts(backend, width, seed):
    if seed in HOLDOUT_SEEDS and width in (12, 14):
        pytest.skip("the holdout seeds are run at 13 and 16 bits")
    for mutant in (None, *MUTANTS):
        loader = case(width, seed, mutant)
        result = verify_shared_table(loader.source(), loader.contract(), backend=backend)
        assert result["status"] == loader.expected, (width, seed, mutant, result)
        if mutant is not None:
            assert result["witness"] is not None  # replayed on the source by the verifier


@pytest.mark.parametrize("backend", BACKENDS)
def test_the_reference_construction_stops_where_the_new_one_concludes(backend):
    """At 12 bits the minterm indicator exhausts the default product budget on ANF."""
    loader = case(12, 0)
    _document, normalized, *_ = _normalize(loader.contract(), _guard())
    new = verify_affine_table(loader.source(), normalized, backend=backend)
    assert new["status"] == "equivalent"
    if backend == "anf":
        old = verify_affine_table(loader.source(), normalized, domain_style="minterms")
        assert old["status"] == "inconclusive" and old["resource"] == "products"
        assert new["products"] < 10_000 < old["products"]


def test_a_16_bit_contract_fits_the_shared_transport_limit():
    from symq.labs.shared_table import _MAX_JSON_BYTES, _canonical

    assert len(_canonical(case(16, 0).contract())) < _MAX_JSON_BYTES


@pytest.mark.parametrize("width", [4, 16])
def test_a_case_is_reproducible_from_its_seed(width):
    assert case(width, 5) == case(width, 5)
    assert case(width, 5).source() == case(width, 5).source()
    assert [case(width, 5, m).expected for m in (None, *MUTANTS)] == (
        ["equivalent"] + ["not_proved"] * len(MUTANTS))
    with pytest.raises(ValueError):
        case(17, 0)


def test_physical_inputs_of_a_small_case_are_admitted_words_only():
    loader = case(4, 2)
    _document, spec, *_ = _normalize(loader.contract(), _guard())
    addresses = {sum((x >> q & 1) << j for j, q in enumerate(spec["address_wires"]))
                 for x in physical_inputs(spec)}
    assert addresses == set(range(loader.upper))
