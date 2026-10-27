import random

import pytest

from symq import (
    BACKENDS,
    Circuit,
    InternalInconsistency,
    ResourceLimitExceeded,
    check_equivalence,
    simulate,
)
from symq.backends import SparseAlgebra, ZDDAlgebra
from symq.generators import MUTATIONS, commute, equivalent_variant, mutate, random_circuit

NAMES = sorted(BACKENDS)


def checked(left, right, name):
    """Run the check; the packed backend may only refuse with a justified degree overflow."""
    try:
        return check_equivalence(left, right, backend=name)
    except ResourceLimitExceeded as error:
        assert name == "packed" and error.resource == "degree" and error.observed > 2
        return None


def seeded_pair(seed):
    rng = random.Random(seed)
    width = rng.randint(2, 7)
    return rng, random_circuit(width, rng.randint(1, 30), rng, max_controls=4)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("seed", range(30))
def test_variants_are_equivalent(name, seed):
    rng, circuit = seeded_pair(seed)
    variant = equivalent_variant(circuit, rng, steps=25)
    assert circuit.equivalent(variant)
    result = checked(circuit, variant, name)
    assert result is None or (result.equivalent and result.witness is None)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("seed", range(60))
def test_mutants_agree_with_exhaustive_oracle(name, seed):
    rng, circuit = seeded_pair(seed)
    mutant, _ = mutate(circuit, rng)
    expected = circuit.equivalent(mutant)
    result = checked(circuit, mutant, name)
    if result is None:
        return
    assert result.equivalent == expected
    if not expected:
        assert circuit.run(result.witness) >> result.output & 1 != (
            mutant.run(result.witness) >> result.output & 1
        )


def test_every_mutation_kind_is_exercised():
    seen = set()
    for seed in range(200):
        rng, circuit = seeded_pair(seed)
        seen.add(mutate(circuit, rng)[1])
    assert seen == set(MUTATIONS)


def test_commute_is_sound():
    rng = random.Random(0)
    for _ in range(300):
        a, b = random_circuit(4, 2, rng).gates
        if commute(a, b):
            assert Circuit(4, [a, b]).equivalent(Circuit(4, [b, a]))


def test_width_mismatch_rejected():
    with pytest.raises(ValueError):
        check_equivalence(Circuit(2), Circuit(3))


def test_witness_for_large_width_without_enumeration():
    width = 40
    left = Circuit(width).mcx(*range(30), 39)
    right = Circuit(width).mcx(*range(31), 39)
    result = check_equivalence(left, right, backend="zdd")
    assert not result.equivalent
    assert result.output == 39
    assert left.run(result.witness) != right.run(result.witness)


# Mutation tests of the backends themselves: deliberately broken algebras must be caught
# by the same differential checks used above.

class NoCancellationSparse(SparseAlgebra):
    name = "sparse"

    def _multiply(self, left, right):
        return {t | u for t in left for u in right}


class MissingCrossTermZDD(ZDDAlgebra):
    name = "zdd"

    def multiply(self, left, right):
        if left <= 1 or right <= 1 or left == right:
            return super().multiply(left, right)
        var, lo, hi = self._var, self._lo, self._hi
        v = min(var[left], var[right])
        l0, l1 = (lo[left], hi[left]) if var[left] == v else (left, 0)
        r0, r1 = (lo[right], hi[right]) if var[right] == v else (right, 0)
        return self._mk(v, self.multiply(l0, r0), self.multiply(l1, r1))


class ForgetfulXorSparse(SparseAlgebra):
    name = "sparse"

    def ixor(self, left, right):
        left |= right
        return left


@pytest.mark.parametrize("mutant", [NoCancellationSparse, MissingCrossTermZDD, ForgetfulXorSparse])
def test_differential_checks_kill_backend_mutants(mutant):
    killed = 0
    for seed in range(40):
        _, circuit = seeded_pair(seed)
        algebra = mutant(circuit.width)
        outputs = [algebra.to_anf(v) for v in simulate(circuit, algebra)]
        killed += outputs != list(circuit.symbolic())
    assert killed > 0


def test_witness_self_check_detects_lying_backend(monkeypatch):
    left = Circuit(2).x(0)
    right = Circuit(2).x(0)
    monkeypatch.setattr(SparseAlgebra, "equal", lambda self, a, b: False)
    monkeypatch.setattr(SparseAlgebra, "min_monomial", lambda self, v: 0)
    with pytest.raises(InternalInconsistency):
        check_equivalence(left, right, backend="sparse")
