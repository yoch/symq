"""Independent and adversarial qualification for the finite-table XOR adapter."""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from symq.circuit import Circuit, Gate
from symq.errors import UnsupportedOperation
from symq.labs.table_xor_contract import (
    ReceiptMismatch,
    TableXorContract,
    check_table_xor,
    replay_table_xor,
)
from symq.resources import Budget
from symq.sat import available


def spec(**changes):
    original = {
        "width": 6, "address_wires": (0, 1), "target_wires": (2, 3),
        "clean_wires": (4,), "borrowed_wires": (5,), "table": (0, 1, 3, 2),
        "legal_addresses": (0, 1, 2), "target_values": None,
        "table_id": "synthetic-t0", "slot_id": "emission-s1", "theorem": "coherent",
    }
    original.update(changes)
    return TableXorContract(**original)


def linear():
    """Independent minimum linear realization of T=(0,1,3,2)."""
    return Circuit(6).cx(0, 2).cx(1, 2).cx(1, 3)


def selector():
    """An independently written row-minterm realization, unlike the linear one."""
    out = Circuit(6)
    out.x(1).ccx(0, 1, 2).x(1)  # a=01
    out.x(0).ccx(0, 1, 2).ccx(0, 1, 3).x(0)  # a=10
    out.ccx(0, 1, 3)  # a=11; declared illegal but still correct
    return out


def restricted_only():
    """A mutant that is correct only when the ORIGINAL input target has equal bits."""
    source = Circuit(6).cx(2, 4).cx(3, 4).cx(4, 5).cx(3, 4).cx(2, 4)
    # The source loader comes AFTER the conditional perturbation. Placing
    # the perturbation after it would check the OUTPUT encoding instead.
    source.gates.extend(linear().gates)
    return source


def pack(address, target, borrowed=0, scratch=0):
    return ((address & 1) | ((address >> 1 & 1) << 1)
            | ((target & 1) << 2) | ((target >> 1 & 1) << 3)
            | (scratch << 4) | (borrowed << 5))


def direct_oracle(initial, table):
    """Independent scalar spec, with no imports from the adapter."""
    address = (initial & 1) | (((initial >> 1) & 1) << 1)
    target = ((initial >> 2) & 1) | (((initial >> 3) & 1) << 1)
    after = target ^ table[address]
    return ((initial & ~(4 | 8)) | ((after & 1) << 2) | ((after >> 1 & 1) << 3))


def basis_states(values=(0, 1, 2, 3)):
    return [pack(a, z, d) for a in (0, 1, 2) for z in values for d in (0, 1)]


def independently_apply_gates(source, initial):
    """Separate gate-table interpreter (no Circuit.run or adapter helpers)."""
    state = initial
    for gate in source.gates:
        active = 1
        for wire in gate.qubits[:-1]:
            active &= (state >> wire) & 1
        if active:
            state ^= 1 << gate.qubits[-1]
    return state


def test_two_different_emissions_and_all_coherences():
    contract = spec()
    inputs = basis_states()
    images = [direct_oracle(x, contract.table) for x in inputs]
    for source in (linear(), selector()):
        proof = check_table_xor(source, contract, backend="exhaustive")
        assert proof.equivalent and proof.checked_states == 24
        assert proof.theorem == "coherent"
        assert all(independently_apply_gates(source, x) == y
                   for x, y in zip(inputs, images))
        # Every |x><y| maps to |T(x)><T(y)|, including x!=y:
        # a direct exact matrix-unit oracle for this permutation-only grammar.
        for i, x in enumerate(inputs):
            for j, y in enumerate(inputs):
                output = (independently_apply_gates(source, x),
                          independently_apply_gates(source, y))
                assert output == (images[i], images[j])


def test_classical_intent_does_not_invent_a_channel_label():
    result = check_table_xor(linear(), spec(theorem="classical"), backend="exhaustive")
    assert result.equivalent and result.theorem == "classical"


def test_restricted_target_is_not_an_arbitrary_dirty_target():
    candidate = restricted_only()
    restricted = check_table_xor(
        candidate, spec(target_values=(0, 3)), backend="exhaustive")
    assert restricted.equivalent and restricted.checked_states == 12
    widened = check_table_xor(candidate, spec(target_values=None), backend="exhaustive")
    assert widened.status == "different"
    assert widened.witness in basis_states()
    assert direct_oracle(widened.witness, spec().table) != candidate.run(widened.witness)


def test_clean_scratch_is_not_a_borrowed_dirty_wire():
    dependent = linear().cx(4, 2)
    permitted = check_table_xor(dependent, spec(), backend="exhaustive")
    assert permitted.equivalent
    not_clean = spec(clean_wires=(), borrowed_wires=(4, 5))
    fail = check_table_xor(dependent, not_clean, backend="exhaustive")
    assert fail.status == "different"
    assert fail.witness is not None and fail.witness & (1 << 4)


