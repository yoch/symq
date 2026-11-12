"""The table and clean-ancilla checks run under hard operating-system limits.

A downstream user of 0.2.0 rebuilt their own resource limits around these research checks.
``symq.labs.isolated_jobs`` makes them runnable by ``run_isolated``: the job's value equals
the in-process result; a hard wall, CPU or memory limit that stops the worker yields no
value at all, never a verdict; an absolute deadline cannot leak into the worker.
"""
from __future__ import annotations

import json
import sys
import time
from fractions import Fraction

import pytest

from benchmarks.affine_table import wide_fixture
from symq.experimental.execution import HardLimits, run_isolated
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.affine_table import verify_affine_table
from symq.labs.backward_ancilla import AncillaLimits, check_clean_ancilla
from symq.labs.isolated_jobs import (
    affine_table_job,
    clean_ancilla_job,
    shared_table_job,
    shift_diagonal_job,
)
from symq.labs.shift_diagonal_ancilla import check_shift_diagonal
from symq.resources import Budget, VerificationSession

LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"),
                           reason="SymQ relies on the address-space and CPU limits on Linux only")


def _dirty() -> HybridProgram:
    return HybridProgram(2, 1).cx(0, 2).cx(1, 2)


def _clean() -> HybridProgram:
    program = HybridProgram(2, 1).ccx(0, 1, 2)
    return program.ccx(0, 1, 2)


def _half() -> HybridProgram:
    """The target is flipped by a measured coin: error probability exactly 1/2."""
    return HybridProgram(1, 1).hmr(0, "b0").x(1, condition="b0")


def _long() -> HybridProgram:
    """A 10-control compute/uncompute: seconds of Pauli work before its product cap."""
    program = HybridProgram(10, 1)
    program.mcx(*range(11))
    return program.mcx(*range(11))


def _without_seconds(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "seconds"}


@pytest.mark.parametrize(("program", "target"), [(_dirty(), 2), (_clean(), 2), (_half(), 1)],
                         ids=["dirty", "clean", "half"])
def test_an_ancilla_job_is_the_engine_result_as_json(program, target):
    for job, check in ((clean_ancilla_job, check_clean_ancilla),
                       (shift_diagonal_job, check_shift_diagonal)):
        value = job(program_to_dict(program), target)
        result = check(program, target)
        assert json.loads(json.dumps(value)) == value
        probability = (value["witness"] or {}).get("probability") if "witness" in value \
            else value["probability"]
        assert probability is None or type(probability) is str
        assert value["status"] == result.status
        if job is clean_ancilla_job:
            assert value["certificate"] == (result.certificate.to_dict()
                                            if result.certificate else None)
            witness = value["witness"]
            if program.ops[0].kind == "hmr":
                assert witness["probability"] == "1/2"
            assert (witness is None) == (result.witness is None)
            if witness:
                assert witness["assignment"] == result.witness.assignment
                assert Fraction(witness["probability"]) == result.witness.probability
        else:
            assert value["assignment"] == result.assignment
            assert (value["probability"] is None if result.probability is None
                    else Fraction(value["probability"]) == result.probability)


def test_an_inconclusive_ancilla_job_keeps_its_report():
    program = _clean()
    value = clean_ancilla_job(program_to_dict(program), 2,
                              limits=AncillaLimits(max_products=1))
    assert value["status"] == "inconclusive" and value["resource"] == "pauli_products"
    assert dict(value["limits"])["max_products"] == 1
    assert json.loads(json.dumps(value)) == value  # the pairs became JSON arrays, not tuples


def test_a_table_job_is_the_verifier_result():
    source, contract = wide_fixture()
    assert (_without_seconds(affine_table_job(source, contract))
            == _without_seconds(verify_affine_table(source, contract)))


