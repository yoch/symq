"""Independent bounded channel-oracle checks for the affine HMR proof pilot."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from symq import Circuit
from symq.experimental.hybrid import HybridProgram, coherence_image, same_channel
from symq.experimental.serialization import program_to_dict
from symq.labs import affine_hmr_portable as portable


def _support(data=1):
    return {"kind": "affine_data_span", "offset": 0,
            "columns": [1 << i for i in range(data)]}


def _reference(width):
    return Circuit(width).to_dict()


def _corrected():
    source = HybridProgram(1, 1).cx(0, 1).hmr(1, "b0").z(0, condition="b0")
    return source


def _emit(source=None, reference=None, support=None):
    source = _corrected() if source is None else source
    reference = _reference(source.width) if reference is None else reference
    support = _support(source.data) if support is None else support
    source_doc = program_to_dict(source)
    result = portable.export_affine_hmr_certificate(source_doc, reference, support)
    return result, source_doc, reference, support


def _check(bundle, source, reference, support):
    return portable.check_affine_hmr_certificate(
        bundle, expected_source_sha256=portable.digest(source),
        expected_reference_sha256=portable.digest(reference),
        expected_support_sha256=portable.digest(support),
    )


def test_corrected_hmr_has_portable_positive_and_independent_dense_channel_oracle():
    source = _corrected()
    result, original, reference, support = _emit(source)
    assert result["status"] == "exported"
    bundle = result["bundle"]
    assert bundle["claim"]["rank"] == 1
    assert bundle["claim"]["events"] == 1
    checked = _check(bundle, original, reference, support)
    assert checked["status"] == "verified" and checked["verified_channel"]
    assert same_channel(source, HybridProgram(1, 1)).equivalent
    # A branch-dependent GLOBAL sign is allowed even though the instrument changes.
    source.neg(condition="b0")
    result, original, reference, support = _emit(source)
    assert result["status"] == "exported"
    assert _check(result["bundle"], original, reference, support)["verified_channel"]
    assert same_channel(source, HybridProgram(1, 1)).equivalent


def test_missing_phase_correction_refused_and_dense_coherence_detects_difference():
    broken = HybridProgram(1, 1).cx(0, 1).hmr(1, "b0")
    result, *_ = _emit(broken)
    assert result["status"] == "not_proved"
    assert result["obligation"] == "input_dependent_branch_phase"
    assert not same_channel(broken, HybridProgram(1, 1)).equivalent
    assert coherence_image(broken, 0, 1) != coherence_image(HybridProgram(1, 1), 0, 1)


def test_affine_coherence_support_linearizes_a_controlled_toffoli():
    source = HybridProgram(2, 1).ccx(0, 1, 2)
    reference = Circuit(3).cx(0, 2).to_dict()
    support = {"kind": "affine_data_span", "offset": 0, "columns": [0b11]}
    result, original, _, _ = _emit(source, reference, support)
    assert result["status"] == "exported"
    assert _check(result["bundle"], original, reference, support)["verified_channel"]
    ref_program = HybridProgram(2, 1).cx(0, 2)
    for x in (0, 3):
        for y in (0, 3):
            assert coherence_image(source, x, y) == coherence_image(ref_program, x, y)
    full = {"kind": "affine_data_span", "offset": 0, "columns": [1, 2]}
    result, *_ = _emit(source, reference, full)
    assert result["status"] == "unsupported"  # intermediate nonlinear control product


def test_large_synthetic_40_physical_35_rank_89_hmr_symbolic_no_branch_enumeration():
    source = HybridProgram(39, 1).cx(0, 39).hmr(39, "b0").z(0, condition="b0")
    for event in range(1, 89):
        source.hmr(39, f"b{event}")  # a known-zero measured ancilla
    support = {"kind": "affine_data_span", "offset": 0,
               "columns": [1 << bit for bit in range(35)]}
    result, original, reference, support = _emit(source, _reference(40), support)
    assert result["status"] == "exported"
    assert result["bundle"]["claim"]["events"] == 89
    assert result["bundle"]["claim"]["rank"] == 35
    assert _check(result["bundle"], original, reference, support)["verified_channel"]
    assert portable.export_affine_hmr_certificate(
        original, reference, support, max_events=80,
    )["status"] == "inconclusive"
    # The same mathematical proof fails with a missing phase correction.
    bad = HybridProgram(39, 1).cx(0, 39).hmr(39, "b0")
    for event in range(1, 89):
        bad.hmr(39, f"b{event}")
    result, *_ = _emit(bad, reference, support)
    assert result["status"] == "not_proved"


def test_wrong_output_and_unsupported_operations_fail_closed():
    source = HybridProgram(1, 1).cx(0, 1)
    result, *_ = _emit(source)
    assert result["status"] == "not_proved" and result["obligation"] == "quantum_output"
    source = HybridProgram(3).ccz(0, 1, 2)
    result, *_ = _emit(source)
    assert result["status"] == "unsupported"
    source = HybridProgram(1, 1).cx(0, 1).reset(1)
    result, *_ = _emit(source)
    assert result["status"] == "unsupported"  # genuine reset: no known-zero shortcut
    source = HybridProgram(1, 1).cx(0, 1).measure_z(1, "b0")
    result, *_ = _emit(source)
    assert result["status"] == "unsupported"  # input-dependent Z measurement


def test_source_pin_reference_pin_support_pin_and_claim_mutations_rejected():
    result, source, reference, support = _emit()
    bundle = result["bundle"]
    for key, mutation in (
        ("source", lambda x: x["ops"][0].update(kind="x")),
        ("reference", lambda x: x["gates"].append(["x", [0]])),
        ("support", lambda x: x.update(offset=1)),
        ("claim", lambda x: x.update(events=0)),
    ):
        altered = copy.deepcopy(bundle)
        mutation(altered[key])
        checked = _check(altered, source, reference, support)
        assert not checked["verified_channel"], key
        assert checked["status"] == "invalid"
    altered = copy.deepcopy(bundle)
    altered["additional"] = True
    assert _check(altered, source, reference, support)["status"] == "invalid"
    assert portable.check_affine_hmr_certificate(
        bundle, expected_source_sha256="0" * 64,
        expected_reference_sha256=portable.digest(reference),
        expected_support_sha256=portable.digest(support),
    )["status"] == "invalid"


def test_false_affine_rank_or_classical_slot_rejected():
    _result, source, reference, support = _emit()
    bad = copy.deepcopy(support)
    bad["columns"] = [1, 1]
    assert portable.export_affine_hmr_certificate(source, reference, bad)["status"] == "invalid"
    bad = copy.deepcopy(source)
    bad["ops"][2]["condition"] = "b3"
    assert portable.export_affine_hmr_certificate(bad, reference, support)["status"] == "invalid"
    bad = copy.deepcopy(source)
    bad["ops"][1]["kind"] = "reset"
    assert portable.export_affine_hmr_certificate(bad, reference, support)["status"] == "unsupported"
    assert portable.export_affine_hmr_certificate(
        source, reference, support, max_terms=0
    )["status"] == "invalid"


def test_standalone_checker_runs_without_importing_symq_or_pysat(tmp_path):
    result, source, reference, support = _emit()
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(result["bundle"]), encoding="utf-8")
    script = Path(portable.__file__)
    assert "from symq" not in script.read_text(encoding="utf-8")
    command = [
        sys.executable, str(script), str(bundle),
        "--source-pin", portable.digest(source),
        "--reference-pin", portable.digest(reference),
        "--support-pin", portable.digest(support),
    ]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr + done.stdout
    assert json.loads(done.stdout)["verified_channel"] is True
    bundle.write_text(bundle.read_text() + "\n", encoding="utf-8")
    # Whitespace does not change the canonical structured source proof identity.
    assert subprocess.run(command, capture_output=True, check=False).returncode == 0
    bundle.write_text('{"kind":1, "kind":2}')
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0


def test_seeded_affine_hmr_positives_match_independent_full_matrix_units():
    """Adversarially compare every claimed positive to the separate Kraus oracle.

    Includes arbitrary coherent x/y, correlated support, repeated HMR, value
    gates before/after uncomputation, conditional global signs, and missing
    phase feedback. Refused/inconclusive cases are NOT declared different.
    """
    import random

    random_source = random.Random(0x51A19)
    accepted = refused = 0
    for _ in range(96):
        program = HybridProgram(2, 1)
        ideal = HybridProgram(2, 1)
        reference = Circuit(3)
        for _ in range(random_source.randrange(4)):
            gate = random_source.choice(("x0", "x1", "cx01", "cx10"))
            if gate == "x0":
                program.x(0)
                ideal.x(0)
                reference.x(0)
            elif gate == "x1":
                program.x(1)
                ideal.x(1)
                reference.x(1)
            elif gate == "cx01":
                program.cx(0, 1)
                ideal.cx(0, 1)
                reference.cx(0, 1)
            else:
                program.cx(1, 0)
                ideal.cx(1, 0)
                reference.cx(1, 0)
        measured = random_source.randrange(2)
        program.cx(measured, 2).hmr(2, "b0")
        if random_source.randrange(4):
            program.z(measured, condition="b0")
        if random_source.randrange(2):
            program.neg(condition="b0")  # legal branch-global phase
        if random_source.randrange(2):
            program.hmr(2, "b1")
            if random_source.randrange(3) == 0:
                program.z(0, condition="b1")  # usually breaks coherence
        if random_source.randrange(2):
            program.cx(0, 1)
            ideal.cx(0, 1)
            reference.cx(0, 1)
        if random_source.randrange(4) == 0:
            program.z(1)  # input-dependent sign, except on fixed subspaces
        columns = [3] if random_source.randrange(3) == 0 else [1, 2]
        support = {"kind": "affine_data_span", "offset": 0, "columns": columns}
        outcome, source_doc, reference_doc, actual_support = _emit(
            program, reference.to_dict(), support
        )
        assert outcome["status"] in {"exported", "not_proved", "unsupported"}
        if outcome["status"] != "exported":
            refused += 1
            continue
        accepted += 1
        checked = _check(outcome["bundle"], source_doc,
                         reference_doc, actual_support)
        assert checked["status"] == "verified"
        legal = (0, 3) if columns == [3] else (0, 1, 2, 3)
        for x in legal:
            for y in legal:
                assert coherence_image(program, x, y) == coherence_image(ideal, x, y)
    assert accepted >= 12 and refused >= 12
