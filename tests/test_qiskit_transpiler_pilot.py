"""Real optional third-party Qiskit transpiler output, with independent proof/replay."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

from benchmarks.qiskit_transpiler_pilot import transpiled_cases
from symq import Circuit
from symq.circuit import circuit_from_dict
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite import ReceiptMismatch, Weights
from symq.labs.rewrite_prepare import prepare_local_classical
from symq.labs.rewrite_request import replay_report, run_request

pytest.importorskip("qiskit")

# Pinned receipts of qiskit.qasm2.dumps(transpile(..., optimization_level=0)) under
# Qiskit 2.6.1 (CI artifacts 13263531451 and 13263981205). Comparing two runs of the
# same process with each other cannot detect a changed lowering; these constants can.
PINNED_QASM_SHA256 = {
    "conjugated_swap_cx": "312b132022e175a64561df05496cfd76a0254f010e927752bc124a23fd1d5849",
    "double_swap_ccx": "3269ab93fa5fb091804906278aff711b45d94182fc0ca47f5b8cd84a27182e4b",
}
_SWAP = [("cx", (0, 1)), ("cx", (1, 0)), ("cx", (0, 1))]
PINNED_GATES = {
    "conjugated_swap_cx": _SWAP + [("cx", (0, 2))] + _SWAP,
    "double_swap_ccx": _SWAP + _SWAP + [("ccx", (0, 1, 2))],
}
# Plausible qubit-order mistakes: the unswapped CX control, a CCX with permuted target.
WRONG_ORDER = {"conjugated_swap_cx": Circuit(3).cx(0, 2), "double_swap_ccx": Circuit(3).ccx(0, 2, 1)}


def _independent_run(circuit: Circuit, initial: int) -> int:
    bits = [(initial >> i) & 1 for i in range(circuit.width)]
    for gate in circuit.gates:
        controls, target = gate.qubits[:-1], gate.qubits[-1]
        if all(bits[wire] for wire in controls):
            bits[target] ^= 1
    return sum(bit << i for i, bit in enumerate(bits))


def _embed(local: Circuit) -> Circuit:
    full = Circuit(local.width + 2).x(0)
    for gate in local.gates:
        full.append(gate.name, *(q + 2 for q in gate.qubits))
    return full.cx(0, 1)


@pytest.mark.sat
def test_actual_qiskit_261_transpiled_sources_and_fresh_proof_replay():
    cases = list(transpiled_cases())
    assert len(cases) == 2
    for sample in cases:
        original, candidate = sample["source"], sample["candidate"]
        assert sample["qiskit_version"] == "2.6.1"
        assert sample["original_gates"] > sample["candidate_gates"]
        assert hashlib.sha256(sample["qasm"].encode()).hexdigest() == sample["qasm_sha256"]
        source = _embed(original)
        prepared = prepare_local_classical(
            source, original, candidate, contract=SubstitutionContract(),
            engine="sat", weights=Weights.from_mapping({"cx": 1, "ccx": 32}),
            require_saving=True,
        )
        assert prepared.ready and prepared.to_dict()["proved"] is False
        assert prepared.location["status"] == "unique"
        report = run_request(prepared.request)
        assert report["result"]["outcome"] == "equivalent", (sample["name"], report)
        assert report["application"] == "applied"
        assert replay_report(report)["replay"]["reverified"]
        span = prepared.request.span
        rewritten = Circuit(
            source.width,
            source.gates[:span[0]] + prepared.request.replacement.gates +
            source.gates[span[1]:],
        )
        # Check the checker-issued candidate, i.e. what a consumer would apply.
        applied = circuit_from_dict(report["candidate"])
        assert applied.gates == rewritten.gates
        for x in range(1 << source.width):
            assert _independent_run(source, x) == _independent_run(rewritten, x)
            assert _independent_run(source, x) == _independent_run(applied, x)
        # A tampered candidate in an otherwise valid report is refused by replay.
        forged = json.loads(json.dumps(report))
        forged["candidate"] = circuit_from_dict(report["candidate"]).x(0).to_dict()
        with pytest.raises(ReceiptMismatch):
            replay_report(forged)
        # The alternative is meaningfully different and wrong alternatives fail.
        for wrong in (Circuit(candidate.width), WRONG_ORDER[sample["name"]]):
            bad = prepare_local_classical(
                source, original, wrong, contract=SubstitutionContract(),
                engine="sat",
            )
            assert bad.ready
            refusal = run_request(bad.request)
            assert refusal["result"]["outcome"] != "equivalent"
            assert refusal["candidate"] is None


def test_actual_qiskit_outputs_are_deterministic_at_pinned_version():
    first = list(transpiled_cases())
    second = list(transpiled_cases())
    assert [(s["name"], s["qasm_sha256"]) for s in first] == [
        (s["name"], s["qasm_sha256"]) for s in second
    ]
    # Not SAT-marked: the pin is checked even where python-sat is absent.
    for sample in first:
        assert sample["qasm_sha256"] == PINNED_QASM_SHA256[sample["name"]]
        assert [(g.name, tuple(g.qubits)) for g in sample["source"].gates] == (
            PINNED_GATES[sample["name"]]
        )



@pytest.mark.sat
def test_paired_isolated_full_call_benchmark_emits_real_proof_receipts():
    run = subprocess.run(
        [sys.executable, "-m", "benchmarks.qiskit_rewrite_benchmark",
         "--benchmark", "--repetitions", "1"],
        capture_output=True, text=True, check=True,
    )
    records = [json.loads(line) for line in run.stdout.splitlines()]
    assert len(records) == 2
    assert {row["case"] for row in records} == {
        "conjugated_swap_cx", "double_swap_ccx",
    }
    assert {row["pair_order"] for row in records} == {0, 1}
    for row in records:
        assert row["status"] == "equivalent_replayed"
        assert row["original_gates"] == 7 and row["candidate_gates"] == 1
        assert row["startup_inclusive_wall_seconds"] >= row["inprocess_total_seconds"] > 0
        assert row["proof_seconds"] > 0 and row["replay_seconds"] > 0
        assert row["process_peak_rss_kib_linux"] > 0


def test_compiler_source_drift_is_refused_at_every_consumer_boundary(monkeypatch):
    """The generator's own pin protects callers, not only dedicated CI tests."""
    from qiskit import qasm2

    original = qasm2.dumps
    monkeypatch.setattr(qasm2, "dumps", lambda circuit: original(circuit) + "\n// drift\n")
    with pytest.raises(ValueError, match="SHA-256 drift"):
        list(transpiled_cases(only="conjugated_swap_cx"))
