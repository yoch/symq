"""Full-source scalar oracles, lost-correlation regressions and hostile receipts."""
from __future__ import annotations

import copy
import hashlib
import json
import random
from dataclasses import replace

import pytest

from symq import Circuit
from symq.experimental.domains import expression_to_dict
from symq.hashing import canonical_sha256
from symq.labs import indexed_substitution as api
from symq.labs.kmx_source_index import IndexLimits, QueryLimits, build_kmx_index
from symq.labs.rewrite import ReceiptMismatch
from symq.resources import Budget
from symq.sat.assumptions import And, Const, Eq, Not, Var


def scalar(operations, width, value):
    """No Circuit interpreter, parser, symbolic expression or SAT machinery."""
    bits = [(value >> q) & 1 for q in range(width)]
    for name, wires in operations:
        if name == "x":
            bits[wires[0]] ^= 1
        elif name == "cx":
            bits[wires[1]] ^= bits[wires[0]]
        elif name == "ccx":
            bits[wires[2]] ^= bits[wires[0]] & bits[wires[1]]
        else:
            raise AssertionError(name)
    return sum(bit << q for q, bit in enumerate(bits))


def problem(tmp_path, *, raw=None, span=(3, 4), replacement=None, contract=None, wires=None):
    if raw is None:
        # The last prefix write to q0 is irrelevant to the required q2 value.
        # Dropping it is safe for Q, but the cone is not the complete prefix.
        raw = b"CX q0 q2\nX q5\nX q0\nCX q2 q3\nCCX q1 q3 q5\n"
    path = tmp_path / "source.kmx"
    path.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    if replacement is None:
        replacement = Circuit(1)
    if contract is None:
        contract = {
            "initial_assumption": expression_to_dict(Eq(Var("x.0"), Var("x.2"))),
            "clean_at_cut": [2],
        }
    doc = {"kind": "symq_indexed_classical_substitution", "schema_version": 1,
           "source_file_sha256": pin, "prefix_start_op": 0, "op_span": list(span),
           "replacement": replacement.to_dict(),
           "replacement_wires": [3] if wires is None else wires, "contract": contract}
    return path, doc


def pins(doc):
    return {"expected_source_sha256": doc["source_file_sha256"],
            "expected_request_sha256": canonical_sha256(doc)}


def prove(path, doc, **kwargs):
    return api.prove_indexed_substitution(path, doc, **pins(doc), **kwargs)


@pytest.mark.sat
def test_composition_keeps_exact_window_and_only_claims_a_plan(tmp_path):
    path, doc = problem(tmp_path)
    result = prove(path, doc)
    assert result["status"] == "equivalent"
    assert result["complete_candidate"] is result["global_cost"] is None
    assert result["extractions"]["origin_cone"]["gate_indices"] == [0]
    assert result["extractions"]["window"]["gate_indices"] == [3]
    assert result["support"]["local_to_global"] == [0, 2, 3]
    assert result["reduced"]["local_span"] == [1, 2]
    assert result["applicable_plan"]["global_op_span"] == [3, 4]
    assert result["composition"]["external_preparation_proved"] is False
    assert {"domain", "prefix", "suffix", "restore_original", "restore_candidate"} <= set(
        result["composition"]["proved_facts"])
    operations = [("cx", (0, 2)), ("x", (5,)), ("x", (0,)),
                  ("cx", (2, 3)), ("ccx", (1, 3, 5))]
    candidate = operations[:3] + operations[4:]
    for value in range(64):
        if ((value >> 0) ^ (value >> 2)) & 1 == 0:
            assert scalar(operations, 6, value) == scalar(candidate, 6, value)
    fresh = api.replay_indexed_substitution(path, doc, json.loads(json.dumps(result)), **pins(doc))
    assert fresh == result


@pytest.mark.sat
def test_initial_correlation_outside_cone_is_not_projected(tmp_path):
    # q7 never occurs in the cone. Its identity INPUT must remain correlated
    # with q1. Its actual cut value differs (X q7 is omitted by extraction).
    domain = And(Eq(Var("x.1"), Var("x.7")), Not(Var("x.7")))
    path, doc = problem(tmp_path, raw=b"X q7\nCX q1 q2\n", span=(1, 2),
                        replacement=Circuit(1), wires=[2],
                        contract={"initial_assumption": expression_to_dict(domain),
                                  "clean_at_cut": [1]})
    result = prove(path, doc)
    assert result["status"] == "equivalent"
    assert result["support"]["identity_domain_inputs_outside_cone"] == [7]
    assert result["support"]["local_to_global"] == [1, 2, 7]
    assert result["extractions"]["origin_cone"]["gate_indices"] == []
    for value in range(256):
        if value & (1 << 1 | 1 << 7) == 0:
            assert scalar([("x", (7,)), ("cx", (1, 2))], 8, value) == value ^ (1 << 7)
    doc["contract"] = {"clean_at_cut": [1]}
    assert prove(path, doc)["status"] == "precondition_failed"


