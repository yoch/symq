"""Genuine pinned Qualtran imports; exhaustive full-coherence channel checks."""
import json
from pathlib import Path

import pytest

from symq.circuit import UnsupportedOperation
from symq.experimental.hybrid import HybridProgram, coherence_image, same_channel
from symq.experimental.importers import parse_phase_stream
from symq.experimental.qualtran import load_qualtran_fixture

CORPUS = Path(__file__).resolve().parents[1] / "benchmarks/corpus/qualtran"


def hybrid(program):
    result = HybridProgram(program.data, program.ancillas)
    for op in program.ops:
        if op.kind == "mcx":
            if len(op.qubits) == 1:
                result.x(*op.qubits)
            else:
                result.mcx(*op.qubits)
        elif op.kind == "mcz":
            getattr(result, {1: "z", 2: "cz", 3: "ccz"}[len(op.qubits)])(*op.qubits)
        elif op.kind == "hmr":
            result.hmr(op.qubits[0], f"b{op.outcome}")
        elif op.kind == "mcz_if":
            getattr(result, {1: "z", 2: "cz", 3: "ccz"}[len(op.qubits)])(
                *op.qubits, condition=f"b{op.outcome}")
        else:
            raise AssertionError(op)
    return result


@pytest.mark.parametrize("degree", (1, 2))
def test_genuine_import_prepared_full_channel_all_coherences(degree):
    fixture = load_qualtran_fixture(CORPUS / f"gf2mul_mbuc_m{degree}.json")
    reference, candidate = (hybrid(p) for p in fixture.programs())
    result = same_channel(reference, candidate)
    assert result.equivalent and result.checked_pairs == 1 << (4 * degree)
    provenance = json.loads(fixture.provenance_json)
    types = {record["type"] for record in provenance["decomposition_trace"]["cleanup"]}
    assert {"MeasureX", "ClassicallyControlled", "Parity", "Discard"} <= types
    # Whole-channel equality is claimed only after the product preparer.
    raw = hybrid(parse_phase_stream(fixture.cleanup, data=2 * degree,
                                    ancillas=degree).program)
    assert not same_channel(raw, HybridProgram(2 * degree, degree)).equivalent


@pytest.mark.parametrize("degree", (1, 2))
def test_missing_correction_is_dephasing_with_identical_basis_values(degree):
    fixture = load_qualtran_fixture(CORPUS / f"gf2mul_mbuc_m{degree}.json")
    reference, _ = (hybrid(p) for p in fixture.programs())
    lines = fixture.cleanup.splitlines()
    del lines[next(i for i, line in enumerate(lines) if line.startswith("CZ "))]
    mutant = hybrid(parse_phase_stream(fixture.preparer + "\n" + "\n".join(lines),
                                      data=2 * degree, ancillas=degree).program)
    for x in range(1 << (2 * degree)):
        assert coherence_image(reference, x, x) == coherence_image(mutant, x, x)
    result = same_channel(reference, mutant)
    assert not result.equivalent and result.witness[0] != result.witness[1]


@pytest.mark.parametrize("mutation", ("parity", "event", "wire"))
def test_parity_event_and_bit_order_mutants_fail_full_channel(mutation):
    fixture = load_qualtran_fixture(CORPUS / "gf2mul_mbuc_m2.json")
    preparer, cleanup = fixture.preparer, fixture.cleanup
    if mutation == "parity":
        cleanup = cleanup.replace("OXOR b2 b1", "OXOR b2 b0")
    elif mutation == "event":
        cleanup = cleanup.replace("CZ q0 q2 if b0", "CZ q0 q2 if b1")
    else:
        preparer = preparer.replace("q0", "TEMP").replace("q1", "q0").replace("TEMP", "q1")
    mutant = hybrid(parse_phase_stream(preparer + "\n" + cleanup, data=4, ancillas=2).program)
    reference, _ = (hybrid(p) for p in fixture.programs())
    assert not same_channel(reference, mutant).equivalent


def test_fixture_digests_and_contract_fail_closed(tmp_path):
    original = json.loads((CORPUS / "gf2mul_mbuc_m2.json").read_text())
    for target, value in (("cleanup", "HMR q4 b0"), ("degree", True),
                          ("contract", {"precondition": "arbitrary dirty result"})):
        payload = {**original, target: value}
        path = tmp_path / f"bad_{target}.json"
        path.write_text(json.dumps(payload))
        with pytest.raises(UnsupportedOperation):
            load_qualtran_fixture(path)
