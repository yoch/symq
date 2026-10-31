"""The recorded performance evidence is intact and the published tables are derived from it."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from benchmarks import paired

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "evidence" / "data" / "2026-10-31"
REPORT = ROOT / "docs" / "evidence" / "performance-2026-10-31.md"
ROUNDS = [DATA / "round1", DATA / "round2"]


def test_raw_records_match_their_checksums():
    lines = (DATA / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 * len(paired.SPLITS) * len(ROUNDS)
    for line in lines:
        digest, name = line.split()
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == digest, name


def test_both_sides_are_single_clean_identified_builds():
    seen = paired.receipts(ROUNDS)
    for side in ("base", "head"):
        assert len(seen[side]) == 1, side
        commit, dirty, source, native, abi = next(iter(seen[side]))
        assert re.fullmatch(r"[0-9a-f]{40}", commit) and dirty is False
        assert len(source) == 64 and len(native) == 64 and abi == 6
    assert next(iter(seen["base"]))[0] != next(iter(seen["head"]))[0]


@pytest.mark.parametrize("backend", ["sat", "sparse", "zdd", "zdd-native"])
def test_published_tables_are_regenerated_from_the_records(backend):
    text = REPORT.read_text(encoding="utf-8")
    match = re.search(rf"<!-- paired:{re.escape(backend)} -->\n(.*?)\n<!-- /paired -->", text,
                      re.DOTALL)
    assert match, f"no generated table for {backend}"
    assert match.group(1).strip() == paired.table(ROUNDS, backend)
