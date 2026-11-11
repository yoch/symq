"""How to obtain the optional native core, said for the installation at hand.

The messages that report a missing or stale C core used to advise ``python
tools/build_native.py``, a file that exists only in a source checkout. A user who installed a
wheel has no such file; a Windows user, or one on a free-threaded CPython, cannot build the core
at all.
"""
from __future__ import annotations

import sys
import sysconfig
from importlib import metadata
from pathlib import Path


def rebuild_command() -> str:
    """The command that rebuilds the installed version from its source distribution.

    * ``SYMQ_REQUIRE_NATIVE=1``: fail when the compiler or the Python headers are missing,
      instead of installing a pure-Python package again;
    * ``--no-cache-dir``: pip keeps the wheels it builds, and would otherwise reinstall the
      pure-Python one it built the first time without compiling anything;
    * ``symq==<version>``: this version, not the newest release on the index.
    """
    try:
        requirement = f"symq=={metadata.version('symq')}"
    except metadata.PackageNotFoundError:
        requirement = "symq"
    return ("SYMQ_REQUIRE_NATIVE=1 python -m pip install --force-reinstall --no-cache-dir "
            f"--no-binary symq {requirement}")


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
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        return ("the native core does not support free-threaded CPython; the pure-Python 'zdd' "
                "backend gives the same answers")
    if in_source_checkout():
        return ("build it from this source checkout with 'python tools/build_native.py' "
                "('--diagnose' explains what is missing)")
    return ("this installation has no native core for this platform and Python version; if it "
            "was installed from a package index and a C compiler and the Python headers are "
            f"available, rebuild it with '{rebuild_command()}'")
