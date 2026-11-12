"""Obligation receipts name their inputs and settings, and only a replay relies on them.

A receipt records what a check was asked, of which inputs, under which settings, and what
it answered. It is not a certificate: these tests change the source, the statement and the
receipt itself, and check that a replay never confirms what the inputs do not support.
"""
from __future__ import annotations

import copy
import json
import time

import pytest

from benchmarks.anchored_kraus import chain
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.experimental.table_xor import PredicateValues
from symq.labs import obligation_receipt as module
from symq.labs.backward_ancilla import AncillaLimits
from symq.labs.obligation_receipt import (
    OBLIGATIONS,
    _body_digest,
    prove_obligation,
    replay_obligation,
)
from symq.labs.shared_table import SharedTable
from symq.resources import Budget

ENGINES = [("affine_table", "anf"), pytest.param("affine_table", "sat", marks=pytest.mark.sat),
           ("shared_table", "anf"), pytest.param("shared_table", "sat", marks=pytest.mark.sat),
           ("clean_ancilla", "pauli"), ("clean_ancilla", "shift_diagonal")]


def _affine():
    source, contract = chain(2)
    contract = dict(contract)
    del contract["target_values"]
    contract.update(kind="symq_affine_hmr_table_contract", schema_version=2,
                    target_space={"kind": "affine_image", "offset": 0, "columns": [1]})
    return source, contract


def _shared():
    table = SharedTable.from_rows([0, 0, 0, 0], address_bits=2, target_bits=1)
    contract = {"kind": "symq_shared_affine_table_contract", "schema_version": 3, "width": 3,
                "address_wires": [0, 1], "target_wires": [2], "clean_wires": [],
                "borrowed_wires": [], "table": table.to_dict(),
                "address_domain": PredicateValues.below(2, 3).to_dict(),
                "target_space": {"kind": "affine_image", "offset": 0, "columns": [1]},
                "bit_order": "lsb_first", "records": "forgotten", "outputs": "all_retained"}
    return program_to_dict(HybridProgram(3, 0)), contract


def _ancilla():
    program = HybridProgram(2, 1).ccx(0, 1, 2).ccx(0, 1, 2)
    return program_to_dict(program), {"target": 2}


def _inputs(obligation):
    return {"affine_table": _affine, "shared_table": _shared, "clean_ancilla": _ancilla}[
        obligation]()


def _break(obligation, source):
    """A source whose verdict differs: a flip on the target or on the ancilla."""
    source = copy.deepcopy(source)
    wire = 2 if obligation != "affine_table" else source["data"] - 1
    source["ops"].append({"kind": "x", "wires": [wire], "slot": None, "condition": None,
                          "source": None, "value": None})
    return source


@pytest.mark.parametrize(("obligation", "engine"), ENGINES)
def test_a_receipt_names_its_inputs_and_a_replay_confirms_it(obligation, engine):
    source, statement = _inputs(obligation)
    receipt = prove_obligation(obligation, source, statement, engine=engine)
    assert json.loads(json.dumps(receipt)) == receipt
    assert receipt["portable_certificate"] is False and "proves nothing" in receipt["authority"]
    assert receipt["verdict"]["status"] in {"equivalent", "clean"}
    assert (receipt["obligation"], receipt["engine"]) == (obligation, engine)
    assert receipt["statement"]["theorem"]
    replay = replay_obligation(receipt, source, statement)
    assert replay["status"] == "confirmed" and replay["same_version"] is True


@pytest.mark.parametrize(("obligation", "engine"), ENGINES)
def test_another_source_or_statement_is_refused_before_any_check(obligation, engine,
                                                                 monkeypatch):
    source, statement = _inputs(obligation)
    receipt = prove_obligation(obligation, source, statement, engine=engine)
    monkeypatch.setattr(module, "_run", lambda *a: pytest.fail("no check may run"))
    other = replay_obligation(receipt, _break(obligation, source), statement)
    assert (other["status"], other["reason"]) == ("mismatch", "source differs from the receipt's")
    changed = copy.deepcopy(statement)
    if obligation == "clean_ancilla":
        changed["target"] = 1
    else:
        changed["records"] = "forgotten "
    other = replay_obligation(receipt, source, changed)
    assert other["status"] == "mismatch" and "statement differs" in other["reason"]


