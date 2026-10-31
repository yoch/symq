"""Machine description shared by every benchmark harness.

All harnesses record the same keys, so results from different campaigns can be compared without
guessing what a field meant in each one.
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


def _proc_field(path: str, key: str) -> str | None:
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(key):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def machine() -> dict:
    """Interpreter, OS and hardware description (no repository state)."""
    memory = _proc_field("/proc/meminfo", "MemTotal")
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    return {
        "python": sys.version,
        "python_version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_model": _proc_field("/proc/cpuinfo", "model name") or "unknown",
        "cpu_count": os.cpu_count(),
        "cpu_affinity": None if affinity is None else len(affinity),
        "cpu_affinity_set": affinity,
        "mem_total_kib": int(memory.split()[0]) if memory else None,
    }
