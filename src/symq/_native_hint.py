"""How to obtain the optional native core, said for the installation at hand.

The messages that report a missing or stale C core used to advise ``python
tools/build_native.py``, a file that exists only in a source checkout. A user who installed a
wheel has no such file; a Windows user cannot build the core at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

REBUILD_FROM_SDIST = "SYMQ_REQUIRE_NATIVE=1 python -m pip install --force-reinstall --no-binary symq symq"
"""Builds the installed version from its source distribution and fails, instead of silently
staying pure Python, when the compiler or the Python headers are missing."""


def in_source_checkout() -> bool:
    """Whether this package is imported from a source tree that carries the build tool."""
    package = Path(__file__).resolve().parent
    return ((package / "backends" / "_zdd.c").is_file()
            and (package.parents[1] / "tools" / "build_native.py").is_file())


def native_core_hint() -> str:
    """One sentence: what this user can do to get the native core."""
    if sys.platform == "win32":
        return ("the native core is not available on Windows; the pure-Python 'zdd' backend "
                "gives the same answers")
    if in_source_checkout():
        return ("build it from this source checkout with 'python tools/build_native.py' "
                "('--diagnose' explains what is missing)")
    return ("this installation has no native core for this platform and Python version; with a "
            f"C compiler and the Python headers installed, rebuild it with '{REBUILD_FROM_SDIST}'")
