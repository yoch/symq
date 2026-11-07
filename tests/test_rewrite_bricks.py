"""Portable data packages never carry proof authority from one site to another."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from symq import Circuit, Gate
from symq.labs import contextual_substitution, rewrite_bricks
from symq.labs.classical_transcript import Program, digest
from symq.labs.rewrite_bricks import (
    check_brick_examples,
    load_classical_brick,
    run_classical_brick,
)
from symq.labs.rewrite_request import replayed_candidate
from symq.resources import Budget, Guard, ResourceLimitExceeded, VerificationSession

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/rewrite_bricks/clean_product.json"
PIN = "d3c2d8d8bcaa2155a8b3b599ac7911b449fb996ade94495bdbf1b5658618ea54"


def _brick():
    return load_classical_brick(EXAMPLE.read_bytes(), expected_sha256=PIN)


def _encoded(doc):
    raw = json.dumps(doc, sort_keys=True).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def _site(index=0):
    case = _brick().to_dict()["examples"][index]
    source = Circuit(case["source"]["width"], [
        Gate(name, tuple(wires)) for name, wires in case["source"]["gates"]
    ])
    constants = tuple(tuple(pair) for pair in case["initial_constants"])
    return source, constants


def _run(brick, source, constants, **kwargs):
    return run_classical_brick(
        brick, source, expected_brick_sha256=brick.sha256,
        expected_source_sha256=digest(Program.freeze(source)),
        initial_constants=constants, **kwargs,
    )


def _scalar(circuit, value):
    """Independent small bit-list semantics, no SAT or Circuit.run."""
    state = [(value >> q) & 1 for q in range(circuit.width)]
    for gate in circuit.gates:
        if all(state[q] for q in gate.qubits[:-1]):
            state[gate.qubits[-1]] ^= 1
    return sum(bit << q for q, bit in enumerate(state))


def _spliced(source, replacement, wires, span):
    mapped = [Gate(name, tuple(wires[q] for q in qs)) for name, qs in replacement["gates"]]
    return Circuit(source.width, source.gates[:span[0]] + mapped + source.gates[span[1]:])


def test_loading_checks_pinned_bytes_and_declared_license_without_running_proof(monkeypatch):
    def no_proof(*_args, **_kwargs):
        raise AssertionError("loading must not prove or execute a brick")

    monkeypatch.setattr(rewrite_bricks, "run_request", no_proof)
    brick = _brick()
    assert brick.sha256 == PIN
    assert brick.to_dict()["sources"][0]["license"] == "MIT"
    edited = brick.to_dict()
    edited["cut_contract"]["clean_at_cut"] = []
    assert brick.to_dict()["cut_contract"]["clean_at_cut"] == [2]
    with pytest.raises(ValueError, match="SHA-256"):
        load_classical_brick(brick.data + b"\n", expected_sha256=PIN)


@pytest.mark.sat
def test_portable_positive_and_mutant_examples_are_reexecuted_against_finite_oracle():
    brick = _brick()
    report = check_brick_examples(brick, expected_brick_sha256=PIN)
    assert report["all_expectations_met"] and not report["authorizes_other_sites"]
    assert [row["run"]["status"] for row in report["examples"]] == [
        "equivalent", "equivalent", "precondition_failed", "not_proved",
    ]
    doc = brick.to_dict()
    for index, row in enumerate(report["examples"]):
        case = doc["examples"][index]
        source, constants = _site(index)
        wires, span = ((4, 1, 5, 2), (3, 6)) if index == 1 else ((0, 1, 2, 3), (2, 5))
        candidate = _spliced(source, case["replacement"] or doc["replacement"], wires, span)
        differences = []
        for value in range(1 << source.width):
            if (all(((value >> q) & 1) == bit for q, bit in constants)
                    and _scalar(source, value) != _scalar(candidate, value)):
                differences.append(value)
        assert bool(differences) == (case["kind"] == "mutant")
        run = row["run"]
        assert run["quantum_mapping"] == list(wires)
        assert not run["saved_result_is_authority"]
        assert run["classical_mapping"] == []
        if case["kind"] == "positive":
            fresh = replayed_candidate(run["proof_report"])
            assert fresh is not None and fresh.gates == candidate.gates
        else:
            assert run["proof_report"]["candidate"] is None


@pytest.mark.sat
def test_each_site_reproves_prefix_and_restoration_after_success_elsewhere(monkeypatch):
    real = contextual_substitution.check_composition
    calls = []

    def record(**kwargs):
        calls.append(kwargs["prefix_left"].to_dict())
        return real(**kwargs)

    monkeypatch.setattr(contextual_substitution, "check_composition", record)
    brick = _brick()
    first, domain_one = _site(0)
    second, domain_two = _site(1)
    one = _run(brick, first, domain_one)
    two = _run(brick, second, domain_two)
    dirty = _run(brick, second, ())
    assert one["status"] == two["status"] == "equivalent"
    assert len(calls) == 3 and calls[0] != calls[1]
    assert dirty["status"] == "precondition_failed"
    assert dirty["proof_report"]["candidate"] is None
    for run in (one, two):
        assert {"prefix", "restore_original", "restore_candidate"} <= {
            item["name"] for item in run["proof_report"]["result"]["obligations"]
        }


@pytest.mark.sat
def test_same_pattern_after_changed_prefix_cannot_reuse_old_success():
    brick = _brick()
    source, constants = _site()
    assert _run(brick, source, constants)["status"] == "equivalent"
    changed = source.snapshot()
    del changed.gates[0]  # Leaves q2=a at the cut, despite the same initial zero.
    result = _run(brick, changed, constants)
    assert result["status"] == "precondition_failed"
    assert result["proof_report"]["candidate"] is None
    with pytest.raises(ValueError, match="source SHA-256"):
        run_classical_brick(
            brick, changed, expected_brick_sha256=PIN,
            expected_source_sha256=digest(Program.freeze(source)), initial_constants=constants,
        )


@pytest.mark.sat
def test_local_cut_formula_and_orderless_resources_map_to_global_wires():
    doc = _brick().to_dict()
    doc["cut_contract"] = {
        "clean_at_cut": [], "restored_at_cut": [2, 0, 1],
        "cut_assumption": {"kind": "not", "operand": {"kind": "var", "name": "u.2"}},
    }
    raw, pin = _encoded(doc)
    brick = load_classical_brick(raw, expected_sha256=pin)
    source, constants = _site(1)
    run = _run(brick, source, constants)
    assert run["status"] == "equivalent"
    contract = run["proof_report"]["request"]["contract"]
    assert contract["restored_at_cut"] == [1, 4, 5]
    assert contract["cut_assumption"] == {
        "kind": "not", "operand": {"kind": "var", "name": "u.5"},
    }


@pytest.mark.sat
def test_declared_test_labels_cannot_make_an_incorrect_replacement_proved():
    doc = _brick().to_dict()
    doc["replacement"]["gates"] = []
    raw, pin = _encoded(doc)
    brick = load_classical_brick(raw, expected_sha256=pin)
    report = check_brick_examples(brick, expected_brick_sha256=pin)
    assert not report["all_expectations_met"]
    assert not report["examples"][0]["matches_expected"]
    assert _run(brick, *_site())["status"] == "not_proved"


@pytest.mark.sat
@pytest.mark.parametrize("extra_gates", [
    [["x", [3]], ["x", [3]]],  # Identity on every input.
    [["cx", [2, 3]]],  # Identity only on the required clean-scratch domain.
])
def test_equivalent_mutants_are_reproved_without_assuming_every_change_is_wrong(extra_gates):
    doc = _brick().to_dict()
    mutant = copy.deepcopy(doc["examples"][0])
    mutant.update(name="neutral-mutation", kind="mutant", expected_outcome="equivalent",
                  replacement=copy.deepcopy(doc["replacement"]))
    mutant["replacement"]["gates"].extend(extra_gates)
    doc["examples"].append(mutant)
    raw, pin = _encoded(doc)
    brick = load_classical_brick(raw, expected_sha256=pin)
    report = check_brick_examples(brick, expected_brick_sha256=pin)
    assert report["all_expectations_met"] and not report["authorizes_other_sites"]
    run = report["examples"][-1]["run"]
    assert run["status"] == "equivalent"
    candidate = replayed_candidate(run["proof_report"])
    source, constants = _site()
    expected = _spliced(source, mutant["replacement"], (0, 1, 2, 3), (2, 5))
    assert candidate is not None and candidate.gates == expected.gates
    for value in range(1 << source.width):
        if all(((value >> q) & 1) == bit for q, bit in constants):
            assert _scalar(source, value) == _scalar(candidate, value)


@pytest.mark.parametrize("source", [
    Circuit(4),
    Circuit(4).ccx(0, 1, 2).cx(2, 3).ccx(0, 1, 2)
              .ccx(0, 1, 2).cx(2, 3).ccx(0, 1, 2),
])
def test_missing_or_ambiguous_site_is_nonactionable(source):
    result = _run(_brick(), source, ((2, 0),))
    assert result["status"] in ("not_found", "ambiguous")
    assert result["proof_report"] is None and result["quantum_mapping"] is None


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 1.0),
    ("theorem", "coherent"), ("phase_policy", "ignore_global_phase"),
    ("classical_mapping", [["b0", "b1"]]), ("sources", []),
])
def test_closed_theorem_and_manifest_fields_reject_unsupported_claims(field, value):
    doc = _brick().to_dict()
    doc[field] = value
    raw, pin = _encoded(doc)
    with pytest.raises(ValueError):
        load_classical_brick(raw, expected_sha256=pin)


@pytest.mark.parametrize("field,value", [
    ("verified", True), ("proof_report", {"outcome": "equivalent"}),
    ("python", "import os"), ("entrypoint", "module:function"),
])
def test_saved_passes_or_executable_hooks_are_not_part_of_the_data_format(field, value):
    doc = _brick().to_dict()
    doc[field] = value
    raw, pin = _encoded(doc)
    with pytest.raises(ValueError, match="exactly"):
        load_classical_brick(raw, expected_sha256=pin)


@pytest.mark.parametrize("gate", [["z", [0]], ["hmr", [2]], ["ccx", [0, 1, 1]]])
def test_gate_grammar_rejects_phase_measurement_and_aliased_operands(gate):
    doc = _brick().to_dict()
    doc["replacement"]["gates"] = [gate]
    raw, pin = _encoded(doc)
    with pytest.raises(ValueError):
        load_classical_brick(raw, expected_sha256=pin)


@pytest.mark.parametrize("mutation", [
    "unmapped", "input_domain", "bad_cut", "license", "revision", "moving_revision",
])
def test_incomplete_mapping_domain_smuggling_or_missing_provenance_is_refused(mutation):
    doc = _brick().to_dict()
    if mutation == "unmapped":
        doc["pattern"]["width"] = doc["replacement"]["width"] = 5
    elif mutation == "input_domain":
        doc["cut_contract"]["initial_constants"] = [[2, 0]]
    elif mutation == "bad_cut":
        doc["cut_contract"]["cut_assumption"] = {"kind": "var", "name": "x.0"}
    elif mutation == "license":
        doc["sources"][0]["license"] = ""
    else:
        doc["sources"][0]["origin"] = "adapted"  # A revision is then required.
        if mutation == "moving_revision":
            doc["sources"][0]["source_revision"] = "main"
    raw, pin = _encoded(doc)
    with pytest.raises(ValueError):
        load_classical_brick(raw, expected_sha256=pin)


@pytest.mark.parametrize("revision", ["a" * 40, "b" * 64])
def test_adapted_provenance_accepts_explicit_content_identities_as_metadata(revision):
    doc = _brick().to_dict()
    doc["sources"][0].update(origin="adapted", source_revision=revision)
    raw, pin = _encoded(doc)
    assert load_classical_brick(raw, expected_sha256=pin).to_dict()["sources"][0][
        "source_revision"
    ] == revision


def test_brick_and_source_consumer_pins_are_required_and_revalidated():
    brick = _brick()
    source, constants = _site()
    with pytest.raises(TypeError):
        run_classical_brick(brick, source, initial_constants=constants)
    with pytest.raises(ValueError, match="SHA-256"):
        run_classical_brick(
            brick, source, expected_brick_sha256="0" * 64,
            expected_source_sha256=digest(Program.freeze(source)), initial_constants=constants,
        )
    for changed in (replace(brick, data=brick.data + b"\n"), replace(brick, sha256="0" * 64)):
        with pytest.raises(ValueError):
            run_classical_brick(
                changed, source, expected_brick_sha256=PIN,
                expected_source_sha256=digest(Program.freeze(source)), initial_constants=constants,
            )


def test_duplicate_json_and_oversized_documents_fail_before_any_proof():
    raw = b'{"kind":"ignored","kind":"symq_classical_rewrite_brick"}'
    with pytest.raises(ValueError, match="duplicate"):
        load_classical_brick(raw, expected_sha256=hashlib.sha256(raw).hexdigest())
    large = b" " * (rewrite_bricks.MAX_BRICK_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds"):
        load_classical_brick(large, expected_sha256=hashlib.sha256(large).hexdigest())


@pytest.mark.parametrize("limit", ["gates", "width"])
def test_source_limits_precede_snapshot(monkeypatch, limit):
    source = Circuit(4 if limit == "gates" else rewrite_bricks.MAX_SOURCE_WIDTH + 1)
    if limit == "gates":
        source.gates = [Gate("x", (0,))] * (rewrite_bricks.MAX_SOURCE_GATES + 1)

    def no_snapshot(*_args, **_kwargs):
        raise AssertionError("oversized source must be refused before snapshot")

    monkeypatch.setattr(Circuit, "snapshot", no_snapshot)
    result = run_classical_brick(
        _brick(), source, expected_brick_sha256=PIN, expected_source_sha256="0" * 64,
        initial_constants=(),
    )
    assert result["status"] == "inconclusive" and result["proof_report"] is None


@pytest.mark.sat
def test_whole_call_timeout_revokes_a_positive_inner_report(monkeypatch):
    real_run = rewrite_bricks.run_request
    real_check = Guard.check_time
    expired = False

    def after_proof(*args, **kwargs):
        nonlocal expired
        report = real_run(*args, **kwargs)
        assert report["result"]["outcome"] == "equivalent"
        expired = True
        return report

    def check(guard):
        if expired:
            raise ResourceLimitExceeded("seconds", 1, 2)
        return real_check(guard)

    monkeypatch.setattr(rewrite_bricks, "run_request", after_proof)
    monkeypatch.setattr(Guard, "check_time", check)
    run = _run(_brick(), *_site())
    assert run["status"] == "inconclusive" and run["proof_report"] is None


def test_expired_and_unsupported_inherited_budgets_never_yield_a_candidate():
    run = _run(_brick(), *_site(), budget=Budget(max_seconds=1e-9))
    assert run["status"] == "inconclusive" and run["proof_report"] is None
    with VerificationSession(Budget(max_bytes=1024)), pytest.raises(ValueError, match="budgets"):
        _run(_brick(), *_site())
    examples = check_brick_examples(_brick(), expected_brick_sha256=PIN,
                                    budget=Budget(max_seconds=1e-9))
    assert examples["status"] == "inconclusive" and not examples["all_expectations_met"]


def test_malformed_example_expectations_cannot_make_skips_count_as_success():
    for field, value in (("expected_outcome", "unsupported"), ("kind", "passed")):
        doc = _brick().to_dict()
        doc["examples"][2][field] = value
        raw, pin = _encoded(doc)
        with pytest.raises(ValueError):
            load_classical_brick(raw, expected_sha256=pin)
    doc = _brick().to_dict()
    doc["examples"] = copy.deepcopy(doc["examples"][:2])
    raw, pin = _encoded(doc)
    with pytest.raises(ValueError, match="positive and mutant"):
        load_classical_brick(raw, expected_sha256=pin)
    doc = _brick().to_dict()
    for case in doc["examples"]:
        case["expected_outcome"] = "equivalent"
    raw, pin = _encoded(doc)
    with pytest.raises(ValueError, match="decisive negative"):
        load_classical_brick(raw, expected_sha256=pin)
