"""One canonical digest for every hashed SymQ object (programs, contracts, domains, transcripts).

Objects are serialised as compact JSON (``separators=(",", ":")``, UTF-8) and hashed with SHA-256.
Each caller still chooses the body it hashes, including a version or grammar tag, so existing
digests recorded in artifacts keep their values.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["canonical_json", "canonical_sha256"]


def canonical_json(value: Any, *, sort_keys: bool = True) -> bytes:
    """Compact, deterministic JSON bytes; non-finite floats are refused."""
    return json.dumps(value, sort_keys=sort_keys, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def canonical_sha256(value: Any, *, sort_keys: bool = True) -> str:
    """Hex SHA-256 of :func:`canonical_json`."""
    return hashlib.sha256(canonical_json(value, sort_keys=sort_keys)).hexdigest()
