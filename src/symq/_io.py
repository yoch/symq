"""Atomic file output: a reader sees either the previous file or the complete new one."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` through a temporary file in the same directory and a rename.

    An interrupted write (timeout, crash, full disk) leaves the destination untouched instead of
    truncated, which matters for receipts and caches that are read back later.
    """
    target = Path(path)
    directory = target.parent if str(target.parent) else Path(".")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                             dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