@pytest.mark.sat
def test_preserving_q_but_changing_another_output_is_rejected(tmp_path):
    path, doc = problem(tmp_path, replacement=Circuit(1).x(0), wires=[4])
    result = prove(path, doc)
    assert result["status"] == "not_proved"
    assert result["applicable_plan"] is None
    assert 4 in result["support"]["local_to_global"]
    assert result["composition"]["global_counterexample"] is None
    assert result["composition"]["witness_scope"] == "reduced_obligation_only"


@pytest.mark.sat
@pytest.mark.parametrize("domain", [Const(False), And(Var("x.7"), Not(Var("x.7")))])
def test_empty_domain_including_an_omitted_variable_is_refused(tmp_path, domain):
    path, doc = problem(tmp_path, raw=b"X q7\nCX q0 q1\n", span=(1, 2),
                        replacement=Circuit(2).cx(0, 1), wires=[0, 1],
                        contract={"initial_assumption": expression_to_dict(domain)})
    result = prove(path, doc)
    assert result["status"] == "precondition_failed"
    assert result["applicable_plan"] is None
    assert next(o for o in result["reduced"]["proof"]["obligations"]
                if o["name"] == "domain")["status"] == "failed"


@pytest.mark.sat
def test_unwritten_predecessors_are_arbitrary_and_restoration_is_separate(tmp_path):
    path, doc = problem(tmp_path, raw=b"CX q0 q1\n", span=(0, 1),
                        replacement=Circuit(1), wires=[1], contract={"clean_at_cut": [0]})
    assert prove(path, doc)["status"] == "precondition_failed"
    doc["contract"] = {"initial_constants": [[0, 0]], "clean_at_cut": [0]}
    assert prove(path, doc)["status"] == "equivalent"
    # Equal blocks can both fail their declared borrowed-bit restoration.
    path, doc = problem(tmp_path, raw=b"X q0\n", span=(0, 1),
                        replacement=Circuit(1).x(0), wires=[0],
                        contract={"restored_at_cut": [0]})
    assert prove(path, doc)["status"] == "not_proved"


@pytest.mark.sat
def test_seeded_complete_circuits_against_independent_exhaustive_oracle(tmp_path):
    rng = random.Random(20261108)
    for case in range(20):
        width = 3 + case % 4
        operations = []
        for _ in range(10):
            arity = rng.randint(1, 3)
            operations.append(({1: "x", 2: "cx", 3: "ccx"}[arity],
                               tuple(rng.sample(range(width), arity))))
        g = ("ccx", tuple(rng.sample(range(width), 3)))
        complete = operations[:5] + [g, g] + operations[5:]
        raw = "".join(name.upper() + " " + " ".join(f"q{q}" for q in wires) + "\n"
                      for name, wires in complete).encode()
        path, doc = problem(tmp_path, raw=raw, span=(5, 7), replacement=Circuit(1),
                            wires=[0], contract={})
        result = prove(path, doc)
        assert result["status"] == "equivalent"
        for value in range(1 << width):
            assert scalar(complete, width, value) == scalar(operations, width, value)


@pytest.mark.sat
def test_every_receipt_link_and_unknown_field_is_reverified(tmp_path):
    path, doc = problem(tmp_path)
    receipt = prove(path, doc)
    mutations = [
        lambda d: d.update(status="not_proved"),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(verified=True),
        lambda d: d["support"]["local_to_global"].reverse(),
        lambda d: d["dependencies"].update(python="forged"),
        lambda d: d["extractions"]["origin_cone"].update(dependencies=[]),
        lambda d: d["extractions"]["window"].update(op_span=[0, 1]),
        lambda d: d["applicable_plan"].update(global_op_span=[0, 1]),
        lambda d: d["reduced"]["contract"].update(initial_assumption=None),
        lambda d: d["composition"].update(external_preparation_proved=True),
    ]
    for mutate in mutations:
        mutant = copy.deepcopy(receipt)
        mutate(mutant)
        with pytest.raises(ReceiptMismatch):
            api.replay_indexed_substitution(path, doc, mutant, **pins(doc))
    for key, value in [("op_span", [2, 3]), ("replacement_wires", [0]),
                       ("contract", {}), ("replacement", Circuit(1).x(0).to_dict())]:
        mutant = copy.deepcopy(doc)
        mutant[key] = value
        with pytest.raises(ReceiptMismatch, match="request"):
            api.prove_indexed_substitution(path, mutant, **pins(doc))
    path.write_bytes(path.read_bytes() + b"X q4\n")
    with pytest.raises(ValueError, match="SHA-256"):
        api.replay_indexed_substitution(path, doc, receipt, **pins(doc))


