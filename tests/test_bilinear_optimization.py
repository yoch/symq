"""Exact, source-pinned bilinear synthesis tests on independent oracles.

The original Kaggle inputs by James Barlow are public open-set fixtures;
these results are not a blind agent benchmark or a Kaggle score claim.
"""
from __future__ import annotations

import random

import pytest

from benchmarks.kaggle_bilinear_eval import independent_product, manifest, source_starts
from benchmarks.kaggle_bilinear_kmb import encode, parse, pivot_fanout, simulate
from benchmarks.kaggle_bilinear_towers import build_terms
from symq import Budget, check_equivalence
from symq.circuit import Circuit
from symq.generators import gf2n
from symq.generators.bilinear_optimization import (
    MAX_SCHEDULE_TERMS,
    _irreducible,
    certify_decomposition,
)


def _ops(circuit: Circuit) -> list[tuple[int, int, int, int]]:
    out = []
    for gate in circuit.gates:
        if gate.name == "cx":
            out.append((33, gate.qubits[0], gate.qubits[1], -1))
        elif gate.name == "ccx":
            out.append((49, *gate.qubits))
        else:
            raise AssertionError(f"invalid bilinear gate: {gate.name}")
    return out


@pytest.mark.parametrize(
    "n,modulus,rank,expected_cx",
    [(4, 0x13, 9, 30), (6, 0x49, 15, 82)],
)
def test_public_kaggle_tensors_kmb_and_original_checker_equations(n, modulus, rank, expected_cx):
    from symq.generators.gf2n import Term

    triples, _ = build_terms(n, modulus)
    factors = [Term(*triple) for triple in triples]
    certify_decomposition(n, factors, modulus)
    old = pivot_fanout(n, triples)
    plain = gf2n.emit(n, factors, strategy="pivot")
    optimized = gf2n.emit(n, factors, strategy="pivot-scheduled")
    ops = _ops(optimized.circuit)
    assert optimized.ccx == len(factors) == rank
    assert optimized.width == 3 * n
    assert optimized.cx == expected_cx
    assert optimized.cx <= plain.cx < len(old) - rank
    assert optimized.fold_cx <= optimized.cx
    assert len([gate for gate in optimized.circuit.gates if gate.name == "ccx"]) == rank
    encoded = encode(ops, n)
    assert parse(encoded) == (3 * n, ops)

    # A byte-derived KMB simulator and independent integer polynomial oracle.
    for a in range(1 << n):
        for b in range(1 << n):
            product = independent_product(a, b, n, modulus)
            for target in (0, (1 << n) - 1, 1, ((a << 1) ^ b) & ((1 << n) - 1)):
                x = a | (b << n) | (target << (2 * n))
                goal = a | (b << n) | ((target ^ product) << (2 * n))
                assert simulate(ops, x) == goal
                assert optimized.circuit.run(x) == goal


def test_all_14_original_kmb_workloads_with_new_shared_frame_circuit():
    from symq.generators.gf2n import Term

    rows = manifest()
    originals = source_starts()
    assert len(rows) == 14
    models = {}
    for n, modulus in ((4, 0x13), (6, 0x49)):
        factors = [Term(*row) for row in build_terms(n, modulus)[0]]
        compiled = gf2n.emit(n, factors, strategy="pivot-scheduled")
        raw = encode(_ops(compiled.circuit), n)
        models[(n, modulus)] = (compiled, raw)
    sum_original_ccx = sum_original_cx = sum_ccx = sum_cx = 0
    for row in rows:
        n, modulus = row["width"], row["modulus"]
        source = originals[row["kmb"]]
        source_width, src_ops = parse(source)
        candidate, raw = models[(n, modulus)]
        new_width, dst_ops = parse(raw)
        assert source_width == new_width == row["qubits"] == 3 * n
        assert sum(op[0] == 49 for op in src_ops) == row["start_ccx"]
        assert sum(op[0] == 49 for op in dst_ops) == row["proven_bilinear_target"]
        for a in range(1 << n):
            for b in range(1 << n):
                product = independent_product(a, b, n, modulus)
                for z in (0, (1 << n) - 1):
                    x = a | (b << n) | (z << (2 * n))
                    expected = a | (b << n) | ((z ^ product) << (2 * n))
                    assert simulate(src_ops, x) == expected
                    assert simulate(dst_ops, x) == expected
        sum_original_ccx += sum(op[0] == 49 for op in src_ops)
        sum_original_cx += sum(op[0] == 33 for op in src_ops)
        sum_ccx += candidate.ccx
        sum_cx += candidate.cx
    assert (sum_original_ccx, sum_ccx) == (240, 168)
    assert (sum_original_cx, sum_cx) == (1862, 784)


