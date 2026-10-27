"""Verify the preserved research archive against its digests.

``MANIFEST.sha256`` is the archive's own manifest (``sha256sum`` format) and is checked
when present: every listed file must exist with the listed digest. ``RECEIVED.sha256``
records the files delivered separately before the archive payload; each must match its
own digest and, once the manifest is present, the manifest entry at the same path.

Usage: python research/verify_archive.py [research/archive/2026-10-27]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent / "archive" / "2026-10-27"


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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(sums: dict[str, str], root: Path, label: str) -> list[str]:
    problems = []
    for name, expected in sums.items():
        path = root / name
        if not path.is_file():
            problems.append(f"{label}: missing {name}")
        elif digest(path) != expected:
            problems.append(f"{label}: digest mismatch for {name}")
    return problems


def verify(root: Path = DEFAULT) -> tuple[list[str], dict]:
    """Return (problems, summary)."""
    received = read_sums(root / "RECEIVED.sha256")
    problems = check(received, root, "RECEIVED.sha256")
    summary = {"received": len(received), "manifest": None}
    manifest_path = root / "MANIFEST.sha256"
    if manifest_path.is_file():
        manifest = read_sums(manifest_path)
        summary["manifest"] = len(manifest)
        problems += check(manifest, root, "MANIFEST.sha256")
        for name, value in received.items():
            if manifest.get(name) != value:
                problems.append(
                    f"received file {name} is not listed with the same digest in MANIFEST.sha256"
                    " (its path was inferred; relocate or remove it)"
                )
    return problems, summary


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    problems, summary = verify(root)
    status = ("archive manifest absent: payload not imported yet" if summary["manifest"] is None
              else f"{summary['manifest']} manifest digests checked")
    print(f"{summary['received']} received files checked; {status}")
    for problem in problems:
        print(f"FAIL {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
