"""Verify a research archive directory against its ``MANIFEST.sha256``.

Every listed file must exist with the listed digest, and every file in the directory
(except the manifest itself and Python caches) must be listed.

Usage: python research/verify_archive.py [research/archive/2026-10-27]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent / "archive" / "2026-10-27"
MANIFEST = "MANIFEST.sha256"
IGNORED_DIRS = {"__pycache__", ".pytest_cache"}


def read_sums(path: Path) -> dict[str, str]:
    sums = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        digest, sep, name = line.partition("  ")
        if not sep or len(digest) != 64:
            raise ValueError(f"{path.name}:{number}: not a sha256sum line")
        sums[name.lstrip("*")] = digest
    return sums


def present_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.name != MANIFEST
        and not IGNORED_DIRS.intersection(path.relative_to(root).parts)
    }


def verify(root: Path = DEFAULT) -> tuple[list[str], int]:
    """Return (problems, number of manifest entries)."""
    manifest = read_sums(root / MANIFEST)
    problems = []
    for name, expected in sorted(manifest.items()):
        path = root / name
        if not path.is_file():
            problems.append(f"missing {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(f"digest mismatch for {name}")
    problems += [f"unlisted {name}" for name in sorted(present_files(root) - manifest.keys())]
    return problems, len(manifest)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    problems, count = verify(root)
    print(f"{count} manifest digests checked in {root}")
    for problem in problems:
        print(f"FAIL {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
