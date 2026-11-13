"""Unconditional local lemmas retain source identity and exact-window guards."""
from __future__ import annotations

import copy
import hashlib
from dataclasses import replace

import pytest
from test_indexed_substitution import pins, problem, prove, scalar
from test_kmb_window import _packets

from symq import Circuit
from symq.experimental.domains import expression_to_dict
from symq.labs import indexed_substitution as api
from symq.labs.kmx_source_index import IndexLimits, KmxSourceIndex, QueryLimits, build_kmx_index
from symq.labs.rewrite import ReceiptMismatch
from symq.resources import Budget
from symq.sat.assumptions import Const


@pytest.mark.parametrize("extension", ["kmx", "kmb"])
def test_long_prefix_needs_only_the_verified_local_window(tmp_path, extension):
    count = 20_100
    raw = (b"X q5\n" * (count + 2) if extension == "kmx" else
           _packets(*[(0x11, (5,), None, None)] * (count + 2)))
    path, doc = problem(tmp_path, raw=raw, span=(count, count + 2),
                        wires=[3], contract={})
    path = path.rename(path.with_suffix("." + extension))
    result = prove(path, doc, query_limits=replace(QueryLimits(), max_selected_ops=2))
    assert result["status"] == "equivalent"
    assert result["extractions"]["origin_cone"] is None
    assert result["extractions"]["window"]["gate_indices"] == [count, count + 1]
    assert result["support"]["local_to_global"] == [3, 5]
    assert result["support"]["observed_cut_wires"] == []
    assert result["reduced"]["scope"] == "complete_window_only_unconditional"
    assert result["reduced"]["local_span"] == [0, 2]
    assert result["reduced"]["proof"]["theorem"] == "classical_total"
    assert result["complete_candidate"] is result["global_cost"] is None
    assert api.replay_indexed_substitution(
        path, doc, result, **pins(doc),
        query_limits=replace(QueryLimits(), max_selected_ops=2)) == result
    # A real change on a replacement-only wire is still observed by the proof.
    doc["replacement"] = Circuit(1).x(0).to_dict()
    rejected = prove(path, doc, query_limits=replace(QueryLimits(), max_selected_ops=2))
    assert rejected["status"] == "not_proved"
    assert rejected["applicable_plan"] is None


@pytest.mark.parametrize(("operations", "engine"), [
    ([("x", (4,))] * 2, "linear"),
    ([("ccx", (1, 3, 4))] * 2, "packed"),
    ([("ccx", (0, 1, 2)), ("ccx", (2, 3, 4)),
      ("ccx", (2, 3, 4)), ("ccx", (0, 1, 2))], "zdd"),
])
def test_total_backend_paths_match_independent_complete_circuit_oracle(
        tmp_path, operations, engine):
    prefix = [("cx", (0, 4)), ("x", (3,))]
    suffix = [("ccx", (0, 3, 4)), ("x", (1,))]
    complete = prefix + operations + suffix
    raw = "".join(name.upper() + " " + " ".join(f"q{q}" for q in wires) + "\n"
                  for name, wires in complete).encode()
    path, doc = problem(tmp_path, raw=raw, span=(2, 2 + len(operations)),
                        replacement=Circuit(1), wires=[0], contract={})
    proof = prove(path, doc)
    assert proof["status"] == "equivalent"
    assert proof["reduced"]["proof"]["engine"] == engine
    for value in range(32):
        assert scalar(complete, 5, value) == scalar(prefix + suffix, 5, value)


@pytest.mark.parametrize("contract", [
    {"initial_constants": [[5, 0]]}, {"clean_at_cut": [5]}, {"restored_at_cut": [5]},
    *[{name: expression_to_dict(Const(bit))}
      for name in ("initial_assumption", "cut_assumption") for bit in (False, True)],
])
def test_any_nonempty_contract_retains_bounded_prefix_obligations(tmp_path, contract):
    path, doc = problem(tmp_path, raw=b"X q5\n" * 6, span=(4, 6), wires=[5],
                        contract=contract)
    result = prove(path, doc, query_limits=replace(QueryLimits(), max_selected_ops=2))
    assert result["status"] == "inconclusive"
    assert "selected operations" in result["reason"]
    assert result["applicable_plan"] is None


