"""Bounded-cache growth must be lazy, and results must not depend on it.

The ``cache_limit`` mode used to allocate and clear its whole table in the constructor, so the
small structured circuits of the QCEC corpus paid 0.5-17 ms for a cache they never filled -- up
to 40x their entire runtime. The table is now created on first use and doubled (without rehashing,
since a dropped entry only costs recomputation) up to the configured ceiling.

What these tests pin:

* the table is not allocated until the first operation, so a manager with only variables pays
  nothing;
* the capacity never exceeds the limit, and the limit is a real bound;
* results are identical with and without a limit, on every backend operation;
* a tiny limit still produces the same nodes and outputs (the cache only affects work).
"""
from __future__ import annotations

import random

import pytest

from symq import simulate
from symq.anf import ANF
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.generators import random_circuit
from symq.resources import Budget


def test_the_cache_is_not_allocated_before_the_first_operation():
    algebra = NativeZDDAlgebra(4, cache_limit=1 << 20)
    info = algebra.cache_info()
    assert info["lossy"] is True
    assert info["capacity"] == 0, "nothing is allocated by the constructor"
    algebra.variable(0)
    assert algebra.cache_info()["capacity"] == 0, "creating a variable needs no cache"
    algebra.product([algebra.variable(0), algebra.variable(1)])
    assert algebra.cache_info()["capacity"] > 0


def test_the_capacity_never_exceeds_the_limit():
    algebra = NativeZDDAlgebra(8, cache_limit=4096)
    a = algebra.variable(0)
    value = a
    rng = random.Random(1)
    for _ in range(400):
        value = algebra.xor(value, algebra.product([algebra.variable(rng.randrange(8)),
                                                    algebra.variable(rng.randrange(8))]))
    info = algebra.cache_info()
    assert info["capacity"] <= 4096
    assert info["capacity"] >= 1


@pytest.mark.parametrize("limit", [None, 1, 2, 64, 4096])
def test_a_limit_never_changes_the_result(limit):
    rng = random.Random(7)
    circuit = random_circuit(6, 40, rng)
    plain = NativeZDDAlgebra(6, Budget(max_nodes=4_000_000).start())
    limited = NativeZDDAlgebra(6, Budget(max_nodes=4_000_000).start(), cache_limit=limit)
    reference = tuple(plain.to_anf(value) for value in simulate(circuit, plain))
    observed = tuple(limited.to_anf(value) for value in simulate(circuit, limited))
    assert observed == reference
    assert limited.node_count == plain.node_count


def test_a_tiny_table_still_misses_and_recomputes_correctly():
    algebra = NativeZDDAlgebra(5, cache_limit=1)
    a, b = algebra.variable(0), algebra.variable(1)
    product = algebra.product([a, b])
    for _ in range(20):
        assert algebra.equal(algebra.product([a, b]), product)
    assert algebra.to_anf(product) == ANF(frozenset({0b11})), "x0 * x1 is the single monomial x0x1"


def test_the_lossless_default_is_unchanged():
    algebra = NativeZDDAlgebra(4)
    info = algebra.cache_info()
    assert info["lossy"] is False
    assert info["capacity"] > 0, "the lossless cache is allocated up front, as before"