@pytest.mark.parametrize("mutant", [
    lambda p: p.x(2),  # changed table bit / extra target update
    lambda p: p.cx(0, 5),  # borrowed dirty workspace not restored
    lambda p: p.x(4),  # clean scratch not restored
    lambda p: p.cx(0, 3),  # wrong target bit
])
def test_bad_emissions_are_rejected(mutant):
    candidate = mutant(linear())
    result = check_table_xor(candidate, spec(), backend="exhaustive")
    assert result.status == "different"
    assert result.witness is not None
    assert candidate.run(result.witness) != direct_oracle(result.witness, spec().table)


def test_input_bit_order_and_legal_set_are_bound():
    source = linear()
    assert check_table_xor(source, spec(), backend="exhaustive").equivalent
    bad_order = spec(target_wires=(3, 2))
    assert check_table_xor(source, bad_order, backend="exhaustive").status == "different"
    bad_table = spec(table=(0, 1, 2, 3))
    assert check_table_xor(source, bad_table, backend="exhaustive").status == "different"
    changed_legal = spec(legal_addresses=(0, 1, 2, 3))
    # This source implements the entire table, so widening to address 3 stays
    # valid; the changed contract identity nevertheless invalidates old replay.
    assert check_table_xor(source, changed_legal, backend="exhaustive").equivalent


def test_receipt_replay_requires_independent_pins_and_fresh_check():
    contract = spec()
    source = linear()
    record = check_table_xor(source, contract, backend="exhaustive").to_dict()
    assert replay_table_xor(
        source, contract, record,
        expected_source_sha256=record["source_sha256"],
        expected_contract_sha256=record["contract_sha256"],
        backend="exhaustive").equivalent

    for modified_contract in (
        replace(contract, table_id="synthetic-t1"),
        replace(contract, slot_id="emission-s2"),
        replace(contract, table=(0, 1, 2, 2)),
        replace(contract, target_values=(0, 3)),
        replace(contract, legal_addresses=(0, 1, 2, 3)),
        replace(contract, target_wires=(3, 2)),
        replace(contract, theorem="classical"),
    ):
        with pytest.raises(ReceiptMismatch, match="changed"):
            replay_table_xor(
                source, modified_contract, record,
                expected_source_sha256=record["source_sha256"],
                expected_contract_sha256=record["contract_sha256"],
                backend="exhaustive")

    with pytest.raises(ReceiptMismatch):
        replay_table_xor(source.x(2), contract, record,
                         expected_source_sha256=record["source_sha256"],
                         expected_contract_sha256=record["contract_sha256"],
                         backend="exhaustive")

    forged = copy.deepcopy(record)
    forged["source_sha256"] = "0" * 64
    with pytest.raises(ReceiptMismatch):
        replay_table_xor(linear(), contract, forged,
                         expected_source_sha256=record["source_sha256"],
                         expected_contract_sha256=record["contract_sha256"],
                         backend="exhaustive")

    forged = check_table_xor(linear().x(2), contract, backend="exhaustive").to_dict()
    forged.update(status="equivalent", witness=None)
    with pytest.raises(ReceiptMismatch, match="fresh proof"):
        replay_table_xor(linear().x(2), contract, forged,
                         expected_source_sha256=forged["source_sha256"],
                         expected_contract_sha256=forged["contract_sha256"],
                         backend="exhaustive")

    with pytest.raises(ValueError, match="pin"):
        replay_table_xor(source, contract, record,
                         expected_source_sha256="bogus",
                         expected_contract_sha256=record["contract_sha256"],
                         backend="exhaustive")


def test_mutated_and_forged_gate_is_rejected_before_analysis():
    c = linear()
    c.gates[0] = object()
    with pytest.raises(TypeError):
        check_table_xor(c, spec(), backend="exhaustive")
    fake = object.__new__(Gate)
    object.__setattr__(fake, "name", "cx")
    object.__setattr__(fake, "qubits", (0, True))
    c = linear()
    c.gates[0] = fake
    with pytest.raises(TypeError):
        check_table_xor(c, spec(), backend="exhaustive")