@pytest.mark.sat
def test_context_change_outside_window_changes_source_identity(tmp_path):
    path, doc = problem(tmp_path)
    receipt = prove(path, doc)
    path.write_bytes(path.read_bytes().replace(b"X q0\n", b"X q1\n"))
    with pytest.raises(ValueError, match="SHA-256"):
        prove(path, doc)
    doc["source_file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Even a semantically valid NEW proof cannot validate the old report.
    assert prove(path, doc)["status"] == "equivalent"
    with pytest.raises(ReceiptMismatch):
        api.replay_indexed_substitution(path, doc, receipt, **pins(doc))


@pytest.mark.parametrize("raw", [b"H q5\nCX q0 q1\n", b"CX q0 q1\nR q5\n",
                                 b"CX q0 q1\nHMR q5 b0\n"])
def test_unsupported_entire_source_even_outside_selected_window(tmp_path, raw):
    path, doc = problem(tmp_path, raw=raw, span=(0, 1), contract={})
    result = prove(path, doc)
    assert result["status"] == "unsupported" and result["applicable_plan"] is None


def test_no_intermediate_cut_or_nonclassical_replacement(tmp_path):
    path, doc = problem(tmp_path)
    doc["prefix_start_op"] = 1
    assert prove(path, doc)["status"] == "unsupported"
    doc["prefix_start_op"] = 0
    doc["replacement"] = Circuit(4).mcx(0, 1, 2, 3).to_dict()
    doc["replacement_wires"] = [0, 1, 2, 3]
    assert prove(path, doc)["status"] == "unsupported"


def test_limits_schema_duplicates_and_noncanonical_names(tmp_path):
    path, doc = problem(tmp_path)
    for field, value in [("schema_version", True), ("surprise", 1),
                         ("replacement_wires", [True]), ("op_span", [0, True])]:
        mutant = copy.deepcopy(doc)
        mutant[field] = value
        with pytest.raises((ValueError, TypeError)):
            prove(path, mutant)
    raw = json.dumps(doc).replace('"prefix_start_op": 0',
                                  '"prefix_start_op": 0, "prefix_start_op": 0').encode()
    with pytest.raises(ValueError, match="duplicate"):
        api.prove_indexed_substitution(path, raw, **pins(doc))
    for name in ("x.01", "x.9", "u.0"):
        doc["contract"] = {"initial_assumption": expression_to_dict(Var(name))}
        with pytest.raises(ValueError, match="canonical"):
            prove(path, doc)


@pytest.mark.sat
def test_all_stages_and_replay_share_the_same_deadline(tmp_path, monkeypatch):
    path, doc = problem(tmp_path)
    receipt = prove(path, doc)
    expired = Budget(absolute_deadline=0)
    assert prove(path, doc, budget=expired)["applicable_plan"] is None
    assert api.replay_indexed_substitution(path, doc, receipt, **pins(doc),
                                           budget=expired)["status"] == "inconclusive"
    original = api.check_substitution
    deadlines = []

    def delayed(*args, **kwargs):
        deadlines.append(kwargs["budget"].absolute_deadline)
        proof = original(*args, **kwargs)
        # Deterministic clock advance: completed inner proof cannot escape expiry.
        monkeypatch.setattr("symq.resources.time.perf_counter", lambda: deadlines[-1] + 1)
        return proof

    monkeypatch.setattr(api, "check_substitution", delayed)
    result = prove(path, doc, budget=Budget(max_seconds=10))
    assert deadlines[0] is not None
    assert result["status"] == "inconclusive" and result["applicable_plan"] is None


@pytest.mark.sat
def test_owned_index_reuse_and_bounded_queries(tmp_path):
    path, doc = problem(tmp_path)
    with build_kmx_index(path, expected_source_sha256=doc["source_file_sha256"]) as index:
        path.unlink()
        assert api.check_indexed_substitution(index, doc, **pins(doc))["status"] == "equivalent"
        for kwargs in (
            {"limits": replace(api.CompositionLimits(), max_support_wires=2)},
            {"query_limits": replace(QueryLimits(), max_sql_queries=1)},
            {"limits": replace(api.CompositionLimits(), max_request_bytes=10)},
        ):
            result = api.check_indexed_substitution(index, doc, **pins(doc), **kwargs)
            assert result["status"] == "inconclusive" and result["applicable_plan"] is None
        with pytest.raises(ValueError, match="time"):
            api.check_indexed_substitution(index, doc, **pins(doc), budget=Budget(max_nodes=1))
    path.write_bytes(b"CX q0 q1\n")
    doc["source_file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert prove(path, doc, index_limits=replace(IndexLimits(), max_source_bytes=1))[
        "status"] == "inconclusive"
