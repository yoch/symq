import itertools
import math
import random

import pytest

from symq.labs.bilinear_phase_fusion.checker import (
    Inconclusive,
    Rejected,
    check_certificate,
    check_outcome,
    load_strict,
    multiplication_oracle,
)
from symq.labs.bilinear_phase_fusion.compiler import branch, compile_bank, digest
from symq.labs.bilinear_phase_fusion.preparation import emit_source, prove_preparation


@pytest.mark.parametrize(
    "m,poly,bank", [(2, 7, 1), (2, 7, 2), (3, 11, 1), (3, 11, 2), (3, 11, 3), (4, 19, 2)]
)
def test_all_small_outcomes(m, poly, bank):
    p = compile_bank(m, poly, bank)
    for ss in itertools.product(range(1 << m), repeat=bank):
        r = check_outcome(p, list(ss))
        assert r["ccz"] == (m if any(ss) else 0)


def scalar_replay(state, gates):
    sign = 1
    for g in gates:
        if g[0] == "cx":
            if (state >> g[1]) & 1:
                state ^= 1 << g[2]
        elif g[0] == "ccz":
            if all((state >> q) & 1 for q in g[1:]):
                sign = -sign
        else:
            raise AssertionError(g)
    return state, sign


def exact_branch_column(p, ss, x, dirty=False, stale=False):
    m = p["field"]["m"]
    poly = p["field"]["modulus"]
    c = x & 1
    a = (x >> 1) & ((1 << m) - 1)
    residual = 0
    for j, s in enumerate(ss):
        b = (x >> (1 + m + j * m)) & ((1 << m) - 1)
        garbage = c * multiplication_oracle(a, b, m, poly)
        if dirty and j == 0:
            garbage ^= a & 1
        residual ^= (s & garbage).bit_count() & 1
    state = x ^ (2 if stale else 0)
    y, sgn = scalar_replay(state, branch(p, ss))
    return y, sgn * (-1 if residual else 1)


@pytest.mark.parametrize("m,poly,bank", [(2, 7, 2), (3, 11, 2)])
def test_exact_kraus_columns(m, poly, bank):
    p = compile_bank(m, poly, bank)
    # These scalar signs are exact integers. All columns of every Kraus map.
    for ss in itertools.product(range(1 << m), repeat=bank):
        gates = branch(p, list(ss))
        for x in range(1 << p["width"]):
            c = x & 1
            a = (x >> 1) & ((1 << m) - 1)
            residual = 0
            for j, s in enumerate(ss):
                b = (x >> (1 + m + j * m)) & ((1 << m) - 1)
                garbage = c * multiplication_oracle(a, b, m, poly)
                residual ^= (s & garbage).bit_count() & 1
            y, sign = scalar_replay(x, gates)
            assert y == x and sign == (-1 if residual else 1)


def test_coherent_external_reference_and_use():
    p = compile_bank(2, 7, 2)
    d = 1 << p["width"]
    rng = random.Random(20261112)
    v = [complex(rng.gauss(0, 1), rng.gauss(0, 1)) for _ in range(2 * d)]
    norm = math.sqrt(sum(abs(x) ** 2 for x in v))
    v = [x / norm for x in v]
    target = []
    # A consumer uses a garbage bit as CZ control on an external reference E.
    for x, amp in enumerate(v):
        e = x >> p["width"]
        c = x & 1
        a = (x >> 1) & 3
        b = (x >> 3) & 3
        useful = (c * multiplication_oracle(a, b, 2, 7)) & 1
        target.append(amp * (-1 if useful and e else 1))
    for ss in itertools.product(range(4), repeat=2):
        out = [0j] * (2 * d)
        for x, amp in enumerate(target):
            y, sign = exact_branch_column(p, list(ss), x)
            out[y] += amp * sign / 4
        assert max(abs(out[x] - target[x] / 4) for x in range(2 * d)) < 1e-14
        assert abs(sum(abs(a) ** 2 for a in out) - 1 / 16) < 1e-14


@pytest.mark.parametrize("fault", ["dirty", "stale"])
def test_invalid_context_really_changes_phase_or_output(fault):
    p = compile_bank(2, 7, 1)
    failures = []
    for s in range(4):
        for x in range(1 << p["width"]):
            y, sgn = exact_branch_column(p, [s], x, **{fault: True})
            if (y, sgn) != (x, 1):
                failures.append((s, x, y, sgn))
    assert failures


@pytest.mark.parametrize("m,poly,bank", [(2, 7, 2), (3, 11, 2), (12, 0x1053, 1)])
def test_preparation(m, poly, bank):
    src = emit_source(m, poly, bank, None)
    r = prove_preparation(src)
    assert r["arbitrary_live_bits"] == 1 + m * (1 + bank)


