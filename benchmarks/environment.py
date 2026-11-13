"""Machine description shared by every benchmark harness.

All harnesses record the same keys, so results from different campaigns can be compared without
guessing what a field meant in each one.
"""
from __future__ import annotations

import math
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

    A commit is claimed only when git tracks the imported package itself: an installed or copied
    package inside some checkout's ignored or untracked folder gets ``git_commit = None``.
    ``git_dirty`` counts modified tracked files and untracked ``.py``/``.c`` files of the package. No absolute path is
    recorded (records are committed as evidence): the package location is given relative to the
    repository root, or as ``"untracked"``, and the native binary by its file name.
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
        native = {"available": True, "file": binary.name,
                  "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
        try:
            from symq.backends import _zdd

            native["abi"] = getattr(_zdd, "ABI_VERSION", None)
        except ImportError as error:
            native.update(available=False, error=type(error).__name__)
    try:
        pysat = metadata.version("python-sat")
    except metadata.PackageNotFoundError:
        pysat = None
    tracked = _git(package, "ls-files", "--error-unmatch", "--", "__init__.py") is not None
    commit = dirty = None
    location = "untracked"
    if tracked:
        commit = _git(package, "rev-parse", "HEAD")
        status = _git(package, "status", "--porcelain", "--untracked-files=all", "--", ".")
        if status is not None:
            # A tracked change counts; an untracked file counts only if it is source that would
            # be imported (not bytecode or a build product such as the native binary).
            dirty = any(not line.startswith("??") or line.endswith((".py", ".c"))
                        for line in status.splitlines())
        prefix = _git(package, "rev-parse", "--show-prefix")
        location = (prefix or "").rstrip("/") or "."
    return {
        "symq_location": location,
        "symq_version": getattr(symq, "__version__", None),
        "git_commit": commit,
        "git_dirty": dirty,
        "source_sha256": digest.hexdigest(),
        "source_files": len(sources),
        "native": native,
        "python_sat": pysat,
    }


MACHINE_KEYS = ("python_version", "implementation", "platform", "machine", "cpu_model",
                "cpu_count", "cpu_affinity", "mem_total_kib")
"""Environment fields that must agree for two records to be compared (with the SAT library)."""


def machine_signature(record: dict) -> tuple:
    """What makes two records comparable: the machine, the interpreter and the SAT library."""
    environment = record.get("environment", {})
    return (*(environment.get(key) for key in MACHINE_KEYS),
            record.get("receipt", {}).get("python_sat"))


def machine_difference(left: dict, right: dict) -> str | None:
    """The first field that makes two records incomparable, or ``None``.

    The one rule used by ``benchmarks.quick`` and ``benchmarks.paired``. A missing field is a
    difference: two records that do not say what they ran on are not comparable.
    """
    for key in MACHINE_KEYS:
        current, previous = left.get("environment", {}), right.get("environment", {})
        if key not in current or key not in previous or current[key] != previous[key]:
            return f"environment.{key}"
    current, previous = left.get("receipt", {}), right.get("receipt", {})
    if ("python_sat" not in current or "python_sat" not in previous
            or current["python_sat"] != previous["python_sat"]):
        return "receipt.python_sat"
    return None


def cell_problem(record: dict, cell: dict) -> str | None:
    """Why a schema-2 quick-bench cell cannot enter a ratio, or ``None`` when it can.

    A cell must be ``ok`` with a positive finite median, and complete: every requested sample,
    or a consistent early stop after one sample above the slow-stop threshold (slow cells are
    the ones a regression check needs most, so they are compared, never dropped).
    """
    if cell.get("status") != "ok":
        return str(cell.get("status", "missing status"))
    requested = record.get("repetitions")
    seconds = cell.get("seconds", [])
    if not isinstance(requested, int) or requested < 1 or not isinstance(seconds, list):
        return "incomplete repetitions"
    if len(seconds) != requested:
        slow = record.get("slow_stop_seconds")
        if not (cell.get("stopped_after_slow_sample") is True
                and isinstance(slow, (int, float)) and 1 <= len(seconds) < requested
                and all(isinstance(value, (int, float)) for value in seconds)
                and seconds[-1] > slow and all(value <= slow for value in seconds[:-1])):
            return "incomplete repetitions"
    median = cell.get("median_seconds")
    if not isinstance(median, (int, float)) or not math.isfinite(median) or median <= 0:
        return "invalid median"
    return None
