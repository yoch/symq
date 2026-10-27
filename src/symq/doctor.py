"""Environment report for symq: native core, registered backends and external baselines.

Only the installed package is inspected; the build tooling (``tools/build_native.py``)
lives in the source tree and is not shipped with the wheel.
"""
from __future__ import annotations

import platform
import shutil
import sys
import sysconfig
from importlib import metadata
from pathlib import Path
from typing import TextIO

from . import external
from .backends import BACKENDS, has_native

try:
    from .backends import _zdd
    from .backends.zdd_native import MAX_WIDTH
except ImportError:
    _zdd = None
    MAX_WIDTH = None


def _version() -> str:
    try:
        return metadata.version("symq")
    except metadata.PackageNotFoundError:
        return "unknown (not installed)"


def _toolchain_lines() -> list[str]:
    compiler = (sysconfig.get_config_var("CC") or "cc").split()[0]
    found = shutil.which(compiler)
    include = Path(sysconfig.get_paths()["include"])
    return [
        f"           C compiler ({compiler}): {found or 'not found in PATH'}",
        f"           Python.h: {'found in ' + str(include) if (include / 'Python.h').is_file() else 'missing'}",
        "           Hint: from a source checkout, run 'python tools/build_native.py --diagnose'.",
    ]


def doctor(stream: TextIO | None = None) -> int:
    """Print the environment report; returns 0 when the native core is loaded, 1 otherwise."""
    out = stream if stream is not None else sys.stdout
    lines: list[str] = [
        "symq doctor:",
        "  Environment:",
        f"    - symq version:      {_version()}",
        f"    - Python version:    {platform.python_version()} ({platform.python_implementation()})",
        f"    - Platform:          {platform.platform()}",
        f"    - Executable:        {sys.executable}",
        "  Native ZDD Core (zdd-native):",
    ]
    native = has_native() and _zdd is not None
    if native:
        lines.append(f"    [OK] Status: AVAILABLE (loaded from {_zdd.__file__})")
        lines.append(f"    [OK] Max native width:   {MAX_WIDTH} wires (uint64_t monomial masks)")
    else:
        lines.append("    [WARN] Status: NOT AVAILABLE (pure-Python mode)")
        lines.extend(_toolchain_lines())

    lines.append(f"  Registered Backends ({len(BACKENDS)}):")
    for name in sorted(BACKENDS):
        tag = "native C core" if name == "zdd-native" else "pure-python"
        lines.append(f"    - {name:<17} [{tag}]")

    lines.append("  External Baselines (symq.external):")
    if not external.UNAVAILABLE:
        versions = ", ".join(f"{k}: {v}" for k, v in external.versions().items())
        lines.append(f"    [OK] Status: AVAILABLE ({versions})")
    else:
        missing = ", ".join(sorted(external.UNAVAILABLE))
        lines.append(f"    [INFO] Status: OPTIONAL (missing: {missing})")
        lines.append("           Install external baselines with: pip install 'symq[external]'")

    print("\n".join(lines), file=out)
    return 0 if native else 1