def test_an_absolute_deadline_is_refused_and_a_session_budget_is_converted():
    program = program_to_dict(_dirty())
    with pytest.raises(ValueError, match="absolute deadline"):
        shift_diagonal_job(program, 2, budget=Budget(absolute_deadline=time.perf_counter() + 9))
    with pytest.raises(TypeError):
        clean_ancilla_job(program, 2, budget={"max_seconds": 1})
    source, contract = wide_fixture()
    with pytest.raises(ValueError, match="absolute deadline"):
        shared_table_job(source, contract, budget=Budget(absolute_deadline=1.0))
    with VerificationSession(Budget(max_seconds=60)) as session:
        relative = session.subprocess_budget()
        assert relative.absolute_deadline is None
        assert shift_diagonal_job(program, 2, budget=relative)["status"] == "not_clean"


def test_jobs_run_in_a_worker_and_return_the_same_value():
    program = program_to_dict(_dirty())
    for job in (clean_ancilla_job, shift_diagonal_job):
        outcome = run_isolated(job, program, 2, limits=HardLimits(wall_seconds=60))
        assert outcome.status == "completed", outcome
        assert outcome.value == job(program, 2)
        assert outcome.exitcode == 0
    source, contract = wide_fixture()
    outcome = run_isolated(affine_table_job, source, contract,
                           limits=HardLimits(wall_seconds=120))
    assert outcome.status == "completed", outcome
    assert _without_seconds(outcome.value) == _without_seconds(affine_table_job(source, contract))
    if sys.platform != "win32":
        assert outcome.peak_rss_bytes > 0


@pytest.mark.timing
def test_a_hard_wall_limit_stops_the_worker_without_a_verdict():
    started = time.perf_counter()
    outcome = run_isolated(clean_ancilla_job, program_to_dict(_long()), 10,
                           limits=HardLimits(wall_seconds=1.0))
    assert outcome.status == "inconclusive" and outcome.value is None
    assert time.perf_counter() - started < 5


@LINUX
def test_a_hard_cpu_limit_stops_the_worker_without_a_verdict():
    import signal

    outcome = run_isolated(clean_ancilla_job, program_to_dict(_long()), 10,
                           limits=HardLimits(wall_seconds=30, cpu_seconds=1))
    assert outcome.status == "inconclusive" and outcome.value is None
    assert outcome.exitcode == -signal.SIGXCPU  # killed by the CPU limit, not a raised error


@LINUX
def test_a_memory_limit_the_worker_cannot_meet_gives_no_verdict():
    outcome = run_isolated(shift_diagonal_job, program_to_dict(_dirty()), 2,
                           limits=HardLimits(wall_seconds=30, memory_bytes=1024**2))
    assert outcome.status == "inconclusive" and outcome.value is None
    assert outcome.reason == "worker memory limit exceeded"


def _shared() -> tuple[dict, dict]:
    """An identity loader and a constant-zero two-bit shared table."""
    from symq.experimental.table_xor import PredicateValues
    from symq.labs.shared_table import SharedTable

    table = SharedTable.from_rows([0] * 4, address_bits=2, target_bits=1)
    contract = {"kind": "symq_shared_affine_table_contract", "schema_version": 3, "width": 3,
                "address_wires": [0, 1], "target_wires": [2], "clean_wires": [],
                "borrowed_wires": [], "table": table.to_dict(),
                "address_domain": PredicateValues.below(2, 4).to_dict(),
                "target_space": {"kind": "affine_image", "offset": 0, "columns": [1]},
                "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}
    return program_to_dict(HybridProgram(3, 0)), contract


def test_an_absolute_deadline_computed_in_the_worker_is_not_reported():
    """``verify_shared_table`` turns its budget into a deadline of the worker's clock."""
    source, contract = _shared()
    assert shared_table_job(source, contract, budget=Budget(max_seconds=30))["status"] == (
        "equivalent")
    report = shared_table_job(source, contract, budget=Budget(max_seconds=1e-9))
    assert report["status"] == "inconclusive" and report["limits"]["max_seconds"] == 1e-9
    assert report["limits"].get("absolute_deadline") is None
    from symq.labs.isolated_jobs import _json

    inner = {"status": "inconclusive", "limits": {"absolute_deadline": 4565.9, "max_terms": 3}}
    assert _json(inner) == {"status": "inconclusive", "limits": {"max_terms": 3}}
    assert _json({"absolute_deadline": None}) == {"absolute_deadline": None}
