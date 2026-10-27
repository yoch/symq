import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from symq import make_algebra, simulate
from symq.corpus import load_corpus

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "research" / "archive" / "2026-10-27"
CORPUS = ROOT / "benchmarks" / "corpus" / "qcec" / "MANIFEST.json"
ARCHIVE_ENGINES = ("copy_set", "fast_set", "zdd", "auto_zdd")

ARCHIVE_OUTPUTS = """
import json
from src.corpus import read_corpus
from src.optimized import FastSetState, SetState
from src.zdd import AutoZDDState, ZDDState

engines = {"copy_set": SetState, "fast_set": FastSetState, "zdd": ZDDState,
           "auto_zdd": AutoZDDState}
out = {}
for item in read_corpus():
    n = item["n"]
    out[item["name"]] = {}
    for label, engine in engines.items():
        state = engine(n, tuple(range(n)))
        state.run(item["ops"])
        wires, phase = state.digest()
        assert phase == ()
        out[item["name"]][label] = {str(q): list(terms) for q, terms in wires}
print(json.dumps(out))
"""

_spec = importlib.util.spec_from_file_location(
    "verify_archive", ROOT / "research" / "verify_archive.py"
)
verify_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_archive)


def test_archive_matches_its_manifest_exactly():
    problems, count = verify_archive.verify(ARCHIVE)
    assert problems == []
    assert count == len(verify_archive.present_files(ARCHIVE)) == 29


def test_tampered_missing_and_unlisted_files_are_reported(tmp_path):
    copy = tmp_path / "archive"
    shutil.copytree(ARCHIVE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    target = copy / "docs" / "CORPORA_RECENTS.md"
    target.write_bytes(target.read_bytes() + b"\n")
    (copy / "src" / "zdd.py").unlink()
    (copy / "notes.txt").write_text("extra\n")
    (copy / "src" / "__pycache__").mkdir()
    (copy / "src" / "__pycache__" / "zdd.cpython-312.pyc").write_bytes(b"cache")
    problems, _ = verify_archive.verify(copy)
    assert problems == [
        "digest mismatch for docs/CORPORA_RECENTS.md",
        "missing src/zdd.py",
        "unlisted notes.txt",
    ]


def run_in_archive(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, *args], cwd=ARCHIVE, env=env, capture_output=True, text=True, check=False
    )


def test_archived_test_suite_still_passes():
    result = run_in_archive("-m", "pytest", "-q", "-p", "no:cacheprovider", "tests")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "24 passed" in result.stdout


@pytest.fixture(scope="module")
def archive_outputs() -> dict:
    result = run_in_archive("-c", ARCHIVE_OUTPUTS)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("backend", ["sparse", "zdd"])
def test_symq_reproduces_archived_engine_outputs(archive_outputs, backend):
    entries = load_corpus(CORPUS).select(("dev", "holdout"))
    assert {e.name for e in entries} == set(archive_outputs)
    for entry in entries:
        circuit = entry.load()
        algebra = make_algebra(backend, circuit.width)
        ours = {
            str(wire): sorted(algebra.to_anf(value).terms)
            for wire, value in enumerate(simulate(circuit, algebra))
            if not algebra.is_zero(value)
        }
        for engine in ARCHIVE_ENGINES:
            assert archive_outputs[entry.name][engine] == ours, (entry.name, engine)
