import subprocess
import sys
from pathlib import Path

import pytest

from symq.corpus import load_corpus

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "corpus" / "blind" / "MANIFEST.json"


def test_blind_manifest_matches_files_byte_for_byte():
    assert load_corpus(MANIFEST).verify() == []


def test_blind_corpus_is_regenerated_identically():
    done = subprocess.run(
        [sys.executable, str(ROOT / "benchmarks" / "generate_blind.py"), "--check-only"],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize("entry", load_corpus(MANIFEST).entries, ids=lambda e: e.name)
def test_blind_entries_parse_as_recorded(entry):
    circuit = entry.load()
    assert entry.split == "holdout" and entry.supported
    assert (circuit.width, len(circuit.gates)) == (entry.width, entry.gates)
    assert circuit.width <= 64
