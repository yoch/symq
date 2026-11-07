"""An original-input predicate survives learning, preparation, proof and replay."""
from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from symq import Circuit
from symq.__main__ import main
from symq.experimental.domains import expression_to_dict
from symq.labs.contextual_substitution import (
    SubstitutionContract,
    check_substitution,
    replay_substitution,
)
from symq.labs.cut_invariants import discover_cut_invariants, replay_cut_invariants
from symq.labs.rewrite import ReceiptMismatch, Weights
from symq.labs.rewrite_engine import recommend_rewrite_engine
from symq.labs.rewrite_prepare import prepare_local_classical
from symq.labs.rewrite_request import (
    RewriteRequest,
    load_request,
    replay_report,
    replayed_candidate,
    request_from_dict,
    request_to_dict,
    run_request,
)
from symq.resources import Budget
from symq.sat.assumptions import And, Const, Eq, Not, Var, Xor


def _scalar(circuit: Circuit, value: int) -> int:
    """Small bit-list oracle, independent of Circuit.run and the SAT encoding."""
    bits = [(value >> q) & 1 for q in range(circuit.width)]
    for gate in circuit.gates:
        controls, target = gate.qubits[:-1], gate.qubits[-1]
        if all(bits[q] for q in controls):
            bits[target] ^= 1
    return sum(bit << q for q, bit in enumerate(bits))


def _problem():
    # x1 = x2 is an INPUT relation. After the prefix, u2 = u0 XOR u1.
    # Target q3 is arbitrary, including dirty accumulation inputs.
    source = Circuit(4).cx(0, 2).cx(2, 3).cx(1, 0)
    replacement = Circuit(4).cx(0, 3).cx(1, 3)
    contract = SubstitutionContract(
        restored_at_cut=(0, 1, 2),
        cut_assumption=Eq(Var("u.2"), Xor(Var("u.0"), Var("u.1"))),
        initial_assumption=Eq(Var("x.1"), Var("x.2")),
    )
    return source, replacement, contract


def _request(contract=None):
    source, replacement, default = _problem()
    return RewriteRequest(
        "classical", source, replacement, (1, 2),
        default if contract is None else contract, Weights(), engine="auto",
    )


def test_original_four_positional_fields_and_legacy_wire_format_are_unchanged():
    predicate = Not(Var("u.2"))
    legacy = SubstitutionContract(((2, 0),), (2,), (0,), predicate)
    assert legacy.initial_assumption is None
    expected = {
        "initial_constants": [[2, 0]], "clean_at_cut": [2], "restored_at_cut": [0],
        "cut_assumption": {"kind": "not", "operand": {"kind": "var", "name": "u.2"}},
        "theorem": "classical_contextual_full",
    }
    assert legacy.document() == expected
    doc = request_to_dict(_request(legacy))
    assert doc["contract"] == {key: value for key, value in expected.items() if key != "theorem"}
    assert request_from_dict(doc).contract == legacy
    # Null is accepted at file/API input, but the recorded legacy form omits it.
    doc["contract"]["initial_assumption"] = None
    assert "initial_assumption" not in request_to_dict(request_from_dict(doc))["contract"]


@pytest.mark.sat
def test_correlated_input_domain_proves_the_actual_site_and_arbitrary_targets():
    source, replacement, contract = _problem()
    proof = check_substitution(source, (1, 2), replacement, contract=contract)
    assert proof.equivalent and proof.candidate is not None
    assert all(item.status == "passed" for item in proof.obligations)
    candidate = proof.candidate.circuit()
    legal = illegal_differences = 0
    for value in range(16):
        same_inputs = ((value >> 1) & 1) == ((value >> 2) & 1)
        equal = _scalar(source, value) == _scalar(candidate, value)
        if same_inputs:
            legal += 1
            assert equal
        else:
            illegal_differences += not equal
    assert legal == 8 and illegal_differences == 8
    assert replay_substitution(proof, source, (1, 2), replacement, contract=contract).equivalent


@pytest.mark.sat
def test_learned_relational_domain_is_carried_to_the_substitution_checker():
    source, replacement, contract = _problem()
    prefix = Circuit(4, source.gates[:1])
    learned = discover_cut_invariants(prefix, assumption=contract.initial_assumption)
    assert learned.proved
    fresh = replay_cut_invariants(
        prefix, learned.to_dict(), assumption=contract.initial_assumption,
        dictionary=learned.dictionary,
    )
    linked = replace(contract, cut_assumption=fresh.cut_assumption(prefix))
    proved = check_substitution(source, (1, 2), replacement, contract=linked)
    assert proved.equivalent
    # A proved relation from a restricted learner is not valid on a wider domain.
    refused = check_substitution(
        source, (1, 2), replacement, contract=replace(linked, initial_assumption=None),
    )
    assert refused.outcome == "precondition_failed" and refused.candidate is None
    assert any(item.name == "prefix" and item.status == "failed" for item in refused.obligations)


