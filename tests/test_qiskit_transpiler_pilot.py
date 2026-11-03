"""Real optional third-party Qiskit transpiler output, with independent proof/replay."""
from __future__ import annotations

import hashlib

import pytest

pytest.importorskip("qiskit")

from benchmarks.qiskit_transpiler_pilot import transpiled_cases  # noqa: E402
from symq import Circuit  # noqa: E402
from symq.labs.contextual_substitution import SubstitutionContract  # noqa: E402
from symq.labs.rewrite import Weights  # noqa: E402
from symq.labs.rewrite_prepare import prepare_local_classical  # noqa: E402
from symq.labs.rewrite_request import replay_report, run_request  # noqa: E402


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
        for x in range(1 << source.width):
            assert _independent_run(source, x) == _independent_run(rewritten, x)
        # The alternative is meaningfully different and wrong alternatives fail.
        wrong = Circuit(candidate.width)
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
