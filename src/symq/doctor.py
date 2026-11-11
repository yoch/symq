"""Environment report for symq: native core, registered backends and external baselines.

Only the installed package is inspected; the build tooling (``tools/build_native.py``)
lives in the source tree and is not shipped with the wheel, so the advice printed for a
missing native core depends on how the package was installed (``symq._native_hint``).
"""
from __future__ import annotations

import platform
import shutil
import sys
import sysconfig
from importlib import import_module, metadata
from pathlib import Path
from types import ModuleType
from typing import TextIO

from ._native_hint import native_core_hint
from .backends import BACKENDS, NATIVE_IMPORT_ERROR, has_native

_zdd: ModuleType | None
try:
    _zdd = import_module("symq.backends._zdd")
except ImportError:
    _zdd = None


def _version() -> str:
    try:
        return metadata.version("symq")
    except metadata.PackageNotFoundError:
        return "unknown (not installed)"


def _toolchain_lines(reason: str | None) -> list[str]:
    compiler = (sysconfig.get_config_var("CC") or "cc").split()[0]
    found = shutil.which(compiler)
    include = Path(sysconfig.get_paths()["include"])
    lines = [
        f"           C compiler ({compiler}): {found or 'not found in PATH'}",
        f"           Python.h: {'found in ' + str(include) if (include / 'Python.h').is_file() else 'missing'}",
    ]
    hint = native_core_hint()
    if hint not in (reason or ""):  # the import error usually carries it already
        lines.append(f"           Hint: {hint}.")
    return lines


def report() -> dict:
    """Machine-readable environment and build identity (the content of ``doctor --json``).

    ``source_sha256`` digests every installed ``.py`` and ``.c`` file of the package, so a
    consumer can pin the exact implementation it qualified without re-hashing files itself.
    """
    import hashlib

    from . import external

    package = Path(__file__).resolve().parent
    sources = {}
    for path in sorted(package.rglob("*")):
        if path.suffix in {".py", ".c"} and "__pycache__" not in path.parts:
            sources[path.relative_to(package).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    aggregate = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sources.items()).encode())
    native: dict = {"available": has_native() and _zdd is not None,
                    "import_error": NATIVE_IMPORT_ERROR}
    if native["available"]:
        assert _zdd is not None and _zdd.__file__ is not None
        binary = Path(_zdd.__file__)
        native.update(path=str(binary), abi=getattr(_zdd, "ABI_VERSION", None),
                      sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                      max_variables={name: getattr(BACKENDS[name], "max_width", None)
                                     for name in ("zdd-native", "zdd-native-wide")
                                     if name in BACKENDS})
    try:
        from .sat import available, versions

        sat = {"available": available(), **versions()}
    except ImportError:  # pragma: no cover - symq.sat is pure Python
        sat = {"available": False}
    return {
        "schema_version": 1, "kind": "symq_doctor", "version": _version(),
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "platform": platform.platform(), "executable": sys.executable,
        "native": native, "sat": sat, "backends": sorted(BACKENDS),
        "external": {"versions": {name: version for name, version in external.versions().items()
                                  if version is not None},
                     "unavailable_adapters": sorted(external.UNAVAILABLE)},
        "source_sha256": aggregate.hexdigest(), "sources": sources,
    }


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
        assert _zdd is not None and _zdd.__file__ is not None
        widths = ", ".join(f"{name}: {getattr(BACKENDS[name], 'max_width', '?')}"
                           for name in ("zdd-native", "zdd-native-wide") if name in BACKENDS)
        lines.append(f"    [OK] Status: AVAILABLE (loaded from {_zdd.__file__})")
        lines.append(f"    [OK] Max variables:  {widths}")
    else:
        level = "ERROR" if require_native else "INFO"
        lines.append(f"    [{level}] Status: NOT AVAILABLE (pure-Python backends only)")
        if NATIVE_IMPORT_ERROR:
            lines.append(f"           Reason: {NATIVE_IMPORT_ERROR}")
        lines.extend(_toolchain_lines(NATIVE_IMPORT_ERROR))

    lines.append(f"  Registered Backends ({len(BACKENDS)}):")
    for name in sorted(BACKENDS):
        tag = "native C core" if name.startswith("zdd-native") else "pure-python"
        lines.append(f"    - {name:<17} [{tag}]")

    lines.append("  SAT engine (symq.sat):")
    try:
        from . import sat as sat_engine

        solver = ", ".join(f"{name} {version}"
                           for name, version in sat_engine.versions().items())
        sat = sat_engine.available()
    except ImportError:  # pragma: no cover - symq.sat is pure Python
        sat, solver = False, ""
    if sat:
        lines.append(f"    [OK] Status: AVAILABLE ({solver})")
    else:
        lines.append("    [INFO] Status: NOT INSTALLED (the symbolic engines do not need it)")
        lines.append("           Install it with: pip install 'symq[sat]'")

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