@pytest.mark.sat
def test_constants_and_relational_predicate_are_conjoined_not_alternatives():
    source, _replacement, contract = _problem()
    contract = replace(
        contract, initial_constants=((1, 0),),
        cut_assumption=Eq(Var("u.2"), Var("u.0")),
    )
    replacement = Circuit(4).cx(0, 3)
    proof = check_substitution(source, (1, 2), replacement, contract=contract)
    assert proof.equivalent
    for value in (0, 1, 8, 9):  # q1=q2=0; q0 and the accumulation target are free.
        assert _scalar(source, value) == _scalar(proof.candidate.circuit(), value)
    for relaxed in (replace(contract, initial_constants=()),
                    replace(contract, initial_assumption=None)):
        result = check_substitution(source, (1, 2), replacement, contract=relaxed)
        assert result.outcome == "precondition_failed" and result.candidate is None


@pytest.mark.sat
@pytest.mark.parametrize("initial,constants", [
    (Const(False), ()),
    (Not(Var("x.0")), ((0, 1),)),
    (And(Eq(Var("x.0"), Var("x.1")), Xor(Var("x.0"), Var("x.1"))), ()),
])
def test_an_empty_combined_domain_never_authorizes_a_vacuous_rewrite(initial, constants):
    source, replacement, contract = _problem()
    contract = replace(contract, initial_assumption=initial, initial_constants=constants)
    result = check_substitution(source, (1, 2), replacement, contract=contract)
    assert result.outcome == "precondition_failed"
    assert not result.certified and result.candidate is None
    assert [(item.name, item.status) for item in result.obligations] == [("domain", "failed")]


@pytest.mark.sat
def test_an_input_predicate_is_not_reused_as_an_unproved_cut_predicate():
    source, replacement, contract = _problem()
    no_cut = check_substitution(
        source, (1, 2), replacement, contract=replace(contract, cut_assumption=None),
    )
    assert no_cut.outcome == "not_proved" and no_cut.candidate is None
    # This local failure need not be reachable; never label it global inequivalence.
    assert not no_cut.different
    changed_prefix = Circuit(4).x(2).cx(2, 3).cx(1, 0)
    wrong_site = check_substitution(changed_prefix, (1, 2), replacement, contract=contract)
    assert wrong_site.outcome == "precondition_failed" and wrong_site.candidate is None


@pytest.mark.sat
def test_general_input_predicate_does_not_discharge_borrowed_restoration():
    # These blocks are equal, but each overwrites borrowed q1 on a legal input.
    source = Circuit(3).cx(0, 1)
    contract = SubstitutionContract(
        initial_assumption=Eq(Var("x.0"), Var("x.2")), restored_at_cut=(1,),
    )
    result = check_substitution(source, (0, 1), source, contract=contract)
    assert result.outcome == "not_proved" and result.candidate is None
    assert any(item.name == "restore_original" and item.status == "failed"
               for item in result.obligations)


def test_nonempty_domain_contract_forces_sat_even_for_linear_blocks():
    source, replacement, contract = _problem()
    assert recommend_rewrite_engine(source, (1, 2), replacement, contract).engine == "sat"
    with pytest.raises(ValueError, match="contract must be empty"):
        check_substitution(source, (1, 2), replacement, contract=contract, engine="linear")
    for engine in ("linear", "packed", "zdd"):
        doc = request_to_dict(_request())
        doc["engine"] = engine
        with pytest.raises(ValueError, match="empty input/cut/restoration contract"):
            request_from_dict(doc)


@pytest.mark.parametrize("invalid", [Var("u.0"), Var("x.4"), object()])
def test_input_predicate_uses_only_declared_original_input_wires(invalid):
    source, replacement, contract = _problem()
    with pytest.raises((TypeError, ValueError)):
        check_substitution(
            source, (1, 2), replacement, contract=replace(contract, initial_assumption=invalid),
        )


@pytest.mark.parametrize("invalid", [
    True,
    {"kind": "const", "value": 1},
    {"kind": "var", "name": 0},
    {"kind": "or", "left": {}, "right": {}},
    {"kind": "var", "name": "x.0", "assume_proved": True},
])
def test_closed_input_predicate_json_refuses_malformed_or_unknown_fields(invalid):
    doc = request_to_dict(_request())
    doc["contract"]["initial_assumption"] = invalid
    with pytest.raises((TypeError, ValueError)):
        request_from_dict(doc)


