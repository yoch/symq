import hashlib
import json
import shutil
from pathlib import Path

import pytest

from symq.corpus import git_blob_sha1, load_corpus

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json"
RESULTS = ROOT / "benchmarks" / "results"
CORPUS_MANIFESTS = {"qcec": MANIFEST,
                    "blind": ROOT / "benchmarks" / "corpus" / "blind" / "MANIFEST.json"}
DEV = {"c2_181", "mod5adder_306", "rd73_312", "rd84_313", "sym9_317"}
HOLDOUT = {"5xp1_194", "alu1_198", "dk27_225", "cm150a_210", "pcler8_248", "mlp4_245"}


def test_git_blob_sha1_matches_git():
    assert git_blob_sha1(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_manifest_matches_files_byte_for_byte():
    assert load_corpus(MANIFEST).verify() == []


def test_split_is_the_handoff_split():
    corpus = load_corpus(MANIFEST)
    assert {e.name for e in corpus.select(("dev",))} == DEV
    assert {e.name for e in corpus.select(("holdout",))} == HOLDOUT
    assert all(e.supported for e in corpus.select(("dev", "holdout")))
    assert len(corpus.select(("extension",))) == 9
    with pytest.raises(ValueError):
        corpus.select(("test",))


def test_manifest_records_upstream_and_license():
    corpus = load_corpus(MANIFEST)
    source = corpus.manifest["source"]
    assert source["commit"] == "98d6784176bfeb6ef923d4d0220e8d486dc1982f"
    license_text = (MANIFEST.parent / source["license_file"]).read_bytes()
    assert git_blob_sha1(license_text) == source["license_git_blob_sha1"]
    assert b"MIT License" in license_text


@pytest.mark.parametrize("entry", load_corpus(MANIFEST).entries, ids=lambda e: e.name)
def test_entries_parse_as_recorded(entry):
    if entry.supported:
        circuit = entry.load()
        assert (circuit.width, len(circuit.gates)) == (entry.width, entry.gates)
    else:
        assert entry.name == "c2_182" and "U(" in entry.reason


def test_tampering_is_detected(tmp_path):
    copy = tmp_path / "qcec"
    shutil.copytree(MANIFEST.parent, copy)
    target = copy / "rd73_312.qasm"
    target.write_bytes(target.read_bytes().replace(b"q[1]", b"q[2]", 1))
    (copy / "extra.qasm").write_text("OPENQASM 3.0;")
    problems = load_corpus(copy / "MANIFEST.json").verify()
    assert any(p.startswith("rd73_312: git blob sha1") for p in problems)
    assert "unlisted circuit file extra.qasm" in problems


@pytest.mark.parametrize(
    "run", sorted(p for p in RESULTS.iterdir() if p.is_dir()) if RESULTS.is_dir() else [],
    ids=lambda p: p.name,
)
def test_committed_results_are_sealed(run):
    sums = (run / "SHA256SUMS").read_text().splitlines()
    listed = set()
    for line in sums:
        digest, name = line.split("  ", 1)
        listed.add(name)
        assert hashlib.sha256((run / name).read_bytes()).hexdigest() == digest, name
    assert listed == {p.name for p in run.iterdir()} - {"SHA256SUMS"}
    environment = json.loads((run / "environment.json").read_text())
    manifest = CORPUS_MANIFESTS[environment.get("corpus", "qcec")]
    assert environment["corpus_manifest_sha256"] == hashlib.sha256(
        manifest.read_bytes()).hexdigest()
    rows = [json.loads(line) for line in (run / "results.jsonl").read_text().splitlines()]
    assert not [r for r in rows if r["status"] in ("wrong_verdict", "error")]