@pytest.mark.parametrize("fault", ["phase", "dirty", "stale", "alias", "deleted_product"])
def test_preparation_mutants(fault):
    src = emit_source(3, 11, 1)
    if fault == "phase":
        src["gates"].append(["z", [0]])
    if fault == "dirty":
        src["gates"].insert(0, ["cx", [1, 7]])
    if fault == "stale":
        src["gates"].append(["x", [1]])
    if fault == "alias":
        src["gates"].append(["cx", [1, 1]])
    if fault == "deleted_product":
        i = next(i for i, g in enumerate(src["gates"]) if g[0] == "mcx")
        del src["gates"][i]
    with pytest.raises(Rejected):
        prove_preparation(src)


@pytest.mark.parametrize(
    "fault", ["phase", "restore", "guard", "forward", "boolean", "unsupported"]
)
def test_correction_mutants(fault):
    p = compile_bank(3, 11, 1)
    if fault == "phase":
        i = next(i for i, g in enumerate(p["quantum"]) if g[0] == "ccz")
        del p["quantum"][i]
    if fault == "restore":
        p["quantum"].append(["cx", 4, 5, 1])
    if fault == "guard":
        for g in p["quantum"]:
            if g[0] == "ccz":
                g[-1] = 0
    if fault == "forward":
        p["classical"][0][1] = 10**9
    if fault == "boolean":
        p["quantum"][0][-1] = True
    if fault == "unsupported":
        p["quantum"][0][0] = "h"
    failures = 0
    for s in range(8):
        try:
            check_outcome(p, [s])
        except Rejected:
            failures += 1
    assert failures


def test_binding_and_untrusted_verdict():
    p = compile_bank(3, 11, 1)
    c = {"schema": "bilinear-phase-branch-v1", "program_sha256": digest(p), "outcomes": [1]}
    assert check_certificate(p, c)["ccz"] == 3
    for key, value in [("program_sha256", "0" * 64), ("proved", True)]:
        bad = c | {key: value}
        with pytest.raises(Rejected):
            check_certificate(p, bad)


@pytest.mark.parametrize("data", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_strict_json(data, tmp_path):
    p = tmp_path / "x.json"
    p.write_text(data)
    with pytest.raises(Rejected):
        load_strict(str(p))


@pytest.mark.parametrize("m,p,k", [(True, 7, 1), (3, 9, 1), (3, 11, 0), (3, 11, 129), (1, 3, 1)])
def test_bad_parameters(m, p, k):
    with pytest.raises(ValueError):
        compile_bank(m, p, k)


def test_budget_is_not_success():
    p = compile_bank(3, 11, 1)
    with pytest.raises(Inconclusive):
        check_outcome(p, [1], seconds=0)
    with pytest.raises(Inconclusive):
        prove_preparation(emit_source(3, 11, 1), seconds=0)
    with pytest.raises(Inconclusive):
        prove_preparation(emit_source(3, 11, 1), max_terms=0)


def test_zero_outcome_and_zero_qubit_overhead():
    p = compile_bank(12, 0x1053, 4)
    r = check_outcome(p, [0, 0, 0, 0])
    assert r["ccz"] == r["cx"] == 0
    assert p["width"] == 61


def test_shared_AND_cache_is_a_strong_baseline():
    # Exact comparison of every branch, including the extra HMR record mu.
    # Those extra records must be forgotten, not asserted to match an instrument.
    m = 2
    p = compile_bank(m, 7, 2)
    for ss in itertools.product(range(4), repeat=2):
        gates = branch(p, list(ss))
        for mu in range(4):
            for x in range(1 << p["width"]):
                c = x & 1
                a = (x >> 1) & 3
                u = c * a
                ref = 0
                for j, s in enumerate(ss):
                    b = (x >> (1 + m + j * m)) & 3
                    ref ^= (s & multiplication_oracle(u, b, m, 7)).bit_count() & 1
                # Extra HMR phase and its conditional-CZ repair cancel exactly.
                ref ^= (mu & u).bit_count() & 1
                ref ^= (mu & (c * a)).bit_count() & 1
                y, sgn = scalar_replay(x, gates)
                assert y == x and sgn == (-1 if ref else 1)


def test_rank_obstruction_even_when_CCZ_forms_mix_registers():
    from symq.labs.bilinear_phase_fusion.checker import binary_rank

    # Derivative in c of any CCZ on three affine forms has polar rank <= 2.
    rng = random.Random(81)
    n = 5
    for _ in range(1000):
        forms = [rng.randrange(1 << (n + 2)) for _ in range(3)]

        def evaluate(c, x, forms=forms):
            y = (x << 1) | c | (1 << (n + 1))
            v = 1
            for form in forms:
                v &= (y & form).bit_count() & 1
            return v

        def q(x):
            return evaluate(0, x) ^ evaluate(1, x)

        zero = q(0)
        rows = [
            sum((q((1 << i) ^ (1 << j)) ^ q(1 << i) ^ q(1 << j) ^ zero) << j for j in range(n))
            for i in range(n)
        ]
        assert binary_rank(rows) <= 2