def test_initial_predicate_keeps_the_existing_expression_depth_bound():
    source, replacement, contract = _problem()
    initial = Var("x.0")
    for _ in range(24):
        initial = Not(initial)
    with pytest.raises(ValueError, match="depth"):
        check_substitution(
            source, (1, 2), replacement, contract=replace(contract, initial_assumption=initial),
        )


@pytest.mark.sat
def test_report_replay_binds_the_exact_initial_domain_even_when_a_new_domain_is_valid():
    request = _request()
    report = run_request(request)
    assert report["application"] == "applied"
    assert report["result"]["engine"] == "sat"
    assert report["schema_version"] == 2
    assert replay_report(report)["replay"]["reverified"]
    original = request.contract.initial_assumption
    for changed in (None, Const(True), Not(original), And(original, Not(Var("x.3")))):
        edited = copy.deepcopy(report)
        if changed is None:
            del edited["request"]["contract"]["initial_assumption"]
        else:
            edited["request"]["contract"]["initial_assumption"] = expression_to_dict(changed)
        fresh = run_request(request_from_dict(edited["request"]))
        assert fresh["result"]["contract_sha256"] != report["result"]["contract_sha256"]
        if type(changed) is And:
            assert fresh["result"]["outcome"] == "equivalent"
        with pytest.raises(ReceiptMismatch):
            replay_report(edited)


@pytest.mark.sat
def test_timeout_under_a_relational_domain_is_inconclusive_without_a_candidate():
    request = _request()
    timeout = run_request(request, Budget(max_seconds=1e-9))
    assert timeout["result"]["outcome"] == "inconclusive"
    assert timeout["candidate"] is None and timeout["application"] == "not_proved"
    report = run_request(request)
    replay = replay_report(report, Budget(max_seconds=1e-9))
    assert not replay["replay"]["reverified"]
    assert replay["candidate"] is None


@pytest.mark.sat
@pytest.mark.parametrize("isolate", [False, True])
def test_prepare_rewrite_cli_preserves_the_global_domain_through_standalone_replay(
        tmp_path, capsys, isolate):
    # The local [0,1,2] maps to global [4,1,6]. The input predicate is GLOBAL.
    local = Circuit(3).cx(0, 2).cx(1, 2).cx(0, 2)
    source = Circuit(7).cx(4, 1).cx(4, 6).cx(1, 6).cx(4, 6).cx(6, 5)
    contract = SubstitutionContract(
        clean_at_cut=(1,), restored_at_cut=(4,),
        initial_assumption=Eq(Var("x.1"), Var("x.4")),
    )
    plan = prepare_local_classical(
        source, local, Circuit(3), contract=contract, engine="auto",
    )
    assert plan.ready and not plan.to_dict()["proved"]
    assert plan.request.contract == contract
    inputs = {
        "source.json": source.to_dict(), "original.json": local.to_dict(),
        "candidate.json": Circuit(3).to_dict(),
        "contract.json": {k: v for k, v in contract.document().items() if k != "theorem"},
    }
    for name, doc in inputs.items():
        (tmp_path / name).write_text(json.dumps(doc))
    prepared = tmp_path / "prepared"
    assert main([
        "prepare-rewrite", str(tmp_path / "source.json"), str(tmp_path / "original.json"),
        str(tmp_path / "candidate.json"), "--contract", str(tmp_path / "contract.json"),
        "--output-dir", str(prepared), "--engine", "auto",
    ]) == 0
    preparation = json.loads(capsys.readouterr().out)
    assert preparation["location"]["matches"][0]["wires"] == [4, 1, 6]
    assert preparation["proved"] is False and preparation["candidate_authorized"] is False
    loaded, _files = load_request(prepared / "request.json")
    assert loaded.contract.initial_assumption == contract.initial_assumption
    report_path = tmp_path / "proof.json"
    args = ["rewrite", str(prepared / "request.json"), "--report", str(report_path)]
    assert main(args + (["--isolate"] if isolate else [])) == 0
    assert json.loads(capsys.readouterr().out)["result"]["engine"] == "sat"
    report = json.loads(report_path.read_text())
    candidate = replayed_candidate(report)
    assert candidate is not None
    for value in range(1 << 7):
        equal = _scalar(source, value) == _scalar(candidate, value)
        assert equal == (((value >> 1) & 1) == ((value >> 4) & 1))
    for name in inputs:
        (tmp_path / name).unlink()
    for name in ("source.json", "replacement.json", "request.json"):
        (prepared / name).unlink()
    assert main(["replay", str(report_path)]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["replay"]["reverified"] is True
    assert report["request"]["contract"]["initial_assumption"] == expression_to_dict(
        contract.initial_assumption,
    )
