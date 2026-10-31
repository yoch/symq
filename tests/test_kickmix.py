"""The strict kickmix (.kmx) importer on the public Qualtran test corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from symq import PhaseProgram, UnsupportedOperation, check_equivalence, check_phase_equivalence
from symq.kickmix import KmxSyntaxError, load_kmx, parse_kmx

CORPUS = Path(__file__).resolve().parents[1] / "benchmarks" / "corpus" / "kickmix"


def test_the_corpus_matches_its_manifest():
    manifest = json.loads((CORPUS / "MANIFEST.json").read_text())
    assert manifest["source"]["license"] == "Apache-2.0"
    assert (CORPUS / manifest["source"]["license_file"]).is_file()
    for entry in manifest["files"]:
        data = (CORPUS / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["file"]


def test_inc3_is_the_increment_modulo_8():
    program = load_kmx(CORPUS / "inc3.kmx")
    circuit = program.to_circuit()
    assert [circuit.run(x) for x in range(8)] == [(x + 1) % 8 for x in range(8)]
    assert program.counts()["toffoli_like"] == 1


def _mcx_increment(width: int) -> PhaseProgram:
    reference = PhaseProgram(width, 0)
    for i in range(width - 1, 0, -1):
        reference.mcx(*range(i), i)
    return reference.x(0)


def test_measurement_based_increment_equals_the_textbook_increment():
    """inc8 uncomputes its carries with HMR and CZ corrections; it is the plain increment."""
    program = load_kmx(CORPUS / "inc8.kmx")
    assert program.counts()["HMR"] == 5 and program.counts()["CZ_IF"] == 5
    verdict = check_phase_equivalence(program.to_phase_program(data=range(8)), _mcx_increment(8))
    assert verdict.equivalent and not verdict.violations


def test_dropping_one_phase_correction_is_caught():
    text = (CORPUS / "inc8.kmx").read_text()
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("CZ ") and " if " in line)
    mutant = parse_kmx("\n".join(lines[:first] + lines[first + 1:]))
    verdict = check_phase_equivalence(mutant.to_phase_program(data=range(8)), _mcx_increment(8))
    assert not verdict.equivalent
    assert any("O2" in violation for violation in verdict.violations)


def test_cmul16_mod_21_is_a_controlled_modular_permutation():
    """Pinned observed behaviour: control q5, register q0..q4 (LSB first), x -> 4x mod 21."""
    circuit = load_kmx(CORPUS / "cmul16_mod_21.kmx").to_circuit()
    assert circuit.width == 6
    assert all(circuit.run(x) == x for x in range(32))
    assert all(circuit.run(x | 32) == ((4 * x) % 21) | 32 for x in range(21))
    assert sorted(circuit.run(x) for x in range(64)) == list(range(64))


def test_imported_circuits_go_through_the_classical_checkers():
    circuit = load_kmx(CORPUS / "cmul16_mod_21.kmx").to_circuit()
    assert check_equivalence(circuit, circuit.inverse().inverse(), backend="zdd").equivalent


@pytest.mark.parametrize(("name", "reason"), [
    ("iadd8_qc_2clean_6dirty.kmx", "reset"),
    ("mul16_mod_21.kmx", "reset"),
    ("qft_measurement.kmx", "arbitrary-angle"),
])
def test_files_outside_the_subset_are_refused_with_the_line(name, reason):
    with pytest.raises(UnsupportedOperation, match=rf"line \d+: .*{reason}"):
        load_kmx(CORPUS / name)


def test_phases_and_measurements_never_become_a_classical_circuit():
    with pytest.raises(UnsupportedOperation, match="to_phase_program"):
        load_kmx(CORPUS / "inc8.kmx").to_circuit()


@pytest.mark.parametrize(("text", "error"), [
    ("CCX q0 q1", KmxSyntaxError),
    ("CX q0 q0", KmxSyntaxError),
    ("CX q0 x1", KmxSyntaxError),
    ("X q0 if b0", None),  # parsed; refused when lowered (conditional reversible gate)
    ("HMR q0 b0 if b1", UnsupportedOperation),
    ("FOO q0", UnsupportedOperation),
    ("NEG_IF b0", UnsupportedOperation),
])
def test_malformed_or_unsupported_lines(text, error):
    if error is None:
        program = parse_kmx(text)
        with pytest.raises(UnsupportedOperation, match="conditioned"):
            program.to_phase_program(data=[0])
        return
    with pytest.raises(error):
        parse_kmx(text)


def test_a_condition_must_follow_a_measurement():
    with pytest.raises(UnsupportedOperation, match="before any HMR"):
        parse_kmx("CZ q0 q1 if b3").to_phase_program(data=[0, 1])


def test_swaps_are_lowered_exactly():
    circuit = parse_kmx("SWAP q0 q1\nCSWAP q2 q0 q1").to_circuit()
    for x in range(8):
        a, b, c = x & 1, x >> 1 & 1, x >> 2 & 1
        a, b = b, a
        if c:
            a, b = b, a
        assert circuit.run(x) == a | b << 1 | c << 2


def test_binary_format_is_refused(tmp_path):
    (tmp_path / "x.kmb").write_bytes(b"\x00")
    with pytest.raises(UnsupportedOperation, match="kmb"):
        load_kmx(tmp_path / "x.kmb")
