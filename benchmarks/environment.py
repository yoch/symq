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


def _git(directory: Path, *args: str) -> str | None:
    import subprocess

    try:
        done = subprocess.run(["git", "-C", str(directory), *args], capture_output=True,
                              text=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def receipt() -> dict:
    """Identity of the code that was measured: the imported ``symq`` package, its git commit
    and cleanliness, a digest of its sources, the loaded native binary and the SAT library.

    Self-contained (it does not use ``symq.doctor``), so the same harness can measure an older
    source tree put on ``PYTHONPATH`` and still say exactly what it ran.
    """
    import hashlib
    import importlib.util
    from importlib import metadata

    import symq

    package = Path(symq.__file__).resolve().parent
    sources = sorted(p for p in package.rglob("*") if p.is_file() and p.suffix in {".py", ".c"})
    digest = hashlib.sha256()
    for path in sources:
        digest.update(f"{path.relative_to(package).as_posix()}:".encode())
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
    native: dict = {"available": False}
    spec = importlib.util.find_spec("symq.backends._zdd")
    if spec is not None and spec.origin:
        binary = Path(spec.origin)
        native = {"available": True, "path": str(binary),
                  "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
        try:
            from symq.backends import _zdd

            native["abi"] = getattr(_zdd, "ABI_VERSION", None)
        except ImportError as error:
            native.update(available=False, error=str(error))
    try:
        pysat = metadata.version("python-sat")
    except metadata.PackageNotFoundError:
        pysat = None
    status = _git(package, "status", "--porcelain", "--untracked-files=no", "--", ".")
    return {
        "symq_path": str(package),
        "symq_version": getattr(symq, "__version__", None),
        "git_commit": _git(package, "rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
        "source_sha256": digest.hexdigest(),
        "source_files": len(sources),
        "native": native,
        "python_sat": pysat,
    }