def test_bad_contracts_and_strict_json():
    original = spec()
    assert TableXorContract.from_dict(original.to_dict()) == original
    with pytest.raises(ValueError, match="nonempty"):
        spec(legal_addresses=())
    with pytest.raises(ValueError, match="table"):
        spec(table=(0, 1, 3))
    with pytest.raises(ValueError, match="table rows"):
        spec(table=(0, 1, 3, 4))
    with pytest.raises(ValueError, match="partition"):
        spec(address_wires=(0, 2))
    with pytest.raises(ValueError, match="exact"):
        spec(table=(0, True, 3, 2))
    with pytest.raises(ValueError, match="target_values"):
        spec(target_values=(0, 0))
    with pytest.raises(ValueError, match="theorem"):
        spec(theorem="channel")
    with pytest.raises(ValueError, match="ordering"):
        spec(bit_order="msb_first")
    with pytest.raises(ValueError, match="distinct"):
        spec(table_id="emission-s1")
    broken = original.to_dict()
    broken["unknown"] = True
    with pytest.raises(ValueError, match="unknown"):
        TableXorContract.from_dict(broken)
    broken = original.to_dict()
    broken["target_domain"] = {"kind": "values", "values": [0, True]}
    with pytest.raises(ValueError, match="target_values"):
        TableXorContract.from_dict(broken)
    broken = original.to_dict()
    broken["schema_version"] = True
    with pytest.raises(ValueError, match="version"):
        TableXorContract.from_dict(broken)
    with pytest.raises(UnsupportedOperation):
        linear().append("hmr", 4)


def test_strict_resource_limits_fail_closed():
    contract = spec()
    source = linear()
    assert check_table_xor(source, contract, backend="exhaustive",
                           max_states=10).status == "inconclusive"
    assert check_table_xor(source, contract, backend="exhaustive",
                           budget=Budget(max_terms=10)).status == "inconclusive"
    assert check_table_xor(source, contract, backend="exhaustive",
                           budget=Budget(max_seconds=1e-12)).status == "inconclusive"
    with pytest.raises(ValueError, match="not supported"):
        check_table_xor(source, contract, budget=Budget(max_nodes=1))


@pytest.mark.sat
def test_sat_exact_contract_and_replayed_counterexample():
    assert available()
    contract = spec()
    for candidate in (linear(), selector()):
        success = check_table_xor(candidate, contract, backend="sat",
                                  budget=Budget(max_seconds=10))
        assert success.equivalent and success.sat_clauses > 0
        replay = replay_table_xor(
            candidate, contract, success.to_dict(),
            expected_source_sha256=success.source_sha256,
            expected_contract_sha256=success.contract_sha256,
            backend="sat", budget=Budget(max_seconds=10))
        assert replay.equivalent
    for candidate in (linear().x(2), linear().cx(0, 5)):
        difference = check_table_xor(candidate, contract, backend="sat",
                                     budget=Budget(max_seconds=10))
        assert difference.status == "different"
        assert difference.witness in basis_states()
        assert candidate.run(difference.witness) != direct_oracle(
            difference.witness, contract.table)


@pytest.mark.sat
def test_sat_restricted_target_and_reference_gate_cap():
    assert available()
    source = restricted_only()
    assert check_table_xor(source, spec(target_values=(0, 3)), backend="sat").equivalent
    assert check_table_xor(source, spec(), backend="sat").status == "different"
    assert check_table_xor(linear(), spec(), backend="sat",
                           budget=Budget(max_terms=1)).status == "inconclusive"


def test_replay_rejects_relabelled_backend_reason_and_counts():
    contract, source = spec(), linear()
    positive = check_table_xor(source, contract, backend="exhaustive")
    record = positive.to_dict()
    for field, altered in (
        ("reason", "unrelated PASS"),
        ("backend", "sat"),
        ("checked_states", 0),
        ("sat_clauses", 100),
    ):
        tampered = {**record, field: altered}
        with pytest.raises(ReceiptMismatch):
            replay_table_xor(
                source, contract, tampered,
                expected_source_sha256=positive.source_sha256,
                expected_contract_sha256=contract.sha256,
                backend="exhaustive")


def test_development_qualification_fails_closed_on_missing_replay(tmp_path, monkeypatch):
    import json

    from benchmarks import table_xor_contract as campaign

    source = tmp_path / "emission.json"
    contract = tmp_path / "table.json"
    source.write_text(json.dumps(linear().to_dict()))
    contract.write_text(json.dumps(spec().to_dict()))

    def fail_replay(*args, **kwargs):
        raise ReceiptMismatch("injected replay refusal")

    monkeypatch.setattr(campaign, "replay_table_xor", fail_replay)
    failed = campaign.run(source, contract, backend="exhaustive",
                          repetitions=2, max_seconds=5.0, max_states=64)
    assert not failed["qualified"]
    assert len(failed["trials"]) == 2
    assert all(row["result"]["status"] == "equivalent" and not row["qualified"]
               for row in failed["trials"])
    assert all(row["error"]["type"] == "ReceiptMismatch" for row in failed["trials"])

    monkeypatch.undo()
    successful = campaign.run(source, contract, backend="exhaustive",
                              repetitions=2, max_seconds=5.0, max_states=64)
    assert successful["qualified"]
    assert all(row["qualified"] and row["replay"]["status"] == "equivalent"
               for row in successful["trials"])
    assert all(row["result"] == row["replay"] for row in successful["trials"])


