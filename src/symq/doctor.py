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

from .backends import BACKENDS, NATIVE_IMPORT_ERROR, has_native

try:
    from .backends import _zdd
except ImportError:
    _zdd = None


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


def doctor(stream: TextIO | None = None, *, require_native: bool = False) -> int:
    """Print the environment report and return a process exit code.

    The native core is optional, so its absence is reported but is not an error: the code is 0
    unless ``require_native`` is set and the core cannot be loaded, in which case it is 1.
    """
    from . import external  # imported lazily: probing the baselines can be slow

    out = stream if stream is not None else sys.stdout
    lines: list[str] = [
        "symq doctor:",
        "  Environment:",
        f"    - symq version:      {_version()}",
        f"    - Python version:    {platform.python_version()} ({platform.python_implementation()})",
        f"    - Platform:          {platform.platform()}",
        f"    - Executable:        {sys.executable}",
        "  Native ZDD Core (zdd-native, zdd-native-wide):",
    ]
    native = has_native() and _zdd is not None
    if native:
        widths = ", ".join(f"{name}: {getattr(BACKENDS[name], 'max_width', '?')}"
                           for name in ("zdd-native", "zdd-native-wide") if name in BACKENDS)
        lines.append(f"    [OK] Status: AVAILABLE (loaded from {_zdd.__file__})")
        lines.append(f"    [OK] Max variables:  {widths}")
    else:
        level = "ERROR" if require_native else "INFO"
        lines.append(f"    [{level}] Status: NOT AVAILABLE (pure-Python backends only)")
        if NATIVE_IMPORT_ERROR:
            lines.append(f"           Reason: {NATIVE_IMPORT_ERROR}")
        lines.extend(_toolchain_lines())

    lines.append(f"  Registered Backends ({len(BACKENDS)}):")
    for name in sorted(BACKENDS):
        tag = "native C core" if name.startswith("zdd-native") else "pure-python"
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
    return 1 if require_native and not native else 0
