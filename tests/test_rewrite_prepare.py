"""A local circuit becomes a globally mapped proof request without guessed assumptions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from symq import Circuit
from symq.__main__ import main
from symq.labs.contextual_substitution import SubstitutionContract
from symq.labs.rewrite import Weights
from symq.labs.rewrite_prepare import prepare_local_classical, write_prepared_rewrite
from symq.labs.rewrite_request import (
    load_request_files,
    replay_report,
    replayed_candidate,
    run_request,
)


def _local():
    return Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)


def _source():
    # Local source wires [0,1,2] are mapped to global [4,1,6].
    return (Circuit(8).x(0).ccx(4, 1, 6).ccx(4, 1, 6)
            .cx(0, 5))


def _prepare(*, contract=None, replacement=None, engine="auto"):
    return prepare_local_classical(
        _source(), _local(),
        Circuit(3) if replacement is None else replacement,
        contract=SubstitutionContract() if contract is None else contract,
        engine=engine, weights=Weights.from_mapping({"ccx": 32, "cx": 1}),
    )


def _json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _cli_inputs(directory: Path, *, contract=None, replacement=None) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    files = (
        directory / "source.json", directory / "original.json",
        directory / "candidate.json", directory / "contract.json",
    )
    for path, content in zip(files, (
        _source().to_dict(), _local().to_dict(),
        (Circuit(3) if replacement is None else replacement).to_dict(),
        {} if contract is None else contract,
    )):
        _json(path, content)
    return files


def test_exact_global_mapping_and_frozen_local_preparation_are_not_a_proof():
    source = _source()
    local = _local()
    plan = prepare_local_classical(
        source, local, Circuit(3), contract=SubstitutionContract(),
        engine="auto",
    )
    assert plan.ready
    assert plan.to_dict()["proved"] is False
    assert plan.to_dict()["candidate_authorized"] is False
    assert plan.location["matches"][0]["wires"] == [4, 1, 6]
    assert plan.request is not None
    assert plan.request.span == (1, 3)
    assert plan.request.source.width == plan.request.replacement.width == 8
    assert plan.request.replacement.gates == []
    source.x(7)
    local.x(0)
    # The source and original input lists cannot mutate the frozen proof request.
    assert len(plan.request.source.gates) == 4
    record = run_request(plan.request)
    assert record["result"]["outcome"] == "equivalent"
    assert record["result"]["engine"] == "packed"
    assert replay_report(record)["replay"]["reverified"]
    for value in range(1 << 8):
        assert plan.request.source.run(value) == Circuit(
            8, plan.request.source.gates[:1] + plan.request.source.gates[3:]
        ).run(value)


@pytest.mark.sat
def test_explicit_clean_and_restoration_contract_forces_sat():
    reference = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
    # Scratch wire 4 is zero at the cut for legal initial inputs, and
    # both candidate/reference restore it and the borrowed operands.
    source = Circuit(5).cx(0, 4).cx(0, 4).ccx(0, 1, 4).ccx(0, 1, 4)
    contract = SubstitutionContract(
        initial_constants=((4, 0),), clean_at_cut=(4,),
        restored_at_cut=(0, 1),
    )
    plan = prepare_local_classical(
        source, reference, Circuit(3), contract=contract, engine="auto",
    )
    assert plan.ready
    report = run_request(plan.request)
    assert report["result"]["outcome"] == "equivalent"
    assert report["result"]["theorem"] == "classical_contextual_full"
    assert report["result"]["engine"] == "sat"
    assert {"restore_original", "restore_candidate"} <= {
        x["name"] for x in report["result"]["obligations"]
    }


def test_unknown_or_ambiguous_mapping_is_not_prepared_and_never_exports_a_candidate(tmp_path):
    ref = _local()
    duplicate = Circuit(7).ccx(4, 1, 6).ccx(4, 1, 6).ccx(4, 1, 6).ccx(4, 1, 6)
    ambiguous = prepare_local_classical(
        duplicate, ref, Circuit(3), contract=SubstitutionContract(),
    )
    assert not ambiguous.ready
    assert ambiguous.location["status"] == "ambiguous"
    assert ambiguous.request is None
    with pytest.raises(ValueError, match="unique complete"):
        write_prepared_rewrite(ambiguous, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()
    incomplete = prepare_local_classical(
        Circuit(7).ccx(4, 1, 6), Circuit(4).ccx(0, 1, 2),
        Circuit(4), contract=SubstitutionContract(),
    )
    assert incomplete.location["status"] == "unmapped_wires"
    assert incomplete.request is None


def test_wrong_local_candidate_is_staged_but_refused_by_actual_verifier():
    plan = _prepare(replacement=Circuit(3).ccx(0, 1, 2))
    assert plan.ready  # structural match does not prove semantic equivalence
    report = run_request(plan.request)
    assert report["result"]["outcome"] == "not_proved"
    assert report["candidate"] is None
    assert report["application"] == "not_proved"
    assert replayed_candidate(report) is None


def test_cli_builds_fresh_files_and_replays_after_originals_are_deleted(tmp_path, capsys):
    files = _cli_inputs(tmp_path / "input")
    output = tmp_path / "prepared"
    args = ["prepare-rewrite", str(files[0]), str(files[1]), str(files[2]),
            "--contract", str(files[3]), "--output-dir", str(output), "--engine", "auto"]
    assert main(args) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["kind"] == "symq_rewrite_preparation"
    assert status["status"] == "ready_for_proof"
    assert status["proved"] is False
    assert status["advisory_only"]
    assert status["location"]["matches"][0]["wires"] == [4, 1, 6]
    assert set(output.iterdir()) == {
        output / "source.json", output / "replacement.json",
        output / "request.json", output / "preparation.json",
    }
    manifest = json.loads((output / "preparation.json").read_text())
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert manifest["input_file_sha256"]["reference"] == hashlib.sha256(
        files[1].read_bytes()).hexdigest()
    req, proofs, paths = load_request_files(output / "request.json")
    assert len(paths) == 3 and len(proofs) == 3
    assert req.engine == "auto" and req.span == (1, 3)

    for original in files:
        original.unlink()
    proof = output / "proof.json"
    assert main(["rewrite", str(output / "request.json"), "--report", str(proof)]) == 0
    verify_status = json.loads(capsys.readouterr().out)
    assert verify_status["result"]["outcome"] == "equivalent"
    assert verify_status["result"]["theorem"] == "classical_total"
    assert main(["replay", str(proof)]) == 0
    assert json.loads(capsys.readouterr().out)["replay"]["reverified"] is True
    for file in ("source.json", "replacement.json", "request.json"):
        (output / file).unlink()
    assert main(["replay", str(proof)]) == 0
    assert json.loads(capsys.readouterr().out)["replay"]["reverified"] is True


def test_existing_destination_or_malformed_request_never_overwrites(tmp_path, capsys):
    files = _cli_inputs(tmp_path / "input")
    output = tmp_path / "prepared"
    output.mkdir()
    (output / "important.txt").write_text("must stay untouched")
    args = ["prepare-rewrite", str(files[0]), str(files[1]), str(files[2]),
            "--contract", str(files[3]), "--output-dir", str(output)]
    assert main(args) == 3
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "invalid"
    # Even an error record states explicitly that nothing is proved or authorized.
    assert response["proved"] is False and response["candidate_authorized"] is False
    assert response["ready_for_proof"] is False
    assert (output / "important.txt").read_text() == "must stay untouched"
    assert not (output / "source.json").exists()
    files[3].write_text('{"unknown_cut_assumption": true}')
    assert main(args) == 3
    assert "unknown fields" in json.loads(capsys.readouterr().out)["reason"]


def test_cli_ambiguous_location_returns_inert_json_with_no_partial_artifacts(tmp_path, capsys):
    files = _cli_inputs(tmp_path / "input")
    source = Circuit(8).ccx(4, 1, 6).ccx(4, 1, 6).ccx(4, 1, 6).ccx(4, 1, 6)
    _json(files[0], source.to_dict())
    target = tmp_path / "no-output"
    assert main(["prepare-rewrite", str(files[0]), str(files[1]), str(files[2]),
                 "--contract", str(files[3]), "--output-dir", str(target)]) == 2
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "ambiguous"
    assert status["ready_for_proof"] is False
    assert status["proved"] is False
    assert not target.exists()


def test_116_affine_replacement_sites_are_separately_proved_without_guessing():
    """Synthetic geometry, not a real external compiler artifact or timing comparison."""
    local = Circuit(2).cx(0, 1).cx(0, 1)
    for index in range(116):
        a = index % 48
        b = (index * 13 + 17) % 48
        if a == b:
            b = (b + 1) % 48
        source = (Circuit(48).x((a + 2) % 48)
                  .cx(a, b).cx(a, b).x((b + 3) % 48))
        plan = prepare_local_classical(
            source, local, Circuit(2), contract=SubstitutionContract(),
            engine="auto",
        )
        assert plan.ready
        proof = run_request(plan.request)
        assert proof["result"]["outcome"] == "equivalent"
        assert proof["result"]["engine"] == "linear"
        assert proof["result"]["theorem"] == "classical_total"


def test_public_gf64_source_is_mapped_and_proved_on_a_wider_arbitrary_frame():
    """Authentic exposed public KMB, not a newly acquired compiler holdout.

    Exercises non-identity wire renumbering, dirty accumulation targets,
    and the exact packed total theorem. No private corpus is imported.
    """
    import hashlib
    import random

    from benchmarks.bilinear_kmb import manifest, source_starts
    from benchmarks.kmb import decode
    from symq.circuit import Gate
    from symq.generators.gf2n import tower_multiplier

    fixture = next(row for row in manifest() if row["id"] == "gf64-03")
    raw = source_starts()[fixture["kmb"]]
    assert hashlib.sha256(raw).hexdigest() == fixture["sha256"]
    local = decode(raw)
    assert local.width == 18
    tower = tower_multiplier(6, modulus=fixture["modulus"])
    local_to_global = tuple(range(3, 21))
    source = Circuit(24, [
        Gate("x", (0,)),
        *(Gate(gate.name, tuple(local_to_global[q] for q in gate.qubits))
          for gate in local.gates),
        Gate("cx", (0, 22)),
    ])
    plan = prepare_local_classical(
        source, local, tower, contract=SubstitutionContract(),
        weights=Weights.from_mapping({"ccx": 32, "cx": 1}),
        engine="packed",
    )
    assert plan.ready
    assert plan.location["matches"][0]["wires"] == list(local_to_global)
    assert plan.request is not None
    outcome = run_request(plan.request)
    assert outcome["result"]["outcome"] == "equivalent"
    assert outcome["result"]["engine"] == "packed"
    assert outcome["result"]["theorem"] == "classical_total"
    verified = replayed_candidate(outcome)
    assert verified is not None
    rng = random.Random(20261101)
    probes = [0, (1 << 24) - 1, *[rng.getrandbits(24) for _ in range(256)]]
    for value in probes:
        assert source.run(value) == verified.run(value)


def test_prepared_file_export_refuses_mutated_frozen_request_and_location(tmp_path):
    # A Python caller can edit a Circuit's gate list after the preparer returns.
    # The exported SHA-256 identities must never describe an earlier snapshot.
    for mutate in (
        lambda plan: plan.request.source.x(7),
        lambda plan: plan.request.replacement.x(0),
        lambda plan: plan.location["matches"][0].update(span=[0, 2]),
    ):
        plan = _prepare()
        assert plan.request is not None
        mutate(plan)
        with pytest.raises(ValueError, match="changed after freezing"):
            write_prepared_rewrite(plan, tmp_path / "would-be-false-provenance")
        assert not (tmp_path / "would-be-false-provenance").exists()


def test_prepared_files_must_fit_the_real_proof_input_byte_limit(tmp_path, monkeypatch):
    from symq.labs import rewrite_prepare

    plan = _prepare()
    monkeypatch.setattr(rewrite_prepare, "MAX_INPUT_BYTES", 1)
    with pytest.raises(ValueError, match="exceeds the proof CLI"):
        write_prepared_rewrite(plan, tmp_path / "too-large")
    assert not (tmp_path / "too-large").exists()