@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("method", sorted(gf2n.DECOMPOSITIONS))
def test_pivot_synthesis_of_existing_multipliers(n, method):
    reference = gf2n.multiplier(n, method)
    plain = gf2n.multiplier(n, method, strategy="pivot")
    scheduled = gf2n.multiplier(n, method, strategy="pivot-scheduled")
    for x in range(1 << (3 * n)):
        expected = gf2n.multiplier_expected_output(n, x)
        assert reference.run(x) == plain.run(x) == scheduled.run(x) == expected
    assert len([g for g in scheduled.gates if g.name == "ccx"]) <= len([
        g for g in reference.gates if g.name == "ccx"
    ])
    assert scheduled.counts().get("cx", 0) <= plain.counts().get("cx", 0)


@pytest.mark.parametrize("n", [5, 6, 8, 12, 16, 24])
def test_pivot_schedule_larger_circuits_randomized(n):
    rng = random.Random(0xB111 + n)
    for method in ("schoolbook", "karatsuba", "rank_floor"):
        circuit = gf2n.multiplier(n, method, strategy="pivot-scheduled")
        for _ in range(12 if n >= 12 else 50):
            x = rng.randrange(1 << (3 * n))
            assert circuit.run(x) == gf2n.multiplier_expected_output(n, x), (n, method, x)


def test_certification_rejects_mutants_wrong_polynomial_and_invalid_masks():
    from symq.generators.gf2n import Term

    terms = [Term(*v) for v in build_terms(6, 0x49)[0]]
    certify_decomposition(6, terms, 0x49)
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(6, terms, 0x43)
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(6, terms[:-1], 0x49)
    altered = list(terms)
    altered[0] = Term(terms[0].left, terms[0].right, terms[0].into ^ 1)
    with pytest.raises(ValueError, match="tensor mismatch"):
        certify_decomposition(6, altered, 0x49)
    assert _irreducible(0x49) and _irreducible(0x43)
    assert not _irreducible(0x15)
    with pytest.raises(ValueError, match="irreducible"):
        certify_decomposition(6, terms, 0x45)
    with pytest.raises(ValueError, match="invalid bilinear factor"):
        gf2n.emit(6, [Term(0, 1, 1)], strategy="pivot")
    with pytest.raises(ValueError, match="invalid bilinear factor"):
        gf2n.emit(6, [Term(True, 1, 1)], strategy="pivot")
    with pytest.raises(ValueError, match="invalid bilinear factor"):
        gf2n.emit(6, [Term(1, 64, 1)], strategy="pivot")
    with pytest.raises(ValueError, match="strategy"):
        gf2n.emit(6, terms, strategy="unsupported")
    with pytest.raises(ValueError, match="share"):
        gf2n.emit(6, terms, share=True, strategy="pivot")
    with pytest.raises(ValueError, match="at most"):
        gf2n.emit(6, [terms[0]] * (MAX_SCHEDULE_TERMS + 1), strategy="pivot-scheduled")


def test_in_context_full_permutation_and_negative_mutant():
    """Whole-circuit context; does not claim a local relational SAT cut theorem."""
    from symq.generators.gf2n import Term

    n, modulus = 4, 0x13
    rank_terms = [Term(*v) for v in build_terms(n, modulus)[0]]
    baseline_terms = [
        Term(1 << i, 1 << j, independent_product(1 << i, 1 << j, n, modulus))
        for i in range(n) for j in range(n)
    ]
    baseline = gf2n.emit(n, baseline_terms, strategy="incidence").circuit
    optimized = gf2n.emit(n, rank_terms, strategy="pivot-scheduled").circuit
    prefix = Circuit(3 * n).cx(0, 8).cx(9, 1).cx(2, 10)
    suffix = Circuit(3 * n).ccx(4, 1, 11).cx(11, 0)
    left = Circuit(3 * n, [*prefix.gates, *baseline.gates, *suffix.gates])
    right = Circuit(3 * n, [*prefix.gates, *optimized.gates, *suffix.gates])
    result = check_equivalence(left, right, backend="zdd", budget=Budget(max_seconds=20))
    assert result.equivalent
    mutant = Circuit(right.width, list(right.gates))
    mutant.gates.pop()
    bad = check_equivalence(left, mutant, backend="zdd", budget=Budget(max_seconds=20))
    assert not bad.equivalent
    assert left.run(bad.witness) != mutant.run(bad.witness)
