"""P2 opt-in engine policy: advice is conservative; the verifier still proves actual gates."""
from __future__ import annotations

import json

import pytest

from symq import Circuit
from symq.__main__ import main
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite import Weights
from symq.labs.rewrite_engine import quadratic_bounded, recommend_rewrite_engine
from symq.labs.rewrite_request import (
    RewriteRequest,
    replay_report,
    request_from_dict,
    request_to_dict,
    run_request,
)


def _test_request(source, span, replacement, contract=None, engine="auto"):
    return RewriteRequest(
        "classical", source, replacement, span,
        SubstitutionContract() if contract is None else contract, Weights(), False, engine,
    )


@pytest.mark.parametrize("kind,expected_engine", [
    ("affine", "linear"), ("quadratic", "packed"), ("cubic", "zdd"),
])
def test_auto_chooses_an_exact_total_checker_without_using_sat(kind, expected_engine):
    source = Circuit(5)
    if kind == "affine":
        source.cx(0, 1).cx(0, 1)
    elif kind == "quadratic":
        source.ccx(0, 1, 2).ccx(0, 1, 2)
    else:
        source.mcx(0, 1, 2, 3).mcx(0, 1, 2, 3)
    request = _test_request(source, (0, 2), Circuit(5))
    advice = recommend_rewrite_engine(source, (0, 2), Circuit(5), request.contract)
    assert advice.engine == expected_engine
    assert advice.theorem == "classical_total"
    assert advice.proof.startswith("advice_only")
    report = run_request(request)
    assert report["application"] == "applied"
    assert report["result"]["outcome"] == "equivalent"
    assert report["result"]["theorem"] == "classical_total"
    assert report["result"]["engine"] == expected_engine
    assert report["request"]["engine"] == "auto"
    assert replay_report(report)["replay"]["reverified"]
    candidate = report["candidate"]
    assert candidate["width"] == source.width
    for state in range(1 << source.width):
        assert source.run(state) == Circuit(source.width).run(state)


@pytest.mark.sat
def test_auto_never_weakens_a_real_prepared_cut_contract():
    source = Circuit(4).cx(0, 2)
    replacement = Circuit(4)
    contract = SubstitutionContract(initial_constants=((0, 0),),
                                    clean_at_cut=(0,))
    request = _test_request(source, (0, 1), replacement, contract)
    assert recommend_rewrite_engine(source, (0, 1), replacement, contract).engine == "sat"
    report = run_request(request)
    assert report["result"]["outcome"] == "equivalent"
    assert report["result"]["theorem"] == "classical_contextual_full"
    assert report["result"]["engine"] == "sat"
    assert len(report["result"]["obligations"]) >= 4
    for state in range(1 << source.width):
        if (state & 1) == 0:
            assert source.run(state) == Circuit(4).run(state)
    doc = request_to_dict(request)
    doc["engine"] = "packed"
    with pytest.raises(ValueError, match="empty input/cut/restoration"):
        request_from_dict(doc)


def test_quadratic_upper_bound_handles_nontrivial_control_flow_safely():
    assert quadratic_bounded(Circuit(4).ccx(0, 1, 2).cx(2, 3))
    assert not quadratic_bounded(Circuit(4).ccx(0, 1, 2).ccx(2, 1, 3))
    assert not quadratic_bounded(Circuit(4).mcx(0, 1, 2, 3))
    # The policy is only advice; unknown degree escalates to a general exact checker.
    source = Circuit(4).ccx(0, 1, 2).ccx(2, 1, 3)
    advice = recommend_rewrite_engine(source, (0, 2), Circuit(4), SubstitutionContract())
    assert advice.engine == "zdd"


def test_legacy_default_stays_sat_and_new_engine_is_bound_to_replay():
    source = Circuit(3).cx(0, 1).cx(0, 1)
    old = _test_request(source, (0, 2), Circuit(3), engine="sat")
    modern = _test_request(source, (0, 2), Circuit(3), engine="auto")
    assert "engine" not in request_to_dict(old)
    assert request_to_dict(modern)["engine"] == "auto"
    report = run_request(modern)
    edited = json.loads(json.dumps(report))
    edited["request"]["engine"] = "sat"
    from symq.labs.rewrite import ReceiptMismatch
    with pytest.raises(ReceiptMismatch):
        replay_report(edited)


