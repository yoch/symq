"""Symbolic domain images are checked against independent integer semantics."""
from itertools import product

import pytest

from symq.backends import make_algebra
from symq.circuit import Circuit
from symq.experimental.domains import (
    AffineDomain,
    FullCube,
    PredicateDomain,
    PreparedDomain,
    domain_from_dict,
)
from symq.resources import Budget
from symq.sat.assumptions import And, Const, Eq, Not, Var, Xor


def symbolic_values(domain, offset=0):
    algebra = make_algebra("zdd", max(1, offset + domain.parameters))
    roots, legal = domain.symbolic(algebra, offset, Budget().start())
    roots = tuple(algebra.to_anf(value) for value in roots)
    legal = algebra.to_anf(legal)
    return [(sum(root.evaluate(value << offset) << wire
                 for wire, root in enumerate(roots)), legal.evaluate(value << offset))
            for value in range(1 << domain.parameters)]


@pytest.mark.parametrize("domain", [
    FullCube(3), AffineDomain(3, 1, (3, 6)), AffineDomain(3, 5, ()),
    PreparedDomain(Circuit(3).cx(0, 1).ccx(0, 1, 2), (0,)),
    PreparedDomain(Circuit(2).x(1), ()),
    PredicateDomain(3, And(Eq(Var("x.0"), Var("x.1")), Not(Var("x.2")))),
])
def test_symbolic_image_matches_integer_semantics_and_domain_membership(domain):
    actual = symbolic_values(domain, offset=2)
    expected = [(domain.decode(value), int(domain.contains(domain.decode(value))))
                for value in range(1 << domain.parameters)]
    assert actual == expected
    image = {value for value, legal in actual if legal}
    assert image == {value for value in range(1 << domain.data) if domain.contains(value)}
    restored = domain_from_dict(domain.to_dict())
    assert restored == domain
    assert restored.sha256 == domain.sha256


def test_all_small_affine_bases_and_offsets_match_exhaustive_membership():
    for columns in product(range(8), repeat=2):
        if not columns[0] or not columns[1] or columns[0] == columns[1]:
            with pytest.raises(ValueError, match="rank"):
                AffineDomain(3, 0, columns)
            continue
        for offset in range(8):
            domain = AffineDomain(3, offset, columns)
            assert symbolic_values(domain) == [(domain.decode(u), 1) for u in range(4)]


def test_preparation_freezes_source_and_returns_detached_copies():
    source = Circuit(3).cx(0, 1).ccx(0, 1, 2)
    domain = PreparedDomain(source, (0,))
    digest = domain.sha256
    source.x(0)
    domain.preparation.x(2)
    assert domain.sha256 == digest
    assert [domain.decode(value) for value in range(2)] == [0, 7]
    with pytest.raises(ValueError):
        PreparedDomain(Circuit(2), (0, 0))


def test_predicate_compilation_checks_every_closed_operator_and_empty_support():
    domain = PredicateDomain(2, Eq(Xor(Var("x.0"), Var("x.1")), Const(True)))
    assert symbolic_values(domain) == [(0, 0), (1, 1), (2, 1), (3, 0)]
    assert symbolic_values(PredicateDomain(1, Const(False))) == [(0, 0), (1, 0)]
    with pytest.raises(ValueError, match="undeclared"):
        PredicateDomain(2, Var("x.2"))
    with pytest.raises(ValueError):
        domain_from_dict({"kind": "predicate", "data": 2,
                          "predicate": {"kind": "callable", "code": "pass"}})


def test_validation_and_symbolic_budget_are_fail_closed():
    for invalid in [True, 0, -1]:
        with pytest.raises(ValueError):
            FullCube(invalid)
    with pytest.raises(ValueError):
        AffineDomain(2, 0, (4,))
    with pytest.raises(ValueError):
        domain_from_dict({"kind": "full_cube", "data": 2, "ignored": True})
    with pytest.raises(ValueError):
        FullCube(2).decode(True)
    with pytest.raises(ValueError):
        AffineDomain(2, 0, ()).decode(1)
    with pytest.raises(ValueError):
        FullCube(3).symbolic(make_algebra("zdd", 2), 0, Budget().start())
    from symq.resources import ResourceLimitExceeded
    guard = Budget(max_seconds=1e-12).start()
    with pytest.raises(ResourceLimitExceeded):
        FullCube(2).symbolic(make_algebra("zdd", 2), 0, guard)