@pytest.mark.parametrize(("obligation", "engine"), ENGINES)
def test_a_negative_verdict_is_kept_with_its_witness(obligation, engine):
    source, statement = _inputs(obligation)
    broken = _break(obligation, source)
    receipt = prove_obligation(obligation, broken, statement, engine=engine)
    assert receipt["verdict"]["status"] in {"not_proved", "not_clean"}
    assert receipt["verdict"]["witness"] is not None
    assert replay_obligation(receipt, broken, statement)["status"] == "confirmed"


def test_an_edited_receipt_is_refused_and_a_forged_one_is_refuted():
    source, statement = _ancilla()
    receipt = prove_obligation("clean_ancilla", source, statement, engine="pauli")
    edited = copy.deepcopy(receipt)
    edited["verdict"]["status"] = "not_clean"
    result = replay_obligation(edited, source, statement)
    assert result["status"] == "mismatch" and "edited" in result["reason"]
    # A forger can recompute the digest; the replay still recomputes the verdict.
    edited["receipt_sha256"] = _body_digest(edited)
    result = replay_obligation(edited, source, statement)
    assert result["status"] == "mismatch"
    assert result["verdict"]["status"] == "clean"
    assert result["reason"].startswith("the replay found clean")


def test_a_forged_failed_obligation_is_refuted():
    source, statement = _affine()
    broken = _break("affine_table", source)
    receipt = prove_obligation("affine_table", broken, statement, engine="anf")
    forged = copy.deepcopy(receipt)
    forged["verdict"]["obligation"] = "branch_phase" if receipt["verdict"]["obligation"] != \
        "branch_phase" else "outputs"
    forged["receipt_sha256"] = _body_digest(forged)
    assert replay_obligation(forged, broken, statement)["status"] == "mismatch"


def test_receipts_of_another_kind_or_version_are_refused():
    source, statement = _ancilla()
    receipt = prove_obligation("clean_ancilla", source, statement, engine="pauli")
    for change in ({"kind": "other"}, {"schema_version": 2}):
        bad = {**receipt, **change}
        bad["receipt_sha256"] = _body_digest(bad)
        assert replay_obligation(bad, source, statement)["status"] == "mismatch"
    assert replay_obligation({"kind": "symq_obligation_receipt"}, source,
                             statement)["status"] == "mismatch"
    older = {**receipt, "symq_version": "0.0.1"}
    older["receipt_sha256"] = _body_digest(older)
    replay = replay_obligation(older, source, statement)
    assert replay["status"] == "confirmed" and replay["same_version"] is False


def test_settings_are_recorded_and_replayed():
    source, statement = _ancilla()
    receipt = prove_obligation("clean_ancilla", source, statement, engine="pauli",
                               budget=Budget(max_terms=4096, max_seconds=30),
                               limits=AncillaLimits(max_products=5))
    assert receipt["verdict"]["status"] == "inconclusive"
    assert receipt["settings"]["limits"]["max_products"] == 5
    assert receipt["settings"]["budget"]["max_seconds"] == 30
    assert receipt["resources"]["resource"] == "pauli_products"
    # The replay uses the receipt's own limits, so it stops the same way.
    assert replay_obligation(receipt, source, statement)["status"] == "confirmed"
    source, statement = _affine()
    receipt = prove_obligation("affine_table", source, statement, engine="anf",
                               max_products=1, max_json_items=50_000)
    from symq.labs.obligation_receipt import _table_defaults

    # Every bound is written out, the defaults of this version included.
    assert receipt["settings"]["bounds"] == {**_table_defaults(), "max_json_items": 50_000,
                                             "max_products": 1}
    assert receipt["settings"]["bounds"]["max_seconds"] == 10.0
    assert receipt["verdict"]["status"] == "inconclusive"
    assert receipt["resources"]["limits"]["max_products"] == 1


def test_a_replay_that_decides_or_runs_out_says_so(monkeypatch):
    source, statement = _ancilla()
    real = module._run

    def stopped(*args):
        ran = real(*args)
        ran["result"] = {**ran["result"], "status": "inconclusive", "witness": None}
        return ran

    monkeypatch.setattr(module, "_run", stopped)
    receipt = prove_obligation("clean_ancilla", source, statement, engine="pauli")
    monkeypatch.setattr(module, "_run", real)
    assert replay_obligation(receipt, source, statement)["status"] == "concluded"
    decisive = prove_obligation("clean_ancilla", source, statement, engine="pauli")
    monkeypatch.setattr(module, "_run", stopped)
    assert replay_obligation(decisive, source, statement)["status"] == "inconclusive"


