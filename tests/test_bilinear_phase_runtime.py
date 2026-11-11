"""Runtime, source binding, and refusal tests, independent of the optimizer."""

from __future__ import annotations

import copy
import itertools

import pytest

from symq import Circuit
from symq.anf import ANF
from symq.labs.bilinear_phase_fusion.checker import (
    Inconclusive,
    Rejected,
    canonical_digest,
    check_outcome,
    multiplication_oracle,
)
from symq.labs.bilinear_phase_fusion.compiler import compile_bank
from symq.labs.bilinear_phase_fusion.preparation import emit_source, to_symq
from symq.labs.bilinear_phase_fusion.runtime import (
    check_source_certificate,
    correction_for_outcome,
    preparation_document,
)
from symq.phase import phase_semantics


def certificate(source, program, outcomes):
    return {
        "schema": "bilinear-phase-erasure-branch-v1",
        "preparation_sha256": canonical_digest(preparation_document(source, program)),
        "program_sha256": canonical_digest(program),
        "outcomes": outcomes,
    }


def test_actual_circuit_adapter_on_every_small_input():
    source = to_symq(emit_source(2, 7, 2))
    assert type(source) is Circuit
    live = 7
    for x in range(1 << live):
        c, a = x & 1, (x >> 1) & 3
        expected = x
        for j in range(2):
            b = (x >> (3 + 2 * j)) & 3
            expected |= (c * multiplication_oracle(a, b, 2, 7)) << (live + 2 * j)
        assert source.run(x) == expected


def test_native_phase_ir_matches_independent_polynomial_for_all_branches():
    p = compile_bank(3, 11, 2)
    for outcomes in itertools.product(range(8), repeat=2):
        result = phase_semantics(correction_for_outcome(p, list(outcomes)))
        expected = set()
        for j, s in enumerate(outcomes):
            for a in range(3):
                for b in range(3):
                    if (s & multiplication_oracle(1 << a, 1 << b, 3, 11)).bit_count() & 1:
                        expected.add(1 | (1 << (1 + a)) | (1 << (4 + 3 * j + b)))
        assert result.phase == ANF(frozenset(expected))
        assert result.outputs == tuple(ANF.variable(i) for i in range(p["width"]))


def test_source_bound_prepared_branch_replays_and_restores_all_live_versions():
    p = compile_bank(3, 11, 2)
    source = to_symq(emit_source(3, 11, 2))
    cert = certificate(source, p, [1, 7])
    r = check_source_certificate(source, p, cert)
    assert r["theorem"] == "prepared_bilinear_erasure_branch"
    assert r["source_interval"] == [0, len(source.gates)]
    assert r["additional_forgotten_outcomes"] == 0
    assert r["correction"]["restored_wires"] == p["width"]
    assert r["preparation"]["application_site_extracted"] is False


@pytest.mark.parametrize("fault", ["dirty", "stale", "delete", "binding", "flag", "width"])
def test_source_mutations_never_inherit_a_preparation_proof(fault):
    p = compile_bank(3, 11)
    source = to_symq(emit_source(3, 11, 1))
    cert = certificate(source, p, [3])
    if fault == "binding":
        source.x(0)
    elif fault == "flag":
        cert["prepared"] = True
    else:
        if fault == "dirty":
            source.cx(1, p["width"])
        if fault == "stale":
            source.x(1)
        if fault == "delete":
            source.gates.pop()
        if fault == "width":
            source.width += 1
        if fault != "width":
            # A matching digest does not authorize incorrect preparation either.
            cert = certificate(source, p, [3])
    with pytest.raises(Rejected):
        check_source_certificate(source, p, cert)


@pytest.mark.parametrize("seconds", [float("nan"), float("inf"), True, "1"])
def test_malformed_time_budget_is_rejected(seconds):
    with pytest.raises(Rejected):
        check_outcome(compile_bank(2, 7), [1], seconds=seconds)


def test_budget_expiration_during_classical_validation_is_inconclusive(monkeypatch):
    p = compile_bank(3, 11)
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(
        "symq.labs.bilinear_phase_fusion.checker.time.monotonic", lambda: next(ticks, 2)
    )
    with pytest.raises(Inconclusive):
        check_outcome(p, [1], seconds=1)


def test_checker_does_not_call_the_compiler(monkeypatch):
    p = compile_bank(3, 11)
    source = to_symq(emit_source(3, 11, 1))
    cert = certificate(source, p, [3])

    def forbidden(*args, **kwargs):
        raise AssertionError("compiler called from checker")

    monkeypatch.setattr("symq.labs.bilinear_phase_fusion.compiler.compile_bank", forbidden)
    assert check_source_certificate(source, p, cert)["correction"]["ccz"] == 3
    mutant = copy.deepcopy(p)
    mutant["quantum"] = [g for g in p["quantum"] if g[0] != "ccz"]
    cert["program_sha256"] = canonical_digest(mutant)
    with pytest.raises(Rejected, match="phase coefficient"):
        check_source_certificate(source, mutant, cert)
