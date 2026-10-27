import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "research" / "archive" / "2026-10-27"

_spec = importlib.util.spec_from_file_location(
    "verify_archive", ROOT / "research" / "verify_archive.py"
)
verify_archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_archive)


def test_preserved_archive_files_match_their_digests():
    problems, summary = verify_archive.verify(ARCHIVE)
    assert problems == []
    assert summary["received"] >= 3


def test_tampering_and_missing_payload_are_reported(tmp_path):
    copy = tmp_path / "archive"
    shutil.copytree(ARCHIVE, copy)
    target = copy / "docs" / "CORPORA_RECENTS.md"
    target.write_bytes(target.read_bytes() + b"\n")
    (copy / "MANIFEST.sha256").write_text(f"{'0' * 64}  src/zdd.py\n")
    problems, summary = verify_archive.verify(copy)
    assert summary["manifest"] == 1
    assert "RECEIVED.sha256: digest mismatch for docs/CORPORA_RECENTS.md" in problems
    assert "MANIFEST.sha256: missing src/zdd.py" in problems
    assert any("AGENT_QANT.md is not listed" in p for p in problems)