@pytest.mark.sat
def test_cli_engine_auto_is_explicit_and_replays_exactly(tmp_path, capsys):
    data = {"kind": "classical_reversible", "width": 3,
            "gates": [["ccx", [0, 1, 2]], ["ccx", [0, 1, 2]]]}
    (tmp_path / "source.json").write_text(json.dumps(data))
    (tmp_path / "replacement.json").write_text(json.dumps({
        "kind": "classical_reversible", "width": 3, "gates": [],
    }))
    request = {"schema_version": 1, "kind": "symq_rewrite_request",
               "theorem": "classical", "source": "source.json",
               "replacement": "replacement.json", "span": [0, 2],
               "contract": {}, "weights": {"by_kind": [["ccx", 20]]},
               "require_saving": True}
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request))
    output = tmp_path / "result.json"
    assert main(["rewrite", str(path), "--engine", "auto",
                 "--report", str(output)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["result"]["engine"] == "packed"
    assert status["result"]["theorem"] == "classical_total"
    report = json.loads(output.read_text())
    assert report["request"]["engine"] == "auto"
    assert main(["replay", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["replay"]["reverified"]


def test_reject_incompatible_or_unknown_engines_before_any_verification():
    source = Circuit(2).x(0)
    payload = request_to_dict(_test_request(source, (0, 1), Circuit(2)))
    payload["engine"] = "maybe_faster"
    with pytest.raises(ValueError, match="classical engine"):
        request_from_dict(payload)
    payload["engine"] = 7
    with pytest.raises(ValueError, match="engine must be a string"):
        request_from_dict(payload)


def _random_circuit(rng, width: int, length: int) -> Circuit:
    circuit = Circuit(width)
    for _ in range(length):
        kind = rng.choice(("x", "cx", "ccx"))
        getattr(circuit, kind)(*rng.sample(range(width), {"x": 1, "cx": 2, "ccx": 3}[kind]))
    return circuit


def test_the_quadratic_bound_is_sound_against_the_exact_degree_of_every_prefix():
    """Differential check: whenever the static bound accepts a circuit, every intermediate state
    has exact ANF degree <= 2 (sparse reference) and the packed engine simulates it."""
    import random

    from symq import make_algebra, simulate

    rng = random.Random(20261101)
    accepted = rejected_exactly_cubic = 0
    for _ in range(400):
        width = rng.randint(3, 6)
        circuit = _random_circuit(rng, width, rng.randint(1, 8))
        degrees = []
        reference = make_algebra("sparse", width)
        for stop in range(len(circuit.gates) + 1):
            prefix = Circuit(width, list(circuit.gates[:stop]))
            degrees.append(max(reference.to_anf(v).degree for v in simulate(prefix, reference)))
        if quadratic_bounded(circuit):
            accepted += 1
            assert max(degrees) <= 2, circuit.gates
            simulate(circuit, make_algebra("packed", width))  # never refuses a degree
        elif max(degrees) > 2:
            rejected_exactly_cubic += 1
    assert accepted > 50 and rejected_exactly_cubic > 20


def test_a_mutated_bound_that_ignores_the_target_history_is_caught():
    """Mutation: forgetting that a Toffoli target keeps its previous degree would accept this
    degree-three circuit; the real bound refuses it."""
    circuit = Circuit(4).ccx(0, 1, 2).ccx(2, 3, 0)

    def mutant(c: Circuit) -> bool:
        return all(len(g.qubits) <= 3 for g in c.gates)  # degree of controls ignored

    assert mutant(circuit) and not quadratic_bounded(circuit)


def test_the_cli_engine_choices_are_the_request_engines():
    from symq.__main__ import _parser
    from symq.labs.rewrite_request import CLASSICAL_ENGINES

    commands = next(a for a in _parser()._actions if a.dest == "command")
    engine = next(a for a in commands.choices["rewrite"]._actions if a.dest == "engine")
    assert set(engine.choices) == CLASSICAL_ENGINES