@pytest.mark.sat
@pytest.mark.parametrize("name", ["initial_assumption", "cut_assumption"])
def test_constant_false_predicate_never_becomes_an_unconditional_proof(tmp_path, name):
    path, doc = problem(tmp_path, raw=b"X q0\nX q0\n", span=(0, 2), wires=[0],
                        contract={name: expression_to_dict(Const(False))})
    result = prove(path, doc)
    assert result["status"] == "precondition_failed"
    assert result["applicable_plan"] is None
    assert result["extractions"]["origin_cone"] is not None


def test_fast_path_keeps_query_source_support_and_time_limits(tmp_path):
    path, doc = problem(tmp_path, raw=b"X q5\n" * 4, span=(2, 4), wires=[3], contract={})
    cases = [
        {"query_limits": replace(QueryLimits(), max_selected_ops=1)},
        {"query_limits": replace(QueryLimits(), max_read_bytes=1)},
        {"limits": replace(api.CompositionLimits(), max_support_wires=1)},
        {"limits": replace(api.CompositionLimits(), max_request_bytes=1)},
        {"index_limits": replace(IndexLimits(), max_source_bytes=1)},
        {"budget": Budget(absolute_deadline=0)},
    ]
    for kwargs in cases:
        result = prove(path, doc, **kwargs)
        assert result["status"] == "inconclusive", kwargs
        assert result["applicable_plan"] is None


@pytest.mark.parametrize("field", ["gate_indices", "global_wires", "program"])
def test_fast_path_rechecks_every_window_field(tmp_path, monkeypatch, field):
    path, doc = problem(tmp_path, raw=b"X q1\nX q5\nX q5\n", span=(1, 3),
                        wires=[5], contract={})
    original = KmxSourceIndex.window
    calls = 0

    def corrupt_first_window(self, **kwargs):
        nonlocal calls
        result = original(self, **kwargs)
        calls += 1
        if calls == 1:
            result[field] = {"width": 1, "gates": []} if field == "program" else [1]
        return result

    monkeypatch.setattr(KmxSourceIndex, "window", corrupt_first_window)
    with pytest.raises(ValueError, match="selection receipt"):
        prove(path, doc)
    assert calls == 2


def test_unconditional_receipts_pin_the_omitted_context_and_request(tmp_path):
    raw = b"X q1\nX q5\nX q5\nX q3\n"
    path, doc = problem(tmp_path, raw=raw, span=(1, 3), wires=[5], contract={})
    receipt = prove(path, doc)
    with build_kmx_index(path, expected_source_sha256=doc["source_file_sha256"]) as index:
        # The owned snapshot remains authoritative, but portable replay must
        # reject changed prefix bytes even though no prefix cone was queried.
        path.write_bytes(raw.replace(b"X q1", b"X q2"))
        assert api.check_indexed_substitution(index, doc, **pins(doc)) == receipt
        with pytest.raises(ReceiptMismatch, match="index"):
            api.check_indexed_substitution(index, doc,
                **{**pins(doc), "expected_source_sha256": "0" * 64})
    with pytest.raises(ValueError, match="SHA-256"):
        api.replay_indexed_substitution(path, doc, receipt, **pins(doc))
    doc["source_file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert prove(path, doc)["status"] == "equivalent"
    with pytest.raises(ReceiptMismatch):
        api.replay_indexed_substitution(path, doc, receipt, **pins(doc))
    for key, value in [("op_span", [0, 2]), ("replacement_wires", [3]),
                       ("contract", {"restored_at_cut": [5]})]:
        changed = copy.deepcopy(doc)
        changed[key] = value
        with pytest.raises(ReceiptMismatch, match="request"):
            api.prove_indexed_substitution(path, changed, **pins(doc))


@pytest.mark.parametrize("field", ["origin_cone", "scope", "contract", "schema_version"])
def test_unconditional_receipt_scope_and_contract_are_reverified(tmp_path, field):
    path, doc = problem(tmp_path, raw=b"X q5\nX q5\n", span=(0, 2), wires=[5], contract={})
    receipt = prove(path, doc)
    if field == "origin_cone":
        receipt["extractions"][field] = {"gate_indices": []}
    elif field == "scope":
        receipt["reduced"][field] = "origin_cone_then_complete_window_only"
    elif field == "contract":
        receipt["request"][field] = {"restored_at_cut": [5]}
    else:
        receipt[field] = True
    with pytest.raises(ReceiptMismatch):
        api.replay_indexed_substitution(path, doc, receipt, **pins(doc))
