"""Public-source generated compiler-rewrite pilot (research, SAT optional).

Sources:
- Veri-Q/Benchmark scripts/combinational/adder.py at
  9be108313844e30c5df5780989a68cac4d966cfe (MIT, copyright 2026 Veri-Q).
  The generator below is adapted from that public source; the MIT notice and
  exact upstream reference are in docs/evidence/compiler-handoff-pilot.md.
- DVLab-NTU/qsyn benchmark/qasm/ab+ac.qasm at
  b77187c87f0bddd69bc6c213700642ee6c423159 (Apache-2.0, 2023 DVLab NTU).
These are two different provenance families. The optimized variants below are
ours and are conditional on an explicitly stated input-domain bit. They are
not claimed to implement an independently proven high-level adder algorithm.
"""
from __future__ import annotations

import hashlib

import pytest

from symq import Circuit
from symq.qasm import parse_qasm
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite import Weights
from symq.labs.rewrite_prepare import prepare_local_classical
from symq.labs.rewrite_request import replay_report, run_request


# Adapted from publicly released Veri-Q combinational adder generator (MIT).
def _veriq_generated_adder(number: int) -> str:
    out = f"//Adder with {number} qubits input.\n"
    out += 'OPENQASM 2.0;\ninclude "qelib1.inc";\n'
    out += f"qreg q[{3 * number + 1}];\n"
    for j in range(number):
        s = 3 * j
        out += f"ccx q[{s+1}],q[{s+2}],q[{s+3}];\n"
        out += f"cx q[{s+1}],q[{s+2}];\n"
    for j in range(number):
        s = 3 * j
        out += f"ccx q[{s}],q[{s+2}],q[{s+3}];\n"
    for j in range(number):
        s = 3 * j
        out += f"cx q[{s}],q[{s+2}];\n"
    return out


_QSYN = (
    'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[6];\n\n'
    'ccx q[0], q[1], q[3];\n'
    'ccx q[0], q[2], q[4];\n'
    'x q[3];\n'
    'x q[4];\n'
    'ccx q[3], q[4], q[5];\n'
    'x q[3];\n'
    'x q[5];\n'
    'x q[4];\n'
    'ccx q[0], q[2], q[4];\n'
    'ccx q[0], q[1], q[3];\n'
)
_WEIGHTS = Weights.from_mapping({"ccx": 32, "cx": 1, "x": 1})


def _fixture(family: str) -> tuple[Circuit, Circuit, int]:
    if family == "veriq":
        qasm = _veriq_generated_adder(2)
        assert hashlib.sha256(qasm.encode()).hexdigest() == (
            "83525fcab6a229ca6bd0a31a99db60c4878aa290f7e9f5dec3d9ee1e907891c5"
        )
        clean_control = 1
    else:
        qasm = _QSYN
        assert hashlib.sha256(qasm.encode()).hexdigest() == (
            "fbe4da09f62b188bac681750cd263417b8a72ebb5d071e63d0ef3177aa5bc4d1"
        )
        clean_control = 0
    source = parse_qasm(qasm)
    # Two initial compiler/benchmark gates are inactive on the declared domain.
    candidate = Circuit(source.width, list(source.gates[2:]))
    return source, candidate, clean_control


def _context(original: Circuit, variation: int) -> Circuit:
    # Unique full-block occurrence inside a dirty, disjoint two-wire frame.
    source = Circuit(original.width + 2)
    if variation & 1:
        source.x(0)
    if variation & 2:
        source.cx(0, 1)
    if variation & 4:
        source.x(1)
    for gate in original.gates:
        source.append(gate.name, *(w + 2 for w in gate.qubits))
    source.cx(1, 0)
    return source


def _independent_run(circuit: Circuit, value: int) -> int:
    """Reference evaluator independent of Circuit.run and SymQ SAT/ANF."""
    bits = [(value >> wire) & 1 for wire in range(circuit.width)]
    for gate in circuit.gates:
        *controls, target = gate.qubits
        if all(bits[wire] for wire in controls):
            bits[target] ^= 1
    return sum(bit << wire for wire, bit in enumerate(bits))


@pytest.mark.sat
@pytest.mark.parametrize("family", ["veriq", "qsyn"])
@pytest.mark.parametrize("variation", range(6))
def test_actual_public_source_conditional_rewrite_is_proved_and_replayed(family, variation):
    original, candidate, control = _fixture(family)
    source = _context(original, variation)
    contract = SubstitutionContract(initial_constants=((control + 2, 0),))
    prepared = prepare_local_classical(
        source, original, candidate, contract=contract,
        engine="sat", weights=_WEIGHTS, require_saving=True,
    )
    assert prepared.ready, prepared.location
    assert prepared.location["status"] == "unique"
    assert prepared.to_dict()["proved"] is False
    assert prepared.to_dict()["candidate_authorized"] is False
    report = run_request(prepared.request)
    assert report["result"]["outcome"] == "equivalent", report
    assert report["result"]["engine"] == "sat"
    assert report["result"]["theorem"] == "classical_contextual_full"
    assert report["candidate"] is not None
    assert replay_report(report)["replay"]["reverified"]
    assert report["result"]["cost"]["candidate_weighted"] < report["result"]["cost"]["reference_weighted"]
    # The final applied candidate is verified over every legal global basis input.
    rewritten = Circuit(source.width, source.gates[:prepared.request.span[0]]
                        + prepared.request.replacement.gates
                        + source.gates[prepared.request.span[1]:])
    for value in range(1 << source.width):
        if (value >> (control + 2)) & 1:
            continue
        assert _independent_run(source, value) == _independent_run(rewritten, value)


@pytest.mark.sat
@pytest.mark.parametrize("family", ["veriq", "qsyn"])
@pytest.mark.parametrize("variation", range(6))
def test_adversarial_wrong_candidate_or_false_input_domain_never_authorized(family, variation):
    original, candidate, control = _fixture(family)
    source = _context(original, variation)
    if variation % 2:
        # Deliberately remove an additional active gate.
        wrong = Circuit(candidate.width, list(candidate.gates[1:]))
        contract = SubstitutionContract(initial_constants=((control + 2, 0),))
    else:
        wrong = candidate
        # Invert the promised input restriction: the deleted gates can fire.
        contract = SubstitutionContract(initial_constants=((control + 2, 1),))
    plan = prepare_local_classical(
        source, original, wrong, contract=contract, engine="sat", weights=_WEIGHTS,
    )
    assert plan.ready
    report = run_request(plan.request)
    assert report["result"]["outcome"] != "equivalent", report
    assert report["candidate"] is None
    assert report["application"] != "applied"


def test_pinned_generator_output_and_public_benchmark_provenance():
    assert len(parse_qasm(_veriq_generated_adder(3)).gates) == 12
    assert hashlib.sha256(_veriq_generated_adder(3).encode()).hexdigest() == (
        "e78d9b6fe9cbf8b9e9fab6462a03876ba7646a45ac007903f94f3539e4ff61ef"
    )
    assert len(parse_qasm(_QSYN).gates) == 10


def test_corrupt_or_unsupported_public_source_is_not_silently_reinterpreted():
    with pytest.raises(ValueError):
        parse_qasm(_QSYN.replace("ccx q[0], q[1], q[3]", "h q[0]"))
