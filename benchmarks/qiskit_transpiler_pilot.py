"""Reproducible optional Qiskit 2.6.1 transpilation into SymQ's reversible grammar.

Unlike the earlier externally *generated* Veri-Q benchmark seed, this module
runs an actual public third-party compiler/transpiler. It does not import
Qiskit until called and is only exercised in a separately qualified CI job.

Upstream Qiskit: https://github.com/Qiskit/qiskit/releases/tag/2.6.1
Apache-2.0, copyright IBM and contributors. Not a SymQ runtime dependency.
"""
from __future__ import annotations

import hashlib

from symq import Circuit
from symq.qasm import parse_qasm

PINNED_QISKIT = "2.6.1"


def transpiled_cases():
    """Return real transpiler output, an independent candidate, and QASM identity.

    We deliberately use optimization_level=0 to retain a nontrivial lowered
    stream. The candidate is derived algebraically by SymQ's test author,
    not presented as the output of Qiskit's optimizer or as a cost benchmark.
    """
    import qiskit
    from qiskit import QuantumCircuit, qasm2, transpile

    if qiskit.__version__ != PINNED_QISKIT:
        raise RuntimeError(f"expected Qiskit {PINNED_QISKIT}, got {qiskit.__version__}")

    first = QuantumCircuit(3)
    first.swap(0, 1)
    first.cx(0, 2)
    first.swap(0, 1)
    second = QuantumCircuit(3)
    second.swap(0, 1)
    second.swap(0, 1)
    second.ccx(0, 1, 2)

    cases = [
        ("conjugated_swap_cx", first, Circuit(3).cx(1, 2)),
        ("double_swap_ccx", second, Circuit(3).ccx(0, 1, 2)),
    ]
    for label, original, candidate in cases:
        lowered = transpile(
            original, basis_gates=["x", "cx", "ccx"],
            optimization_level=0, seed_transpiler=20261103,
        )
        if lowered.num_qubits != 3 or float(lowered.global_phase) != 0.0:
            raise ValueError("transpiler changed qubit width or introduced global phase")
        index = {wire: i for i, wire in enumerate(lowered.qubits)}
        qasm = qasm2.dumps(lowered)
        from_qasm = parse_qasm(qasm)
        direct = Circuit(3)
        for instruction in lowered.data:
            kind = instruction.operation.name
            if kind not in {"x", "cx", "ccx"}:
                raise ValueError(f"unqualified emitted compiler operation: {kind}")
            direct.append(kind, *(index[q] for q in instruction.qubits))
        if direct.gates != from_qasm.gates:
            raise ValueError("OpenQASM export and in-memory lowering disagree")
        if len(from_qasm.gates) <= len(candidate.gates):
            raise ValueError("chosen compiler fixture has no measurable gate saving")
        yield {
            "name": label, "source": from_qasm, "candidate": candidate,
            "qasm_sha256": hashlib.sha256(qasm.encode("utf-8")).hexdigest(),
            "qasm": qasm, "qiskit_version": PINNED_QISKIT,
            "original_gates": len(from_qasm.gates),
            "candidate_gates": len(candidate.gates),
        }


if __name__ == "__main__":
    import json

    for example in transpiled_cases():
        print(json.dumps({
            "name": example["name"],
            "qiskit_version": example["qiskit_version"],
            "qasm_sha256": example["qasm_sha256"],
            "original_gates": example["original_gates"],
            "candidate_gates": example["candidate_gates"],
            "source": "Qiskit transpile optimization_level=0 basis=x,cx,ccx",
            "provenance": "https://github.com/Qiskit/qiskit/releases/tag/2.6.1",
            "license": "Apache-2.0",
        }, sort_keys=True))