def test_settings_that_cannot_be_replayed_are_refused():
    source, statement = _ancilla()
    with pytest.raises(ValueError, match="absolute deadline"):
        prove_obligation("clean_ancilla", source, statement, engine="pauli",
                         budget=Budget(absolute_deadline=time.perf_counter() + 9))
    with pytest.raises(ValueError, match="unknown obligation"):
        prove_obligation("channel", source, statement, engine="pauli")
    with pytest.raises(ValueError, match="runs on"):
        prove_obligation("clean_ancilla", source, statement, engine="anf")
    with pytest.raises(ValueError, match="no other bound"):
        prove_obligation("clean_ancilla", source, statement, engine="pauli", max_products=3)
    with pytest.raises(ValueError, match="target"):
        prove_obligation("clean_ancilla", source, {"target": 2, "extra": 1}, engine="pauli")
    table_source, contract = _affine()
    with pytest.raises(ValueError, match="clean_ancilla only"):
        prove_obligation("affine_table", table_source, contract, engine="anf",
                         limits=AncillaLimits())
    with pytest.raises(TypeError):
        prove_obligation("affine_table", table_source, contract, engine="anf",
                         max_products=[1])


def test_every_obligation_has_a_test_input():
    assert set(OBLIGATIONS) == {"affine_table", "shared_table", "clean_ancilla"}
    for obligation in OBLIGATIONS:
        assert _inputs(obligation)


# --- review follow-up: what a replay compares, and what a receipt records ------------------

def _forged(receipt, **changes):
    forged = copy.deepcopy(receipt)
    for path, value in changes.items():
        target = forged
        *parents, leaf = path.split("__")
        for name in parents:
            target = target[name]
        target[leaf] = value
    forged["receipt_sha256"] = _body_digest(forged)
    return forged


@pytest.mark.parametrize("change", [
    {"portable_certificate": True},
    {"authority": "a full certificate"},
    {"statement__theorem": "channel equality, unconditional"},
    {"statement__dirty_wires": 5},
    {"checker__function": "symq.labs.other.check"},
])
def test_a_confirmed_replay_vouches_for_every_descriptive_field(change):
    source, statement = _shared()
    honest = prove_obligation("shared_table", source, statement, engine="anf")
    forged = _forged(honest, **change)
    result = replay_obligation(forged, source, statement)
    assert result["status"] == "mismatch", change
    assert "describes the check differently" in result["reason"]
    assert replay_obligation(honest, source, statement)["status"] == "confirmed"


def test_a_deterministic_witness_is_compared():
    source, statement = _ancilla()
    broken = _break("clean_ancilla", source)
    for engine in ("pauli", "shift_diagonal"):
        receipt = prove_obligation("clean_ancilla", broken, statement, engine=engine)
        forged = _forged(receipt, verdict__witness={"assignment": 3, "probability": "1"})
        result = replay_obligation(forged, broken, statement)
        assert result["status"] == "mismatch" and "witness" in result["reason"]


@pytest.mark.parametrize(("obligation", "engine"), ENGINES)
def test_the_checker_that_ran_is_recorded(obligation, engine):
    source, statement = _inputs(obligation)
    checker = prove_obligation(obligation, source, statement, engine=engine)["checker"]
    expected = {"affine_table": "symq.labs.affine_table.verify_affine_table",
                "shared_table": "symq.labs.shared_table.verify_shared_table",
                "clean_ancilla": ("symq.labs.backward_ancilla.check_clean_ancilla"
                                  if engine == "pauli" else
                                  "symq.labs.shift_diagonal_ancilla.check_shift_diagonal")}
    assert checker["function"] == expected[obligation]
    if obligation != "clean_ancilla":
        assert checker["proof_kind"].endswith(engine)


@pytest.mark.parametrize(("obligation", "engine"), ENGINES)
def test_the_budget_is_applied_and_replayed(obligation, engine):
    source, statement = _inputs(obligation)
    receipt = prove_obligation(obligation, source, statement, engine=engine,
                               budget=Budget(max_seconds=1e-9))
    assert receipt["verdict"]["status"] == "inconclusive", receipt["verdict"]
    assert receipt["settings"]["budget"]["max_seconds"] == 1e-9
    assert replay_obligation(receipt, source, statement)["status"] == "confirmed"


def test_defaults_are_written_out():
    source, statement = _shared()
    shared = prove_obligation("shared_table", source, statement, engine="anf")
    assert shared["settings"]["budget"]["max_seconds"] == 30.0
    source, statement = _ancilla()
    ancilla = prove_obligation("clean_ancilla", source, statement, engine="pauli")
    assert ancilla["settings"]["budget"]["max_terms"] == 4096
    assert ancilla["settings"]["limits"] == {f: getattr(AncillaLimits(), f) for f in
                                             ancilla["settings"]["limits"]}