def test_replay_uses_the_callers_caps_and_does_not_mistake_a_cap_for_tampering():
    # 3 legal addresses x 4 targets x 2 borrowed values = 24 basis states.
    contract, source = spec(), linear()
    record = check_table_xor(source, contract, backend="exhaustive", max_states=24).to_dict()
    pins = {"expected_source_sha256": record["source_sha256"],
            "expected_contract_sha256": record["contract_sha256"]}
    assert replay_table_xor(source, contract, record, backend="exhaustive",
                            max_states=24, **pins).equivalent
    capped = replay_table_xor(source, contract, record, backend="exhaustive",
                              max_states=23, **pins)
    assert capped.status == "inconclusive" and not capped.equivalent
    assert "basis states" in capped.reason


def test_replay_past_deadline_is_inconclusive_not_a_mismatch():
    import time

    contract, source = spec(), linear()
    record = check_table_xor(source, contract, backend="exhaustive").to_dict()
    late = replay_table_xor(
        source, contract, record, backend="exhaustive",
        expected_source_sha256=record["source_sha256"],
        expected_contract_sha256=record["contract_sha256"],
        budget=Budget(absolute_deadline=time.perf_counter() - 1))
    assert late.status == "inconclusive" and not late.equivalent


def test_session_max_nodes_and_max_bytes_are_refused_too():
    from symq.resources import VerificationSession

    for cap in ({"max_nodes": 1}, {"max_bytes": 1}):
        with VerificationSession(Budget(**cap)), pytest.raises(ValueError, match="max_nodes"):
            check_table_xor(linear(), spec(), backend="exhaustive")


def test_qualification_forwards_max_states_and_consumer_pins(tmp_path, monkeypatch):
    import json

    from benchmarks import table_xor_contract as bench

    contract_path = tmp_path / "contract.json"
    source_path = tmp_path / "source.json"
    contract_path.write_text(json.dumps(spec().to_dict()))
    source_path.write_text(json.dumps(linear().to_dict()))
    report = bench.run(source_path, contract_path, backend="exhaustive", repetitions=1,
                       max_seconds=5.0, max_states=24)
    assert report["qualified"] and report["inputs"]["pins"]["origin"].startswith("self")
    seen = {}
    real = bench.replay_table_xor

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(bench, "replay_table_xor", spy)
    good = bench.run(source_path, contract_path, backend="exhaustive", repetitions=1,
                     max_seconds=5.0, max_states=24,
                     expected_source_sha256=report["inputs"]["source_sha256"],
                     expected_contract_sha256=report["inputs"]["contract_sha256"])
    assert good["qualified"] and good["inputs"]["pins"]["origin"] == "consumer"
    assert seen["max_states"] == 24
    wrong = bench.run(source_path, contract_path, backend="exhaustive", repetitions=1,
                      max_seconds=5.0, max_states=24, expected_source_sha256="0" * 64,
                      expected_contract_sha256=report["inputs"]["contract_sha256"])
    assert not wrong["qualified"]
    assert wrong["trials"][0]["error"]["type"] == "ReceiptMismatch"


def _independent_batch():
    import json
    from pathlib import Path

    root = Path(__file__).parent / "data" / "table_xor_qualification"
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["kind"] == "symq_table_xor_independent_batch"
    return root, manifest["cases"]


@pytest.mark.parametrize("backend", ["exhaustive", pytest.param("sat", marks=pytest.mark.sat)])
def test_independent_qualification_batch_matches_its_manifest(backend):
    """27 cases built apart from the PR fixtures; outcomes fixed by an independent oracle."""
    import json

    from symq.circuit import circuit_from_dict

    root, cases = _independent_batch()
    assert len(cases) == 27
    for case in cases:
        raw = json.loads((root / case["contract"]).read_text())
        if case["expected"] == "refused":
            with pytest.raises(ValueError):
                TableXorContract.from_dict(raw)
            continue
        contract = TableXorContract.from_dict(raw)
        source = circuit_from_dict(json.loads((root / case["source"]).read_text()))
        result = check_table_xor(source, contract, backend=backend, max_states=200_000)
        assert result.status == case["expected"], case["name"]
        if result.equivalent:
            replayed = replay_table_xor(
                source, contract, result.to_dict(), backend=backend, max_states=200_000,
                expected_source_sha256=result.source_sha256,
                expected_contract_sha256=contract.sha256)
            assert replayed.equivalent, case["name"]
