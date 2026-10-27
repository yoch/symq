"""Content-addressed benchmark corpora: manifests, offline hash verification, loading."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .circuit import Circuit
from .qasm import load_qasm

SPLITS = ("dev", "holdout", "extension")


def git_blob_sha1(data: bytes) -> str:
    """The SHA-1 Git assigns to a file's content, comparable with upstream tree entries."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class CorpusEntry:
    name: str
    path: Path
    split: str
    status: str
    git_blob_sha1: str
    sha256: str
    bytes: int
    width: int
    gates: int
    reason: str | None = None

    @property
    def supported(self) -> bool:
        return self.status == "supported"

    def load(self) -> Circuit:
        return load_qasm(self.path)


@dataclass(frozen=True)
class Corpus:
    root: Path
    manifest: dict
    entries: tuple[CorpusEntry, ...]

    def select(self, splits: tuple[str, ...] = SPLITS) -> list[CorpusEntry]:
        unknown = set(splits) - set(SPLITS)
        if unknown:
            raise ValueError(f"unknown splits {sorted(unknown)}")
        return [e for e in self.entries if e.split in splits]

    def verify(self) -> list[str]:
        """Return every mismatch between the manifest and the files on disk."""
        problems = []
        listed = {e.path.name for e in self.entries}
        for entry in self.entries:
            if not entry.path.is_file():
                problems.append(f"{entry.name}: missing file {entry.path.name}")
                continue
            data = entry.path.read_bytes()
            for label, expected, actual in (
                ("git blob sha1", entry.git_blob_sha1, git_blob_sha1(data)),
                ("sha256", entry.sha256, sha256_hex(data)),
                ("size", entry.bytes, len(data)),
            ):
                if expected != actual:
                    problems.append(f"{entry.name}: {label} {actual} != manifest {expected}")
        for extra in sorted(p.name for p in self.root.glob("*.qasm")):
            if extra not in listed:
                problems.append(f"unlisted circuit file {extra}")
        return problems


def load_corpus(manifest_path: str | Path) -> Corpus:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for item in manifest["circuits"]:
        if item["split"] not in SPLITS:
            raise ValueError(f"{item['name']}: unknown split {item['split']!r}")
        entries.append(
            CorpusEntry(
                name=item["name"],
                path=path.parent / item["file"],
                split=item["split"],
                status=item["status"],
                git_blob_sha1=item["git_blob_sha1"],
                sha256=item["sha256"],
                bytes=item["bytes"],
                width=item["width"],
                gates=item["gates"],
                reason=item.get("reason"),
            )
        )
    return Corpus(path.parent, manifest, tuple(entries))