def test_a_session_whose_limits_cannot_be_recorded_is_refused():
    from symq.resources import VerificationSession

    source, statement = _ancilla()
    receipt = prove_obligation("clean_ancilla", source, statement, engine="pauli")
    with VerificationSession(Budget(max_terms=1)):
        with pytest.raises(ValueError, match="VerificationSession"):
            prove_obligation("clean_ancilla", source, statement, engine="pauli")
        with pytest.raises(ValueError, match="VerificationSession"):
            replay_obligation(receipt, source, statement)


@pytest.mark.parametrize("change", [
    {"verdict": []}, {"settings": {}}, {"verdict__status": 3},
    {"settings__budget": {"absolute_deadline": 0}},
    {"settings__bounds": {"backend": "sat"}}, {"settings__bounds": {"max_terms": [1]}},
    {"engine": "pauli"}, {"obligation": "channel"},
])
def test_a_malformed_receipt_is_a_mismatch_not_an_exception(change, monkeypatch):
    source, statement = _affine()
    receipt = prove_obligation("affine_table", source, statement, engine="anf")
    monkeypatch.setattr(module, "_run", lambda *a: pytest.fail("no check may run"))
    result = replay_obligation(_forged(receipt, **change), source, statement)
    assert result["status"] == "mismatch", change


@pytest.mark.sat
def test_a_replay_without_a_solver_is_unsupported_not_a_mismatch(monkeypatch):
    from symq.errors import SatUnavailable
    from symq.labs import kraus_graph

    source, statement = _shared()
    source = _break("shared_table", source)  # a refutation needs the solver
    receipt = prove_obligation("shared_table", source, statement, engine="sat")
    assert receipt["verdict"]["status"] == "not_proved"

    def unavailable(*args, **kwargs):
        raise SatUnavailable("no solver here")

    monkeypatch.setattr(kraus_graph, "_new_solver", unavailable)
    result = replay_obligation(receipt, source, statement)
    assert result["status"] == "unsupported" and "no solver" in result["reason"]


@pytest.mark.parametrize("broken", [False, True])
def test_decisive_statuses_of_ancilla_receipts_are_compared(broken, monkeypatch):
    source, statement = _ancilla()
    if broken:
        source = _break("clean_ancilla", source)
    real = module._run

    def stopped(*args):
        ran = real(*args)
        ran["result"] = {**ran["result"], "status": "inconclusive", "witness": None,
                         "assignment": None}
        return ran

    decisive = prove_obligation("clean_ancilla", source, statement, engine="shift_diagonal")
    assert decisive["verdict"]["status"] == ("not_clean" if broken else "clean")
    monkeypatch.setattr(module, "_run", stopped)
    assert replay_obligation(decisive, source, statement)["status"] == "inconclusive"
    stuck = prove_obligation("clean_ancilla", source, statement, engine="shift_diagonal")
    monkeypatch.setattr(module, "_run", real)
    assert replay_obligation(stuck, source, statement)["status"] == "concluded"


def test_the_statement_summary_counts_legal_addresses():
    source, statement = _shared()
    assert prove_obligation("shared_table", source, statement,
                            engine="anf")["statement"]["legal_addresses"] == 3
    source, statement = _affine()
    assert prove_obligation("affine_table", source, statement,
                            engine="anf")["statement"]["legal_addresses"] == len(
                                statement["legal_addresses"])


@pytest.mark.parametrize("broken", [False, True])
def test_decisive_statuses_of_table_receipts_are_compared(broken, monkeypatch):
    source, statement = _affine()
    if broken:
        source = _break("affine_table", source)
    real = module._run

    def stopped(*args):
        ran = real(*args)
        ran["result"] = {**ran["result"], "status": "inconclusive", "witness": None,
                         "obligation": "resources"}
        return ran

    decisive = prove_obligation("affine_table", source, statement, engine="anf")
    assert decisive["verdict"]["status"] == ("not_proved" if broken else "equivalent")
    monkeypatch.setattr(module, "_run", stopped)
    assert replay_obligation(decisive, source, statement)["status"] == "inconclusive"
    stuck = prove_obligation("affine_table", source, statement, engine="anf")
    monkeypatch.setattr(module, "_run", real)
    assert replay_obligation(stuck, source, statement)["status"] == "concluded"
